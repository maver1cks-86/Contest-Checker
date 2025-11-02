import os
from pymongo import MongoClient
from contest_reminder import run_sync_for_user, users_col
from datetime import datetime, timezone

def run_periodic_sync():
    """
    This is the main function for the Render Cron Job.
    It finds all users who have a refresh_token and runs
    the sync process for each one.
    """
    print(f"--- Cron Job Started: {datetime.now(timezone.utc).isoformat()} ---")
    
    # Find all users who have authenticated (i.e., they have a refresh_token)
    all_users = users_col.find({"refresh_token": {"$exists": True, "$ne": None}})
    
    user_count = 0
    for user in all_users:
        user_count += 1
        user_id = user['_id']
        user_email = user.get('email', user_id)
        
        print(f"\nProcessing user: {user_email}")
        try:
            run_sync_for_user(user_id)
        except Exception as e:
            print(f"!!! CRITICAL ERROR syncing for {user_email}: {e}")
            # Continue to the next user
            pass
            
    print(f"\n--- Cron Job Finished. Processed {user_count} users. ---")

if __name__ == "__main__":
    # Ensure environment variables are set (needed for app import)
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')
    
    # Check for required env vars
    if not os.environ.get("GOOGLE_CLIENT_ID") or not os.environ.get("GOOGLE_CLIENT_SECRET"):
        print("CRITICAL: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.")
    elif not os.environ.get("MONGO_URI"):
         print("CRITICAL: MONGO_URI must be set.")
    else:
        run_periodic_sync()
