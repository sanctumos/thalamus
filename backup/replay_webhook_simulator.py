import json
import time
import datetime
import requests
from requests.exceptions import ConnectionError

LOG_FILE = "raw_data_log.json"
WEBHOOK_URL = "http://64.94.85.112:5000/omi?uid=simulated"  # Production webhook endpoint

def replay_webhook(webhook_url=WEBHOOK_URL, log_file=LOG_FILE):
    # Read and parse log file
    with open(log_file, "r") as f:
        lines = f.readlines()
    
    events = []
    for line in lines:
        try:
            event = json.loads(line)
            events.append(event)
        except Exception as e:
            print(f"💥 Failed to parse line: {e}")
    
    if not events:
        print("💥 No events to replay.")
        return events

    # Sort events by timestamp
    events.sort(key=lambda x: x.get("log_timestamp", ""))
    
    return events  # Return the sorted events list

def start_replay(events, webhook_url=WEBHOOK_URL, dry_run=False):
    if not events:
        return
        
    # Use the timestamp of the first event as a baseline
    baseline_time = datetime.datetime.fromisoformat(events[0]["log_timestamp"].rstrip("Z"))
    prev_time = baseline_time

    print(f"\n🎬 Starting replay of {len(events)} events...")
    print(f"🎯 Target webhook: {webhook_url}")
    if dry_run:
        print("🌵 DRY RUN - Events will be processed but not sent\n")
    else:
        print("🔥 LIVE RUN - Events will be sent to webhook\n")

    try:
        # Test webhook connection
        if not dry_run:
            requests.get(webhook_url.split("?")[0] + "/ping")
    except ConnectionError:
        print("⚠️  Warning: Webhook server not responding. Switching to dry run mode.")
        dry_run = True

    for i, event in enumerate(events, 1):
        current_time = datetime.datetime.fromisoformat(event["log_timestamp"].rstrip("Z"))
        # Compute delay based on difference from previous event
        delay = (current_time - prev_time).total_seconds()
        if delay > 0:  # Only wait if there's a positive delay
            print(f"⏳ Waiting {delay:.2f}s...")
            time.sleep(delay)
        
        if dry_run:
            print(f"\n🔎 Event {i}/{len(events)} [DRY RUN]")
            print("\n🧠 Would send to webhook:")
            print(json.dumps(event, indent=2))
            print("📡 Status: simulated\n")
        else:
            try:
                response = requests.post(webhook_url, json=event)
                print(f"\n🔎 Event {i}/{len(events)} - POST {webhook_url}")
                print("\n🧠 Thalamus Input [Raw Sensory Stream]:")
                print(json.dumps(event, indent=2))
                print(f"📡 Status: {response.status_code}\n")
            except Exception as e:
                print(f"💥 Failed to send event: {e}")
                print("⚠️  Switching to dry run mode for remaining events.")
                dry_run = True
        
        prev_time = current_time

if __name__ == "__main__":
    events = replay_webhook()
    start_replay(events)
