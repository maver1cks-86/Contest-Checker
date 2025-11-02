from flask import Flask, jsonify, request, redirect, session, url_for
import requests
from datetime import datetime, timezone, timedelta
import pytz
import os
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pymongo import MongoClient
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from flask_cors import CORS
import uuid

app = Flask(__name__)
# This is required for Flask sessions, which we use to track user logins
# Set this as an Environment Variable in Render: FLASK_SECRET_KEY
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_bad_secret_key_for_dev_only")
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

# ======= CONFIG =======
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://deepikapattem:chinni12@aviation-cluster.rzvts.mongodb.net/?appName=Aviation-Cluster")
CLIENT_SECRETS_FILE = 'client_secret.json'

# --- NEW: We get these from environment variables in Render ---
# You must get these from your client_secret.json
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

# --- MODIFIED: More robust check for Render ---
# This must be the *exact* URL you set in Google Cloud Console
# On Render, it will be "https://your-app-name.onrender.com/auth/google/callback"
if 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
    # We are on Render
    BASE_URL = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}"
else:
    # We are running locally
    BASE_URL = "http://localhost:5000"
    
REDIRECT_URI = f"{BASE_URL}/auth/google/callback"

# --- DEBUG PRINT ---
print(f"Flask App Started. Using REDIRECT_URI: {REDIRECT_URI}")
# --- END DEBUG PRINT ---

SCOPES = ['https://www.googleapis.com/auth/calendar']
client = MongoClient(MONGO_URI)
db = client["contest_tracker"]
contests_col = db["contests"]
# --- NEW: A collection to store user refresh tokens ---
users_col = db["users"]


# ======= NEW: MULTI-USER GOOGLE AUTH =======

def get_google_flow():
    """Creates a Flow object for the web OAuth 2.0 flow."""
    return Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.token.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

def get_service_for_user(user):
    """
    Creates a Google API service object for a specific user
    using their stored refresh token.
    """
    if not user.get('refresh_token'):
        print(f"User {user['_id']} has no refresh token.")
        return None

    try:
        creds = Credentials(
            None,
            refresh_token=user['refresh_token'],
            token_uri="https://oauth2.token.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=SCOPES
        )

        # Refresh the token to get a new access token
        creds.refresh(GoogleAuthRequest())
        
        # Save the (potentially new) refresh token if one is returned
        # Note: This usually happens only on the first exchange
        if creds.refresh_token and creds.refresh_token != user['refresh_token']:
            users_col.update_one(
                {'_id': user['_id']},
                {'$set': {'refresh_token': creds.refresh_token}}
            )

        return build('calendar', 'v3', credentials=creds)

    except Exception as e:
        print(f"Error refreshing token for user {user['_id']}: {e}")
        # If refresh fails (e.g., token revoked), remove the bad token
        users_col.update_one(
            {'_id': user['_id']},
            {'$unset': {'refresh_token': ""}}
        )
        return None

