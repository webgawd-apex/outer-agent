"""
notifier.py
======================================================
Discord Webhook Notifier for MapsAuditor Autonomous Agent.
Sends real-time alerts for:
  - Form submissions & direct emails sent
  - CAPTCHAs encountered (with page screenshot)
  - Daily limit milestones (e.g. 200/day reached)
  - Critical errors or replies
"""

import os
import json
import requests
import datetime

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[notifier] Error reading settings.json: {e}")
    return {}

def send_discord_message(content: str = None, embeds: list = None, file_path: str = None):
    """Send message or embed to Discord webhook configured in settings.json."""
    settings = load_settings()
    webhook_url = settings.get("notifications", {}).get("discord_webhook_url", "")
    
    if not webhook_url or "YOUR_DISCORD_WEBHOOK_URL" in webhook_url or not webhook_url.startswith("https://discord.com/api/webhooks/"):
        # Not configured or placeholder
        print(f"[notifier] Discord notification skipped (no valid webhook URL set)")
        return False

    payload = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds

    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "image/png")}
                data = {"payload_json": json.dumps(payload)} if payload else {}
                r = requests.post(webhook_url, data=data, files=files, timeout=10)
        else:
            r = requests.post(webhook_url, json=payload, timeout=10)
            
        return r.status_code in [200, 204]
    except Exception as e:
        print(f"[notifier] Failed to send Discord webhook: {e}")
        return False

def notify_form_submitted(business_name: str, website: str, niche: str, city: str, count_today: int, max_limit: int):
    settings = load_settings()
    if not settings.get("notifications", {}).get("notify_on_form_submit", True):
        return

    embed = {
        "title": f"✅ Contact Form Submitted ({count_today}/{max_limit})",
        "color": 0x22C55E, # Green
        "fields": [
            {"name": "Business", "value": business_name or "Unknown", "inline": True},
            {"name": "Niche / City", "value": f"{niche} • {city}", "inline": True},
            {"name": "Website", "value": website or "N/A", "inline": False},
        ],
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "footer": {"text": "MapsAuditor Autonomous Engine"}
    }
    send_discord_message(embeds=[embed])

def notify_email_sent(business_name: str, to_email: str, niche: str, city: str, count_today: int, max_limit: int):
    settings = load_settings()
    if not settings.get("notifications", {}).get("notify_on_email_sent", True):
        return

    embed = {
        "title": f"📧 Direct Email Sent ({count_today}/{max_limit})",
        "color": 0x3B82F6, # Blue
        "fields": [
            {"name": "Business", "value": business_name or "Unknown", "inline": True},
            {"name": "Recipient Email", "value": to_email, "inline": True},
            {"name": "Niche / City", "value": f"{niche} • {city}", "inline": True},
        ],
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "footer": {"text": "MapsAuditor Autonomous Engine"}
    }
    send_discord_message(embeds=[embed])

def notify_captcha_detected(business_name: str, url: str, screenshot_path: str = None):
    settings = load_settings()
    if not settings.get("notifications", {}).get("notify_on_captcha", True):
        return

    embed = {
        "title": "⚠️ CAPTCHA Detected — Manual Action Required",
        "description": f"Encountered a CAPTCHA while trying to submit form for **{business_name}**.",
        "color": 0xF59E0B, # Amber
        "fields": [
            {"name": "URL", "value": url, "inline": False},
        ],
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "footer": {"text": "MapsAuditor Autonomous Engine"}
    }
    send_discord_message(embeds=[embed], file_path=screenshot_path)

def notify_daily_limit_reached(count: int, limit: int):
    embed = {
        "title": "🛑 Daily Limit Reached",
        "description": f"Successfully completed **{count}/{limit}** outreach actions today (forms + emails). Engine is now pausing to protect sending limits.",
        "color": 0xEF4444, # Red
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "footer": {"text": "MapsAuditor Autonomous Engine"}
    }
    send_discord_message(embeds=[embed])

def notify_error(business_name: str, error_msg: str):
    settings = load_settings()
    if not settings.get("notifications", {}).get("notify_on_error", True):
        return

    embed = {
        "title": "❌ Pipeline Error",
        "color": 0xEF4444,
        "fields": [
            {"name": "Target", "value": business_name or "N/A", "inline": True},
            {"name": "Error Details", "value": str(error_msg)[:1000], "inline": False}
        ],
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "footer": {"text": "MapsAuditor Autonomous Engine"}
    }
    send_discord_message(embeds=[embed])
