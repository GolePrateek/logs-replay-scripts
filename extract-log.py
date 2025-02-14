import time
import os
import re
import json
from locust import HttpUser, task, between

log_folder = "elb-logs/"
output_file = "parsed_logs.json"

def parse_log_file(file_path):
    """Parse a single log file and extract request details."""
    log_data = []
    
    # Regex patterns
    timestamp_pattern = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)"
    request_pattern = r'"(GET|POST|PUT|DELETE) https?://[^/]+(:443)?(/[^"]*) (HTTP/[\d\.]+)"'
    
    with open(file_path, "r") as file:
        for line in file:
            timestamp_match = re.search(timestamp_pattern, line)
            request_match = re.search(request_pattern, line)
            
            if timestamp_match and request_match:
                timestamp = timestamp_match.group(1)
                method = request_match.group(1)
                url = request_match.group(3)  # Extract only the path
                
                log_data.append({"timestamp": timestamp, "method": method, "url": url})
    
    return log_data

def parse_all_logs(folder_path):
    """Parse all log files in the given folder."""
    all_logs = []
    
    # Iterate over all files in the folder
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        
        if os.path.isfile(file_path) and filename.endswith(".log"):  # Process only log files
            print(f"Parsing: {filename}")
            log_entries = parse_log_file(file_path)
            all_logs.extend(log_entries)
    
    return all_logs

# Parse all log files
log_entries = parse_all_logs(log_folder)

# Convert timestamps to replay in real-time
base_time = None
for entry in log_entries:
    entry["timestamp"] = time.strptime(entry["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ")
    if base_time is None:
        base_time = entry["timestamp"]
    entry["delay"] = time.mktime(entry["timestamp"]) - time.mktime(base_time)  # Delay from first request

# Convert timestamps back to string format
for entry in log_entries:
    entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", entry["timestamp"])

# Save parsed logs to a JSON file
with open(output_file, "w") as json_file:
    json.dump(log_entries, json_file, indent=4)

print(f"Parsed logs have been saved to {output_file}")