# ======= HELPER: ADD CALENDAR EVENT (Modified) =======
# --- MODIFIED: This function now requires a 'service' object ---
def add_google_calendar_event(contest, service):
    """Adds a single contest event to a user's calendar via their service object."""
    try:
        calendar_id = 'primary'
        event_title = f"{contest['title']} (Reminder)"

        # Check if event with this title already exists
        events_result = service.events().list(
            calendarId=calendar_id,
            q=event_title,
            maxResults=10
        ).execute()
        items = events_result.get('items', [])
        
        existing_titles = [item['summary'] for item in items if 'summary' in item]
        
        if event_title in existing_titles:
            # print(f"Event already exists for: {contest['title']}")
            return False # Not new

        remind_time_start = contest['start'] - timedelta(hours=1)
        remind_time_end = remind_time_start + timedelta(minutes=1)

        event_body = {
            'summary': event_title,
            'description': f"Contest URL: {contest['url']}",
            'start': {'dateTime': remind_time_start.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': remind_time_end.isoformat(), 'timeZone': 'UTC'},
            'reminders': {
                'useDefault': False,
                'overrides': [{'method': 'popup', 'minutes': 0}],
            },
        }
        
        service.events().insert(calendarId=calendar_id, body=event_body).execute()
        print(f"Added Calendar event for {contest['title']}")
        return True # Is new

    except Exception as e:
        print(f"Error adding Google Calendar event for {contest['title']}: {e}")
        return False


# ======= FETCHERS (Unchanged) =======
def get_leetcode():
    print("Fetching LeetCode...")
    url = "https://leetcode.com/graphql"
    query = {
        "operationName": "allContests",
        "variables": {},
        "query": "query allContests { allContests { title titleSlug startTime duration } }"
    }
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com/contest/",
        "Origin": "https://leetcode.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/128.0.0.0 Safari/537.36",
    }
    
    try:
        response = requests.post(url, json=query, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching LeetCode: {e}")
        return []

    data = response.json()
    contests = data.get("data", {}).get("allContests", [])
    now_ts = datetime.now(timezone.utc).timestamp()
    res = []

    for c in contests:
        start_ts = c.get("startTime")
        if not start_ts: continue
        if start_ts >= now_ts:
            start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            res.append({
                "platform": "LeetCode",
                "title": c.get("title"),
                "url": f"https://leetcode.com/contest/{c.get('titleSlug')}/",
                "start": start_dt
            })
    print(f"Found {len(res)} upcoming LeetCode contests.")
    return res

def get_codechef():
    print("Fetching CodeChef...")
    url = "https://www.codechef.com/api/list/contests/all"
    headers = {
        "User-Agent": "Mozilla/5.0", "Referer": "https://www.codechef.com/contests",
        "Origin": "https://www.codechef.com", "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        contests = data.get("future_contests", []) + data.get("present_contests", [])
        now = datetime.now(timezone.utc)
        res = []

        for c in contests:
            start_iso = c.get("contest_start_date_iso")
            if not start_iso: continue
            start_dt = datetime.fromisoformat(start_iso)
            if start_dt < now: continue
            res.append({
                "platform": "CodeChef",
                "title": c.get("contest_name", ""),
                "url": f"https://www.codechef.com/{c.get('contest_code')}",
                "start": start_dt.astimezone(timezone.utc)
            })
        print(f"Found {len(res)} upcoming CodeChef contests.")
        return res
    except Exception as e:
        print(f"Error fetching CodeChef: {e}")
        return []

def get_codeforces():
    print("Fetching Codeforces...")
    url = "https://codeforces.com/api/contest.list"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching Codeforces: {e}")
        return []

    res = []
    now = datetime.now(timezone.utc)
    for c in data.get("result", []):
        if c.get("phase") == "BEFORE":
            start_ts = c.get("startTimeSeconds")
            if not start_ts: continue
            start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            if start_dt > now:
                res.append({
                    "platform": "Codeforces",
                    "title": c.get("name", "Unknown Contest"),
                    "url": f"https://codeforces.com/contest/{c['id']}",
                    "start": start_dt
                })
    print(f"Found {len(res)} upcoming Codeforces contests.")
    return res

def get_mentorpick():
    print("Fetching MentorPick...")
    url = "https://mentorpick.com/api/contest/public?title=&status=scheduled&limit=50&page=1&type=null"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://mentorpick.com/contests/explore/scheduled?mode=null", # <-- FIXED
        "Origin": "https://mentorpick.com"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching MentorPick: {e}")
        return []
        
    res = []
    now = datetime.now(timezone.utc)
    for c in data.get("data", []):
        try:
            start_dt = datetime.strptime(c["startTime"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            if start_dt > now:
                res.append({
                    "platform": "MentorPick", "title": c["title"],
                    "url": f"https://mentorpick.com/contest/{c['slug']}", "start": start_dt
                })
        except Exception as e:
            print(f"Error parsing MentorPick date '{c.get('startTime')}': {e}")
    print(f"Found {len(res)} upcoming MentorPick contests.")
    return res


# ======= NEW: CORE SYNC LOGIC (FOR ONE USER) =======
# This can be called by the web app (manual) or cron job (periodic)

def run_sync_for_user(user_id):
    """
    Runs the complete sync process for a single user.
    Fetches their credentials, scrapes contests, and adds to their calendar.
    """
    user = users_col.find_one({'_id': user_id})
    if not user:
        print(f"Sync failed: User {user_id} not found.")
        return {"error": "User not found"}, 404

    service = get_service_for_user(user)
    if not service:
        print(f"Sync failed: Could not get Google service for user {user_id}.")
        return {"error": "Could not authenticate with Google. Please try logging in again."}, 500

    print(f"--- Starting sync for user {user.get('email', user_id)} ---")
    contests = []
    new_contests_list = []
    fetchers = [get_leetcode, get_codechef, get_codeforces, get_mentorpick]
    
    for fetcher in fetchers:
        try:
            contests.extend(fetcher())
        except Exception as e:
            print(f"Error in fetcher {fetcher.__name__}: {e}")

    contests.sort(key=lambda x: x["start"])
    print(f"Total contests found: {len(contests)}")
    new_events_added = 0
    
    # We now check against the user's *calendar*, not MongoDB,
    # because MongoDB was single-tenant.
    # The add_google_calendar_event function handles duplicate checking.

    for contest in contests:
        try:
            # Add to Google Calendar
            is_new = add_google_calendar_event(contest, service)
            if is_new:
                new_events_added += 1
                json_serializable_contest = contest.copy()
                json_serializable_contest['start'] = contest['start'].isoformat()
                new_contests_list.append(json_serializable_contest)

        except Exception as e:
            print(f"Error processing contest {contest.get('title')}: {e}")

    # Update the user's 'last_synced' timestamp
    users_col.update_one(
        {'_id': user['_id']},
        {'$set': {'last_synced': datetime.now(timezone.utc)}}
    )

    print(f"--- Sync complete for user {user.get('email', user_id)}. Added {new_events_added} new events. ---")
    return {
        "message": f"Sync complete. Added {new_events_added} new events to your calendar.",
        "new_contests_added": new_events_added,
        "total_contests_checked": len(contests),
        "new_contests": new_contests_list
    }


# ======= NEW: FLASK WEB ENDPOINTS =======

@app.route("/login")
def login():
    """
    1. Generates a new Google Auth URL.
    2. Stores a 'state' token in the user's session to prevent CSRF.
    3. Redirects the user's browser to Google to log in.
    """
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent' # Force prompt to ensure we get a refresh_token
    )
    session['state'] = state
    
    # --- DEBUG PRINT ---
    # This will show the *exact* URL Google is being told to redirect to.
    print(f"Generated REDIRECT_URI for flow: {flow.redirect_uri}")
    print(f"Generated Authorization URL: {authorization_url}")
    # --- END DEBUG PRINT ---
    
    return redirect(authorization_url)

@app.route("/auth/google/callback")
def auth_google_callback():
    """
    1. Google redirects the user here after login.
    2. Verifies the 'state' token.
    3. Exchanges the 'code' from Google for auth tokens.
    4. Gets the user's profile info.
    5. Saves the user and their *refresh_token* to MongoDB.
    6. Logs the user in by saving their ID in the Flask session.
    7. Redirects the user back to the React frontend.
    """
    # --- DEBUG PRINT ---
    print(f"Callback received. Full URL: {request.url}")
    # --- END DEBUG PRINT ---

    flow = get_google_flow()
    
    # Check for state mismatch
    if request.args.get('state') != session.get('state'):
        print("!!! STATE MISMATCH ERROR !!!")
        return jsonify({"error": "State mismatch, possible CSRF attack."}), 400

    try:
        # Exchange the code for credentials
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        
        # Get user info
        user_service = build('oauth2', 'v2', credentials=creds)
        user_info = user_service.userinfo().get().execute()
        
        user_id = user_info['id']       # Google's unique 'sub'
        user_email = user_info['email']
        user_name = user_info.get('name')

        # --- This is the critical part ---
        # Save the user and their refresh token to the database
        users_col.update_one(
            {'_id': user_id},
            {
                '$set': {
                    'email': user_email,
                    'name': user_name,
                    'refresh_token': creds.refresh_token,
                    'updated_at': datetime.now(timezone.utc)
                },
                '$setOnInsert': {
                    'created_at': datetime.now(timezone.utc)
                }
            },
            upsert=True
        )

        # Log the user in by saving their ID in the session
        session['user_id'] = user_id
        session['user_email'] = user_email
        
        # Redirect back to the React app's homepage
        # On Render, this will be your main site URL
        frontend_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5173')
        return redirect(frontend_url)

    except Exception as e:
        print(f"Error in OAuth callback: {e}")
        return jsonify({"error": "Authentication failed."}), 500

@app.route("/check-auth", methods=["GET"])
def check_auth():
    """A simple endpoint for React to check if a user is logged in."""
    if 'user_id' in session:
        return jsonify({
            "is_logged_in": True,
            "user": {
                "id": session['user_id'],
                "email": session.get('user_email')
            }
        })
    else:
        return jsonify({"is_logged_in": False}), 401

@app.route("/logout", methods=["POST"])
def logout():
    """Logs the user out by clearing the session."""
    session.clear()
    return jsonify({"message": "Logged out successfully."}), 200


@app.route("/", methods=["POST"])
def manual_sync():
    """
    This is the new "home" endpoint, triggered by the React app's "Sync" button.
    It performs a manual sync *only for the logged-in user*.
    """
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    user_id = session['user_id']
    result = run_sync_for_user(user_id)
    return jsonify(result)


# ======= MAIN =======
if __name__ == "__main__":
    # Set OS-level env for local dev to allow insecure transport
    # Render's HTTPS proxy handles this in production.
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        print("="*50)
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET not set.")
        print("Please set these as environment variables before running.")
        print("You can get them from your client_secret.json file.")
        print("Example: export GOOGLE_CLIENT_ID='your-id'")
        print("="*50)
    else:
        app.run(debug=True, host="0.0.0.0", port=5000)

