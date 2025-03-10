import os
import re
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Time slots in IST with 5-minute intervals
time_intervals = {f"{hour:02d}:{minute:02d} - {hour:02d}:{minute+5:02d}": []
                  for hour in range(24) for minute in range(0, 60, 5)}

def parse_elb_log(line):
    log_pattern = re.compile(
        r'(?P<protocol>\S+) (?P<timestamp>\S+) (?P<elb>\S+) '
        r'(?P<client_ip>\d+\.\d+\.\d+\.\d+):(?P<client_port>\d+) '
        r'(?P<target_ip>\d+\.\d+\.\d+\.\d+):(?P<target_port>\d+) '
        r'(?P<request_time>[\d\.]+) (?P<target_time>[\d\.]+) (?P<response_time>[\d\.]+) '
        r'(?P<http_status>\d+) (?P<elb_status>\d+) (?P<sent_bytes>\d+) (?P<received_bytes>\d+) '
        r'"(?P<request>[^"]+)"'
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

def convert_utc_to_ist(utc_time):
    return utc_time + timedelta(hours=5, minutes=30)

def get_time_interval(ist_time):
    hour, minute = ist_time.hour, ist_time.minute
    start_minute = (minute // 5) * 5
    end_minute = start_minute + 5
    return f"{hour:02d}:{start_minute:02d} - {hour:02d}:{end_minute:02d}"

def process_logs(log_dir):
    if not os.path.exists(log_dir):
        logging.error(f"Log directory '{log_dir}' does not exist.")
        return None
    
    log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
    interval_data = defaultdict(lambda: {"target_avg_time": [], "response_avg_time": [], "url_list": defaultdict(lambda: {"count": 0, "status_codes": defaultdict(int)})})
    
    for file in log_files:
        try:
            with open(os.path.join(log_dir, file), "r") as f:
                for line in f:
                    log_data = parse_elb_log(line.strip())
                    if log_data:
                        utc_time = datetime.strptime(log_data["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ")
                        ist_time = convert_utc_to_ist(utc_time)
                        time_slot = get_time_interval(ist_time)
                        interval_data[time_slot]["target_avg_time"].append(float(log_data["target_time"]))
                        interval_data[time_slot]["response_avg_time"].append(float(log_data["response_time"]))
                        url_entry = interval_data[time_slot]["url_list"][log_data["url"]]
                        url_entry["count"] += 1
                        url_entry["status_codes"][log_data["http_status"]] += 1
        except Exception as e:
            logging.error(f"Error reading file {file}: {e}")
    
    final_output = {}
    for slot, data in interval_data.items():
        final_output[slot] = {
            "target_avg_time": sum(data["target_avg_time"]) / len(data["target_avg_time"]) if data["target_avg_time"] else 0,
            "response_avg_time": sum(data["response_avg_time"]) / len(data["response_avg_time"]) if data["response_avg_time"] else 0,
            "url_list": {url: {"count": entry["count"], "status_codes": dict(entry["status_codes"])} for url, entry in data["url_list"].items()}
        }
    
    with open("processed_logs_IST.json", "w") as json_file:
        json.dump(final_output, json_file, indent=4)
    
    return "processed_logs_IST.json"

if __name__ == "__main__":
    log_directory = "elb-logs"
    output_file = process_logs(log_directory)
    if output_file:
        logging.info(f"Logs saved to {output_file}")
    else:    
        logging.error("Error processing logs")
