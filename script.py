import time
import re
from locust import HttpUser, task, between

# Load and parse log file
# log_file_path = "/mnt/data/031920489000_elasticloadbalancing_us-east-1_app.ICPC-ALB.aab6371aff4cced4_20241116T0115Z_34.237.178.197_2mo6sbj7.log"
log_file_path = "031920489000_elasticloadbalancing_us-east-1_app.ICPC-ALB.aab6371aff4cced4_20241116T0000Z_34.237.178.197_5831r81y.log"

def parse_log_file(log_file_path):
    log_data = []
    timestamp_pattern = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)"
    # Updated regex to capture the full URL including potential ports in the path
    request_pattern = r'"(GET|POST|PUT|DELETE) (https?://[^\s]+) (HTTP/[\d\.]+)"'

    with open(log_file_path, "r") as file:
        for line in file:
            timestamp_match = re.search(timestamp_pattern, line)
            request_match = re.search(request_pattern, line)
            
            if timestamp_match and request_match:
                timestamp = timestamp_match.group(1)
                method = request_match.group(1)
                url = request_match.group(2)
                print(url)  # This will print the extracted URL for verification

                log_data.append({"timestamp": timestamp, "method": method, "url": url})

    return log_data


log_entries = parse_log_file(log_file_path)

# Convert timestamps to replay in real-time
base_time = None
for entry in log_entries:
    entry["timestamp"] = time.strptime(entry["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ")
    if base_time is None:
        base_time = entry["timestamp"]
    entry["delay"] = time.mktime(entry["timestamp"]) - time.mktime(base_time)  # Delay from first request
print(log_entries)

# Locust User Behavior
class AuthenticatedUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Login before running any tests"""
        self.login()

    def login(self):
        """Perform login and save cookies/session"""
        # First, send a GET request to fetch the login page and extract the CSRF token
        response = self.client.get("/login")
        
        # Print out the response text to help with debugging
        # print("Login page response:")
        # print(response.text[:1000])  # Only print first 1000 characters for readability

        # Extract the CSRF token from the page
        csrf_token = self.extract_csrf_token(response.text)
        
        if csrf_token:
            print("CSRF token extracted successfully!")
        else:
            print("Failed to extract CSRF token.")
            return  # If no CSRF token found, stop the login process

        # Prepare login data with CSRF token, username, and password
        login_data = {
            '_csrf_token': csrf_token,  # CSRF token
            '_username': 'admin',  # Replace with actual username
            '_password': '2DcI3qf6orXMm422'  # Replace with actual password
        }

        # Send the login request with the CSRF token and credentials
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",  # Make sure this is correct
            "User-Agent": "Locust/1.0"
        }

        response = self.client.post("/login", data=login_data, headers=headers)

        # Log the response for debugging
        print(f"Login response code: {response.status_code}")

        # Check if login was successful, based on response
        if response.status_code == 200 and "Welcome" in response.text:  # Adjust success condition based on your app    
            print("Logged in successfully!")
        else:
            print("Login failed!")
            print(f"Error details: {response.text}")

    def extract_csrf_token(self, html):
        """Extract the CSRF token from the login page HTML"""
        csrf_token_match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
        
        if csrf_token_match:
            return csrf_token_match.group(1)
        else:
            return None


    @task
    def replay_logs(self):
        """Replay requests based on log entries after login"""
        for entry in log_entries:
            method = entry["method"]
            url = entry["url"]
            delay = entry["delay"]

            time.sleep(delay)  # Simulate original request timing

            # Check for the method type and make the corresponding request
            if method == "GET":
                self.client.get(url)
            elif method == "POST":
                self.client.post(url)
            elif method == "PUT":
                self.client.put(url)
            elif method == "DELETE":
                self.client.delete(url)
