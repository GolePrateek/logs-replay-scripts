import time, os 
import re
from locust import HttpUser, task, between
import json

json_log_file = "parsed_logs.json"

def load_parsed_logs(json_file_path):
    """Load pre-parsed logs from a JSON file."""
    try:
        with open(json_file_path, "r") as file:
            log_data = json.load(file)  # Load JSON data
            return log_data
    except Exception as e:
        print(f"Error loading logs: {e}")
        return []

# Load logs from JSON
log_entries = load_parsed_logs(json_log_file)

# Locust User Class
class AuthenticatedUser(HttpUser):
    wait_time = between(1, 3)  # Simulating real user wait time
    csrf_token = None  # Store CSRF token globally for reuse
    session_cookie = None  # Store session cookie

    def on_start(self):
        """Login once before running any tests."""
        self.login()

    def login(self):
        """Perform login and store CSRF token & session cookie."""
        print("Logging in...")

        # Step 1: GET login page to fetch CSRF token
        response = self.client.get("/login")
        csrf_token = self.extract_csrf_token(response.text)

        if not csrf_token:
            print("Failed to extract CSRF token!")
            return

        print(f"CSRF Token: {csrf_token}")

        # Step 2: Perform login with extracted CSRF token
        login_data = {
            '_csrf_token': csrf_token,
            '_username': 'anup',  # Replace with actual username
            '_password': 'Password@123'  # Replace with actual password
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Locust/1.0"
        }

        login_response = self.client.post("/login", data=login_data, headers=headers)

        if login_response.status_code == 200:
            print("Login successful!")
            
            # Save CSRF token & session cookie for future requests
            self.csrf_token = csrf_token
            self.session_cookie = login_response.cookies  # Save session cookies

        else:
            print(f"Login failed! Status code: {login_response.status_code}")

    def extract_csrf_token(self, html):
        """Extract CSRF token from login page HTML."""
        csrf_token_match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
        return csrf_token_match.group(1) if csrf_token_match else None

    @task
    def replay_logs(self):
        """Replay requests based on log entries after login."""
        if self.csrf_token == None:
            print("Skipping replay, missing authentication session!")
            return

        for entry in log_entries:
            method = entry["method"]
            url = entry["url"]
            delay = entry["delay"]

            time.sleep(delay)  # Simulate original request timing

            # Ensure URL is formatted correctly
            url = url.lstrip(":443")

            headers = {
                "X-CSRF-TOKEN": self.csrf_token,
                "Cookie": f"session={self.session_cookie}",
                "User-Agent": "Locust/1.0"
            }

            print(f"Requesting {method} {url}")

            # Send the appropriate request type
            if method == "GET":
                response = self.client.get(url, headers=headers)
            elif method == "POST":
                response = self.client.post(url, headers=headers)
            elif method == "PUT":
                response = self.client.put(url, headers=headers)
            elif method == "DELETE":
                response = self.client.delete(url, headers=headers)

            if response.status_code == 403:
                print(f"403 Forbidden: {url}")
            elif response.status_code == 200:
                print(f"Success: {url}")
            else:
                print(f"Unexpected {response.status_code} for {url}")

