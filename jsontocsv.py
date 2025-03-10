import os
import re
import json
import csv
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Function to convert JSON to CSV with separate columns for status codes
def json_to_csv(json_file, csv_file):
    with open(json_file, "r") as f:
        data = json.load(f)
    
    csv_data = []
    status_code_headers = set()
    
    # First pass to gather all possible status codes
    for values in data.values():
        for url_data in values["url_list"].values():
            status_code_headers.update(url_data["status_codes"].keys())
    
    status_code_headers = sorted(status_code_headers, key=int)  # Sort numerically
    
    # Prepare CSV rows
    for time_slot, values in data.items():
        target_avg_time = values["target_avg_time"]
        response_avg_time = values["response_avg_time"]
        for url, url_data in values["url_list"].items():
            request_count = url_data["count"]
            row = [time_slot, url, request_count, target_avg_time, response_avg_time]
            
            # Add status code counts dynamically
            for code in status_code_headers:
                row.append(url_data["status_codes"].get(code, 0))
            
            csv_data.append(row)
    
    # Write to CSV
    with open(csv_file, "w", newline='') as f:
        writer = csv.writer(f)
        headers = ["Time Slot", "URL", "Request Count", "Target Avg Time", "Response Avg Time"] + [f"Status {code}" for code in status_code_headers]
        writer.writerow(headers)
        writer.writerows(csv_data)
    
    logging.info(f"CSV file saved to {csv_file}")
    return csv_file

if __name__ == "__main__":
    json_file = "processed_logs_IST.json"
    csv_file = "processed_logs_IST.csv"
    json_to_csv(json_file, csv_file)
