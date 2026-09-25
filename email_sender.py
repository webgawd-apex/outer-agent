"""
email_sender.py
======================================================
Sends outreach emails via Gmail SMTP or SendGrid.
Loads configuration dynamically from settings.json.
Logs every send to SQLite CRM.
"""

import os
import smtplib
import json
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.request
import urllib.error

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[email_sender] Error loading settings.json: {e}")
    return {}

def send_via_gmail_smtp(to_email: str, subject: str, body_text: str, sender_name: str, gmail_user: str, app_password: str) -> bool:
    """Send an email using standard Gmail SMTP with an App Password."""
    if not gmail_user or not app_password or "YOUR_GMAIL" in app_password:
        print("[email_sender] ERROR: Gmail user/app password not configured in settings.json")
        return False
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{gmail_user}>" if sender_name else gmail_user
        msg["To"] = to_email
        
        # Attach plain text version
        part = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part)
        
        # Connect to Gmail SMTP SSL (port 465)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(gmail_user, app_password)
            server.sendmail(gmail_user, [to_email], msg.as_string())
            
        print(f"[email_sender] Successfully sent email to {to_email} via Gmail SMTP")
        return True
    except Exception as e:
        print(f"[email_sender] Gmail SMTP send failed to {to_email}: {e}")
        return False

def send_via_sendgrid(to_email: str, subject: str, body_text: str, from_email: str, from_name: str, api_key: str) -> bool:
    """Send an email using SendGrid API."""
    if not api_key or "YOUR_SENDGRID" in api_key:
        print("[email_sender] ERROR: SendGrid API key not configured")
        return False
        
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body_text}]
    }
    
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 202)
    except Exception as e:
        print(f"[email_sender] SendGrid send failed to {to_email}: {e}")
        return False

def send_outreach_email(lead: dict) -> bool:
    """
    Main dispatch function: selects Gmail or SendGrid based on settings.json,
    constructs the outreach message, sends it, and logs to CRM.
    """
    settings = load_settings()
    to_email = lead.get("email") or lead.get("contact_email")
    if not to_email:
        print(f"[email_sender] No recipient email for lead: {lead.get('name')}")
        return False

    sender_name = settings.get("sender", {}).get("name", "Daniel Joshua")
    subject = settings.get("form_fields", {}).get("subject_field_value", "Quick question about your old leads")
    message = settings.get("outreach_message", "Hi! Quick question, do you ever go back through old quotes or leads that never closed? I help contractors turn those into new jobs. It's free to look into, and I only get paid if it works. Happy to explain more if useful.")
    
    # Personalize greeting if business name available
    biz_name = lead.get("name", "").strip()
    if biz_name:
        full_body = f"Hi {biz_name},\n\n{message}\n\nBest,\n{sender_name}"
    else:
        full_body = f"Hi,\n\n{message}\n\nBest,\n{sender_name}"

    provider = settings.get("email_provider", "gmail").lower()
    success = False

    if provider == "gmail":
        gmail_cfg = settings.get("gmail", {})
        gmail_user = gmail_cfg.get("email") or settings.get("sender", {}).get("email")
        app_pass = gmail_cfg.get("app_password")
        success = send_via_gmail_smtp(to_email, subject, full_body, sender_name, gmail_user, app_pass)
    else:
        sg_cfg = settings.get("sendgrid", {})
        api_key = sg_cfg.get("api_key")
        from_email = sg_cfg.get("from_email") or settings.get("sender", {}).get("email")
        from_name = sg_cfg.get("from_name") or sender_name
        success = send_via_sendgrid(to_email, subject, full_body, from_email, from_name, api_key)

    if success:
        # Update CRM if available
        try:
            import followup_crm
            crm = followup_crm.CRM()
            crm.record_outreach(lead.get("id", 0), "email", {"to": to_email, "subject": subject})
            crm.update_lead_status(lead.get("id", 0), "emailed")
        except Exception:
            pass

    return success
