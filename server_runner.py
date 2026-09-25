"""
server_runner.py
======================================================
Server Entry Point for Cloud Deployments (Render / Railway / VPS / Docker).
Features:
  - Exposes /health endpoint for UptimeRobot to keep server alive 24/7
  - Exposes /status endpoint for live pipeline stats
  - Spawns background thread for the autonomous Google Maps outreach crawler
  - Automatically resets daily 200-limit counters and handles daily scheduling
"""

import os
import time
import threading
import datetime
from flask import Flask, jsonify
from flask_cors import CORS

import autonomous_agent
import followup_crm
import notifier

import reply_checker

app = Flask(__name__)
CORS(app)

crawler_thread = None
crawler_running = False

def background_reply_checker_loop():
    """Checks for new Gmail replies every 10 minutes and sends Discord alerts."""
    print("[server] Starting background Gmail reply monitor...")
    while True:
        try:
            reply_checker.check_for_replies()
        except Exception as e:
            print(f"[server] Reply checker error: {e}")
        time.sleep(600)

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "MapsAuditor Autonomous Outreach Engine",
        "status": "online",
        "time_utc": datetime.datetime.utcnow().isoformat()
    })

@app.route("/health", methods=["GET"])
def health():
    """UptimeRobot ping endpoint to prevent server from sleeping."""
    return jsonify({
        "status": "healthy",
        "today_outreach_count": autonomous_agent.get_today_action_count(),
        "timestamp": datetime.datetime.utcnow().isoformat()
    }), 200

@app.route("/status", methods=["GET"])
def status():
    """Returns current CRM and daily outreach statistics."""
    crm = followup_crm.CRM()
    stats = {
        "today_actions": autonomous_agent.get_today_action_count(),
        "daily_limit": 200,
        "pipeline_summary": followup_crm.get_pipeline_summary()
    }
    return jsonify(stats), 200

@app.route("/trigger", methods=["POST"])
def trigger():
    """Manually trigger or restart the autonomous run."""
    global crawler_thread, crawler_running
    if crawler_running:
        return jsonify({"status": "already_running"}), 400

    crawler_thread = threading.Thread(target=background_crawler_loop, daemon=True)
    crawler_thread.start()
    return jsonify({"status": "started"}), 200

def background_crawler_loop():
    """Continuous worker that runs the autonomous pipeline in headless mode."""
    global crawler_running
    crawler_running = True
    print("[server] Starting autonomous Google Maps outreach loop in headless mode...")
    
    while True:
        try:
            today_count = autonomous_agent.get_today_action_count()
            if today_count < 200:
                print(f"[server] Running outreach batch (current: {today_count}/200)...")
                autonomous_agent.run_maps_autonomous(headless=True)
            else:
                print(f"[server] Daily cap of 200 reached today. Waiting for next cycle...")

            # Sleep 1 hour between batches or until next cycle
            time.sleep(3600)

        except Exception as e:
            print(f"[server] Error in crawler loop: {e}")
            notifier.notify_error("Server Loop", str(e))
            time.sleep(300)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    
    # Start the autonomous crawler daemon
    crawler_thread = threading.Thread(target=background_crawler_loop, daemon=True)
    crawler_thread.start()

    # Start the reply monitor daemon
    reply_thread = threading.Thread(target=background_reply_checker_loop, daemon=True)
    reply_thread.start()
    
    # Start the web server
    print(f"[server] MapsAuditor Engine listening on port {port}")
    app.run(host="0.0.0.0", port=port)
