import json
import random
import time
import re
import requests
from datetime import datetime
from collections import defaultdict

from locust import HttpUser, task, between, LoadTestShape

###############################################################################
# STEP 1: CONFIGURATION
###############################################################################

# Load traffic pattern JSON file
TRAFFIC_FILE = "processed_logs_IST.json"

with open(TRAFFIC_FILE, "r") as f:
    TRAFFIC_DATA = json.load(f)

# Load credentials JSON file
CREDS_FILE = "credentials.json"

try:
    with open(CREDS_FILE, "r") as f:
        CREDENTIALS = json.load(f)
except FileNotFoundError:
    # Default credentials if file not found
    CREDENTIALS = {
        "users": [
            {"username": "team1", "password": "password1"},
            {"username": "team2", "password": "password2"},
            {"username": "team3", "password": "password3"}
        ]
    }

# Only focus on these protected URLs
PROTECTED_URLS = [
    "/team", 
    "/team/", 
    "/team/submit", 
    "/team/problems",
    "/team/scoreboard", 
    "/team/clarifications",
    "/team/problems/{id}/text",
    "/team/submit/{id}",
    "/team/team/{id}",
    "/team/submission/{id}",
    "/team/clarifications/{id}",
    "/team/{id}/samples.zip"
]

# Request headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Content-Type": "application/x-www-form-urlencoded"
}

# Convert time intervals into a dictionary (ignore timestamps, use as buckets)
time_buckets = {}

for time_slot, data in TRAFFIC_DATA.items():
    start_time, _ = time_slot.split(" - ")
    
    try:
        # Convert time to HH:MM format
        start_dt = datetime.strptime(start_time, "%H:%M").strftime("%H:%M")
        
        # Filter to only include protected URLs
        filtered_url_list = {}
        for url, url_data in data.get("url_list", {}).items():
            # Check if the URL is in our protected list or starts with any protected prefix
            if url in PROTECTED_URLS or any(url.startswith(protected.replace("{id}", "")) for protected in PROTECTED_URLS):
                filtered_url_list[url] = url_data
        
        # Create a new data object with the filtered URL list
        filtered_data = data.copy()
        filtered_data["url_list"] = filtered_url_list
        
        time_buckets[start_dt] = filtered_data
    except Exception as e:
        print(f"Skipping invalid time interval {time_slot}: {e}")

###############################################################################
# STEP 2: CUSTOM LOAD SHAPE - ADJUST USERS PER 5-MIN INTERVAL
###############################################################################

