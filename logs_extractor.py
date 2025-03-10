import os
import re
import json
import logging
from datetime import datetime
from collections import defaultdict
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def parse_elb_log(line):
    log_pattern = re.compile(
        r'(?P<protocol>\S+) (?P<timestamp>\S+) (?P<elb>\S+) '
        r'(?P<client_ip>\d+\.\d+\.\d+\.\d+):(?P<client_port>\d+) '
        r'(?P<target_ip>\d+\.\d+\.\d+\.\d+):(?P<target_port>\d+) '
        r'(?P<request_time>[\d\.]+) (?P<target_time>[\d\.]+) (?P<response_time>[\d\.]+) '
        r'(?P<http_status>\d+) (?P<elb_status>\d+) (?P<sent_bytes>\d+) (?P<received_bytes>\d+) '
        r'"(?P<request>[^"]+)" "(?P<user_agent>[^"]*)" '
        r'(?P<ssl_cipher>\S+) (?P<ssl_protocol>\S+)'
    )
    
    match = log_pattern.match(line)
    if match:
        data = match.groupdict()
        request_parts = data["request"].split(" ")
        data["method"] = request_parts[0] if len(request_parts) > 1 else ""
        parsed_url = urlparse(request_parts[1]) if len(request_parts) > 1 else ""
        data["url"] = parsed_url.path.rstrip("/")  # Normalize
        data["http_version"] = request_parts[2] if len(request_parts) > 2 else ""
        data["response_time"] = float(data["response_time"])
        data["http_status"] = int(data["http_status"])
        return data
    return None

def get_time_slot(log_time):
    slots = [(18, 0, "18:00-18:15"), (18, 15, "18:15-18:30"), (18, 30, "18:30-18:45"),
             (18, 45, "18:45-19:00"), (19, 0, "19:00-19:15"), (19, 15, "19:15-19:30"),
             (19, 30, "19:30-19:45"), (19, 45, "19:45-20:00"), (20, 0, "20:00-20:15"),
             (20, 15, "20:15-20:30")]
    
    for hour, minute, slot in slots:
        if log_time.hour == hour and log_time.minute < minute + 15:
            return slot
    return None

def process_logs(log_dir):
    if not os.path.exists(log_dir):
        logging.error(f"Log directory '{log_dir}' does not exist.")
        return None
    
    log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
    all_logs = []
    
    for file in log_files:
        try:
            with open(os.path.join(log_dir, file), "r") as f:
                for line in f:
                    log_data = parse_elb_log(line.strip())
                    if log_data:
                        all_logs.append(log_data)
        except Exception as e:
            logging.error(f"Error reading file {file}: {e}")
    
    logging.info(f"Processed {len(all_logs)} log entries")
    
    with open("filtered_logs.json", "w") as json_file:
        json.dump(all_logs, json_file, indent=4)
    
    return "filtered_logs.json"

if __name__ == "__main__":
    log_directory = "elb-logs"
    output_file = process_logs(log_directory)
    if output_file:
        logging.info(f"Logs saved to {output_file}")
    else:    
        logging.error("Error processing logs")