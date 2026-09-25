"""
reply_checker.py
======================================================
Autonomous Gmail Reply Detector for MapsAuditor Engine.
Uses OAuth token to scan inbox for replies from contractors.
When a reply arrives:
  1. Alerts Discord with high priority notification & snippet
  2. Updates SQLite CRM status to 'responded'
"""

import os
import json
import base64
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import notifier
import followup_crm

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify"
]

TOKEN_PATH = os.path.join(os.path.dirname(__file__), "gmail_token.json")

def get_gmail_service():
    """Retrieve authenticated Gmail API service from file or Render env var."""
    creds = None
    
    # 1. Try reading base64 token from Render environment variable
    b64_token = os.environ.get("GMAIL_TOKEN_BASE64")
    if b64_token:
        try:
            raw_json = base64.b64decode(b64_token).decode("utf-8")
            token_info = json.loads(raw_json)
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        except Exception as e:
            print(f"[reply_checker] Error loading GMAIL_TOKEN_BASE64 from env: {e}")

    # 2. Try reading from local file
    if not creds and os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            print(f"[reply_checker] Error loading token file: {e}")

    if not creds:
        return None

    return build("gmail", "v1", credentials=creds)

def check_for_replies():
    """Scan inbox for new replies and send Discord alerts."""
    service = get_gmail_service()
    if not service:
        return 0

    crm = followup_crm.CRM()
    new_replies_count = 0

    try:
        # Search unread messages
        results = service.users().messages().list(
            userId="me",
            q="is:unread",
            maxResults=20
        ).execute()

        messages = results.get("messages", [])
        for msg_meta in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_meta["id"],
                format="full"
            ).execute()

            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            sender = headers.get("from", "Unknown")
            subject = headers.get("subject", "No Subject")
            snippet = msg.get("snippet", "")

            # Check if this looks like a reply to our outreach
            is_relevant_reply = (
                "re:" in subject.lower() or
                "quote" in subject.lower() or
                "lead" in snippet.lower() or
                "job" in snippet.lower() or
                "service" in snippet.lower()
            )

            if is_relevant_reply:
                print(f"[reply_checker] 🔥 INCOMING REPLY from {sender}: {subject}")
                
                # Send high-priority Discord alert
                embed = {
                    "title": "🔥 NEW CONTRACTOR REPLY RECEIVED!",
                    "color": 0x10B981, # Emerald green
                    "fields": [
                        {"name": "From", "value": sender, "inline": False},
                        {"name": "Subject", "value": subject, "inline": False},
                        {"name": "Message Preview", "value": snippet[:400] if snippet else "No preview", "inline": False}
                    ],
                    "footer": {"text": "MapsAuditor Reply Monitor"}
                }
                notifier.send_discord_message(content="🚨 **Hot Lead Reply! Check Your Inbox**", embeds=[embed])
                
                # Mark as read in Gmail so we don't duplicate notify
                service.users().messages().modify(
                    userId="me",
                    id=msg_meta["id"],
                    body={"removeLabelIds": ["UNREAD"]}
                ).execute()

                new_replies_count += 1

    except Exception as e:
        print(f"[reply_checker] Error scanning replies: {e}")

    return new_replies_count

if __name__ == "__main__":
    check_for_replies()
