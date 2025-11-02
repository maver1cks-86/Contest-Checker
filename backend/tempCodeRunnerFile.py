from flask import Flask, jsonify
import requests
from datetime import datetime, timezone, timedelta
import pytz
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pymongo import MongoClient

app = Flask(__name__)

# ======= CONFIG =======
# IMPORTANT: Replace with your own MongoDB connection string
MONGO_URI = "mongodb+srv://deepikapattem:chinni12@aviation-cluster.rzvts.mongodb.net/?appName=Aviation-Cluster"
client = MongoClient(MONGO_URI)
db = client["contest_tracker"]
contests_col = db["contests"]

# ======= GOOGLE TASKS AUTH =======
SCOPES = ['https://www.googleapis.com/auth/tasks']
TOKEN_FILE = 'token.pkl'
# IMPORTANT: You must have a 'client_secret.json' file in the same directory
# from Google Cloud Console with Tasks API enabled.
CLIENT_SECRETS_FILE = 'client_secret.json'


def get_google_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(None) # Pass None for Request, will be handled
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print(f"Error: '{CLIENT_SECRETS_FILE}' not found.")
                print("Please download it from Google Cloud Console and place it in the same directory.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
            
    return build('tasks', 'v1', credentials=creds)


# Try to initialize service on startup to trigger auth flow if needed
service = get_google_service()


# ======= HELPER: ADD TASK =======
def add_google_task(contest):
    if service is None:
        print("Google Tasks service is not available. Skipping task creation.")
        return
        
    task_lists = service.tasklists().list().execute()
    default_list_id = task_lists.get('items', [{}])[0].get('id', '@default') # Get first list ID

    # Check for existing tasks to avoid duplicates
    try:
        task_list = service.tasks().list(tasklist=default_list_id).execute()
        existing = [t['title'] for t in task_list.get('items', [])]

        task_title = f"{contest['title']} (1 hour before)"
        if task_title in existing:
            print(f"Already added: {contest['title']}")
            return

        # Only one reminder: 1 hour before
        remind_time = contest['start'] - timedelta(hours=1)
        body = {
            'title': task_title,
            'notes': contest['url'],
            'due': remind_time.isoformat()
        }
        service.tasks().insert(tasklist=default_list_id, body=body).execute()
        print(f"Added reminder for {contest['title']} (1 hour before)")
    except Exception as e:
        print(f"Error adding Google Task for {contest['title']}: {e}")


# ======= FETCHERS =======
def get_leetcode():
    url = "https://leetcode.com/graphql"
    query = {
        "operationName": "allContests",
        "variables": {},
        "query": """
        query allContests {
          allContests {
            title
            titleSlug
            startTime
          }
        }
        """
    }

    headers = {
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com/contest/",
        "Origin": "https://leetcode.com",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.post(url, json=query, headers=headers)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching LeetCode: {e}")
        return []

    contests = response.json().get("data", {}).get("allContests", [])
    now = datetime.now(timezone.utc)
    today = now.date()

    res = []
    for c in contests:
        start_dt = datetime.fromtimestamp(c["startTime"], tz=timezone.utc)
        if start_dt.date() >= today:  # ✅ only today or later
            res.append({
                "platform": "LeetCode",
                "title": c["title"],
                "url": f"https://leetcode.com/contest/{c['titleSlug']}/",
                "start": start_dt
            })
    return res


def get_codechef():
    url = "https://www.codechef.com/api/list/contests/all"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.codechef.com/contests",
        "Origin": "https://www.codechef.com",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching CodeChef: {e}")
        return []
        
    contests = data.get("future_contests", []) + data.get("present_contests", [])
    now = datetime.now(timezone.utc)
    today = now.date()
    res = []

    for c in contests:
        start_iso = c.get("contest_start_date_iso")
        if start_iso:
            try:
                start_dt = datetime.fromisoformat(start_iso)
                if start_dt.date() >= today:
                    res.append({
                        "platform": "CodeChef",
                        "title": c["contest_name"],
                        "url": f"https://www.codechef.com/{c['contest_code']}",
                        "start": start_dt
                    })
            except ValueError:
                print(f"Skipping CodeChef contest with invalid date: {start_iso}")
    return res


def get_codeforces():
    print("Fetching Codeforces contests...")
    url = "https://codeforces.com/api/contest.list"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching Codeforces: {e}")
        return []

    res = []
    now = datetime.now(timezone.utc)
    today = now.date()

    for c in data.get("result", []):
        if c.get("phase") == "BEFORE":
            start_ts = c.get("startTimeSeconds")
            if not start_ts:
                continue
            start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            if start_dt.date() >= today:
                res.append({
                    "platform": "Codeforces",
                    "title": c.get("name", "Unknown Contest"),
                    "url": f"https://codeforces.com/contest/{c['id']}",
                    "start": start_dt
                })
    print(f"Found {len(res)} upcoming Codeforces contests.")
    return res


def get_mentorpick():
    url = "https://mentorpick.com/api/contest/public?title=&status=scheduled&limit=50&page=1&type=null"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://mentorpick.com/contests/explore/scheduled?mode=null",
        "Origin": "https://mentorpick.com"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching MentorPick: {e}")
        return []
        
    res = []
    now = datetime.now(timezone.utc)
    today = now.date()

    for c in data.get("data", []):
        try:
            start_dt = datetime.strptime(c["startTime"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            if start_dt.date() >= today:
                res.append({
                    "platform": "MentorPick",
                    "title": c["title"],
                    "url": f"https://mentorpick.com/contest/{c['slug']}",
                    "start": start_dt
                })
        except ValueError:
             print(f"Skipping MentorPick contest with invalid date: {c.get('startTime')}")
    return res


# ======= ROOT ENDPOINT =======
@app.route("/", methods=["GET"])
def home():
    print("Fetching all contests...")
    # Ensure service is initialized for this request
    global service
    if service is None:
        service = get_google_service()
        if service is None:
            return jsonify({"error": "Failed to initialize Google Tasks service. Check 'client_secret.json'."}), 500

    contests = []
    new_contests_list = []

    for fetcher in [get_leetcode, get_codechef, get_codeforces, get_mentorpick]:
        contests.extend(fetcher())

    contests.sort(key=lambda x: x["start"])

    for contest in contests:
        # Check if already exists in MongoDB
        if contests_col.find_one({"title": contest["title"], "platform": contest["platform"]}):
            print(f"Skipping duplicate: {contest['title']}")
            continue

        # Insert new contest
        contest_to_insert = {
            **contest,
            "added_at": datetime.now(timezone.utc)
        }
        contests_col.insert_one(contest_to_insert)
        
        # We need to remove the 'start' datetime object before returning JSON
        contest_json = contest.copy()
        contest_json['start'] = contest['start'].isoformat()
        new_contests_list.append(contest_json)
        print(f"Inserted new contest: {contest['title']}")

        # Add to Google Tasks
        add_google_task(contest)

    return jsonify({
        "message": "Synced new contests to Google Tasks and MongoDB ✅",
        "new_contests_added": len(new_contests_list),
        "total_contests_checked": len(contests),
        "new_contests": new_contests_list
    })


# ======= PLATFORM-SPECIFIC ENDPOINTS =======
@app.route("/leetcode", methods=["GET"])
def leetcode_route():
    contests = get_leetcode()
    for c in contests: c['start'] = c['start'].isoformat()
    return jsonify({"platform": "LeetCode", "count": len(contests), "contests": contests})


@app.route("/codechef", methods=["GET"])
def codechef_route():
    contests = get_codechef()
    for c in contests: c['start'] = c['start'].isoformat()
    return jsonify({"platform": "CodeChef", "count": len(contests), "contests": contests})


@app.route("/codeforces", methods=["GET"])
def codeforces_route():
    contests = get_codeforces()
    for c in contests: c['start'] = c['start'].isoformat()
    return jsonify({"platform": "Codeforces", "count": len(contests), "contests": contests})


@app.route("/mentorpick", methods=["GET"])
def mentorpick_route():
    contests = get_mentorpick()
    for c in contests: c['start'] = c['start'].isoformat()
    return jsonify({"platform": "MentorPick", "count": len(contests), "contests": contests})


# ======= MAIN =======
if __name__ == "__main__":
    app.run(debug=True)
