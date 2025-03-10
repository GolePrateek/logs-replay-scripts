import json
import random
import time
from datetime import datetime, timedelta
from collections import defaultdict

from locust import HttpUser, task, between, LoadTestShape

###############################################################################
# STEP 1: LOAD JSON FILE WITH TRAFFIC PATTERN
###############################################################################

# Load JSON file
JSON_FILE = "traffic_pattern.json"

with open(JSON_FILE, "r") as f:
    TRAFFIC_DATA = json.load(f)

# Convert time intervals into a dictionary (ignore timestamps, use as buckets)
time_buckets = {}

for time_slot, data in TRAFFIC_DATA.items():
    start_time, _ = time_slot.split(" - ")
    
    try:
        # Convert time to HH:MM format
        start_dt = datetime.strptime(start_time, "%H:%M").strftime("%H:%M")
        time_buckets[start_dt] = data  # Store request data
    except Exception as e:
        print(f"Skipping invalid time interval {time_slot}: {e}")

###############################################################################
# STEP 2: CUSTOM LOAD SHAPE - ADJUST USERS PER 5-MIN INTERVAL
###############################################################################

class CustomLoadShape(LoadTestShape):
    """
    Dynamically sets users based on current time in a 5-minute interval.
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

        # Get request volume from this time bucket
        bucket_data = time_buckets.get(current_bucket, {})
        total_requests = sum(url_data["count"] for url_data in bucket_data.get("url_list", {}).values())

        # Define user count based on request volume
        target_users = max(total_requests // 10, 1)  # Scaling factor

        # Define spawn rate (how fast users are added)
        spawn_rate = max(target_users // 10, 1)

        return (target_users, spawn_rate)


###############################################################################
# STEP 3: DEFINE LOCUST USER BEHAVIOR
###############################################################################

class WebsiteUser(HttpUser):
    """
    Simulates user requests dynamically based on the current 5-minute bucket.
    """
    wait_time = between(1, 3)  # Random wait time

    def on_start(self):
        """
        Store test start time when Locust starts execution.
        """
        self.start_time = time.time()

    @task
    def send_request(self):
        """
        Picks a request from the current 5-minute bucket and executes it.
        """
        elapsed = time.time() - self.start_time  # Use manually tracked start time
        current_time = datetime.now().strftime("%H:%M")

        # Find the active bucket
        current_bucket = None
        for bucket_time in sorted(time_buckets.keys()):
            bucket_hour, bucket_minute = map(int, bucket_time.split(":"))
            if datetime.now().hour == bucket_hour and datetime.now().minute >= bucket_minute:
                current_bucket = bucket_time

        if not current_bucket:
            return  # No valid bucket found

        # Get request distribution for this time bucket
        bucket_data = time_buckets.get(current_bucket, {}).get("url_list", {})

        # Build a weighted request list
        request_choices = []
        for url, url_data in bucket_data.items():
            request_choices.extend([url] * url_data["count"])

        if not request_choices:
            return  # No URLs to request

        # Pick a URL based on frequency
        url_to_request = random.choice(request_choices)
        self.client.get(url_to_request)


###############################################################################
# STEP 4: RUN LOCUST WITH THIS CONFIGURATION
###############################################################################

# """
# How to run:
# 1. Save this script as `locustfile.py`
# 2. Ensure `traffic_pattern.json` is in the same directory
# 3. Run: `locust -f locustfile.py`
# 4. Open `http://localhost:8089` in your browser to start the test.
# """