class CustomLoadShape(LoadTestShape):
    """
    Dynamically sets users based on the current time bucket's request volume.
    """

    def tick(self):
        current_time = datetime.now().strftime("%H:%M")  # Get current HH:MM
        current_bucket = None

        # Find the current 5-minute interval (round down)
        for bucket_time in sorted(time_buckets.keys()):
            bucket_hour, bucket_minute = map(int, bucket_time.split(":"))
            if datetime.now().hour == bucket_hour and datetime.now().minute >= bucket_minute:
                current_bucket = bucket_time

        if not current_bucket:
            return None  # No valid bucket, stop test

        # Get request volume from this time bucket (only protected URLs)
        bucket_data = time_buckets.get(current_bucket, {})
        total_requests = sum(url_data["count"] for url_data in bucket_data.get("url_list", {}).values())

        if total_requests == 0:
            return None  # No protected URL requests in this bucket

        # Use exactly as many users as needed based on request count
        # Each user will make approximately one request in this time bucket
        target_users = max(total_requests, 1)
        
        # Define spawn rate (how fast users are added)
        spawn_rate = max(target_users // 5, 1)  # Faster spawn rate to ensure all users are active

        print(f"Time bucket: {current_bucket}, Target users: {target_users}, Spawn rate: {spawn_rate}")
        return (target_users, spawn_rate)


###############################################################################
# STEP 3: AUTHENTICATION HELPER FUNCTIONS
###############################################################################

def extract_csrf_token(html):
    """Extract CSRF token from HTML page."""
    csrf_token_match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return csrf_token_match.group(1) if csrf_token_match else None

def login_and_extract_session(client, username, password):
    """
    Logs in a user and extracts CSRF token & PHPSESSID.
    
    Args:
        client: Locust client for making requests
        username: Login username
        password: Login password
        
    Returns:
        tuple: (csrf_token, cookies_dict, success_flag)
    """
    # Step 1: GET login page to fetch CSRF token
    response = client.get("/login")
    
    if response.status_code != 200:
        print(f"❌ Failed to access login page for {username}: {response.status_code}")
        return None, {}, False
        
    csrf_token = extract_csrf_token(response.text)
    
    if not csrf_token:
        print(f"❌ CSRF Token not found for {username}!")
        return None, {}, False
        
    print(f"✅ CSRF Token for {username}: {csrf_token[:10]}...")
    
    # Step 2: Perform login
    login_data = {
        "_csrf_token": csrf_token,
        "_username": username,
        "_password": password
    }
    
    login_response = client.post("/login", data=login_data)
    
    # Step 3: Check for successful login (302 redirect or 200 with dashboard)
    if login_response.status_code in [200, 302]:
        # Extract cookies from the client's cookiejar
        cookies_dict = {}
        for cookie in client.cookies:
            cookies_dict[cookie.name] = cookie.value
            
        if 'PHPSESSID' in cookies_dict:
            print(f"✅ Extracted PHPSESSID for {username}: {cookies_dict['PHPSESSID'][:5]}...")
            return csrf_token, cookies_dict, True
        else:
            print(f"❌ PHPSESSID not found for {username}!")
            return csrf_token, cookies_dict, False
    else:
        print(f"❌ Login failed for {username}: {login_response.status_code}")
        return csrf_token, {}, False


###############################################################################
# STEP 4: DEFINE LOCUST USER BEHAVIOR
###############################################################################

class DOMjudgeUser(HttpUser):
    """
    Simulates user requests for protected endpoints based on the JSON traffic pattern.
    Handles PHP Session authentication properly.
    """
    wait_time = between(1, 3)  # Random wait time
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_authenticated = False
        self.csrf_token = None
        self.cookies = {}
        
        # Randomly select credentials for this user
        if CREDENTIALS.get("users"):
            self.user_creds = random.choice(CREDENTIALS["users"])
        else:
            self.user_creds = {"username": "default", "password": "default"}

    def on_start(self):
        """
        Authenticate user when starting the test
        """
        self.start_time = time.time()
        
        # Set default headers
        for name, value in HEADERS.items():
            self.client.headers[name] = value
            
        self.authenticate()
        
    def authenticate(self):
        """
        Performs PHP session-based authentication.
        """
        if not self.is_authenticated:
            self.csrf_token, self.cookies, success = login_and_extract_session(
                self.client,
                self.user_creds["username"],
                self.user_creds["password"]
            )
            
            self.is_authenticated = success
            
            # If login failed, try once more after a short delay
            if not success:
                time.sleep(2)
                self.csrf_token, self.cookies, success = login_and_extract_session(
                    self.client,
                    self.user_creds["username"],
                    self.user_creds["password"]
                )
                self.is_authenticated = success

    @task
    def send_protected_request(self):
        """
        Sends requests only to protected endpoints based on the traffic pattern.
        """
        if not self.is_authenticated:
            self.authenticate()
            if not self.is_authenticated:
                return  # Skip if authentication failed
                
        current_time = datetime.now().strftime("%H:%M")

        # Find the active bucket
        current_bucket = None
        for bucket_time in sorted(time_buckets.keys()):
            bucket_hour, bucket_minute = map(int, bucket_time.split(":"))
            if datetime.now().hour == bucket_hour and datetime.now().minute >= bucket_minute:
                current_bucket = bucket_time

        if not current_bucket:
            return  # No valid bucket found

        # Get request distribution for this time bucket (filtered for protected URLs only)
        bucket_data = time_buckets.get(current_bucket, {}).get("url_list", {})

        # Build a weighted request list based on count
        request_choices = []
        for url, url_data in bucket_data.items():
            request_choices.extend([url] * url_data["count"])

        if not request_choices:
            return  # No protected URLs to request in this bucket

        # Pick a URL based on frequency
        url_to_request = random.choice(request_choices)
        
        # Handle URL parameters
        if "{id}" in url_to_request:
            # Replace {id} with an actual ID (customize based on your needs)
            url_to_request = url_to_request.replace("{id}", str(random.randint(1, 100)))
        
        # Choose appropriate method based on URL
        if "/team/submit" in url_to_request:
            self.submit_solution(url_to_request)
        else:
            try:
                self.client.get(url_to_request)
            except Exception as e:
                print(f"Error requesting {url_to_request}: {e}")
                # If we get a session error, try to re-authenticate
                if "session" in str(e).lower() or "unauthorized" in str(e).lower():
                    self.is_authenticated = False
                    self.authenticate()

    def submit_solution(self, url):
        """
        Handles submission-specific requests with CSRF token and PHP session.
        """
        if not self.is_authenticated:
            self.authenticate()
            if not self.is_authenticated:
                return  # Skip if authentication failed
        
        problem_id = url.split("/")[-1] if url.split("/")[-1].isdigit() else random.randint(1, 10)
        language = random.choice(["python", "java", "cpp"])
        
        # Get CSRF token for the submission form first
        try:
            response = self.client.get(f"/team/submit/{problem_id}")
            form_csrf_token = extract_csrf_token(response.text)
            
            if not form_csrf_token:
                print(f"❌ CSRF Token not found for submission form!")
                return
                
            # Simulated file content
            file_content = f"print('Hello, World! Problem {problem_id}')" if language == "python" else "class Main { public static void main(String[] args) {} }"
            
            # Submit solution with CSRF token
            submit_data = {
                "_csrf_token": form_csrf_token,
                "problem": problem_id,
                "language": language,
            }
            
            files = {
                "code": (f"solution.{language}", file_content)
            }
            
            self.client.post(
                url,
                data=submit_data,
                files=files
            )
        except Exception as e:
            print(f"Error submitting solution: {e}")
            # If we get a session error, try to re-authenticate
            if "session" in str(e).lower() or "unauthorized" in str(e).lower():
                self.is_authenticated = False
                self.authenticate()


###############################################################################
# STEP 5: RUN LOCUST WITH THIS CONFIGURATION
###############################################################################

# """
# How to run:
# 1. Save this script as `locustfile.py`
# 2. Ensure `traffic_pattern.json` is in the same directory
# 3. Create a `credentials.json` file with user credentials in the format:
#    {
#      "users": [
#        {"username": "team1", "password": "password1"},
#        {"username": "team2", "password": "password2"}
#      ]
#    }
# 4. Run: `locust -f locustfile.py`
# 5. Open `http://localhost:8089` in your browser to start the test.
# """