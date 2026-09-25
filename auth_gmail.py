"""
auth_gmail.py
======================================================
1-Click Google OAuth Authorization for MapsAuditor.
Authenticates your Gmail account via browser popup (just like Claude / MCP).
Saves a persistent token to 'gmail_token.json' and outputs the token 
string for Render environment variables.
"""

import os
import json
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Scopes needed to read incoming replies and send direct outreach emails
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify"
]

TOKEN_PATH = os.path.join(os.path.dirname(__file__), "gmail_token.json")
CLIENT_SECRET_PATH = os.path.join(os.path.dirname(__file__), "client_secret.json")

def authenticate():
    creds = None
    
    # Check if existing token exists
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception:
            creds = None

    # If no valid token, launch browser login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[OAuth] Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("\n" + "="*60)
            print("  GOOGLE GMAIL OAUTH LOGIN")
            print(" A browser window will open. Sign in and click 'Allow'.")
            print("="*60 + "\n")
            
            if not os.path.exists(CLIENT_SECRET_PATH):
                # Built-in OAuth Client configuration
                client_config = {
                    "installed": {
                        "client_id": os.environ.get("GOOGLE_CLIENT_ID", "YOUR_CLIENT_ID.apps.googleusercontent.com"),
                        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET"),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": ["http://localhost:8080/"]
                    }
                }
                with open(CLIENT_SECRET_PATH, "w", encoding="utf-8") as f:
                    json.dump(client_config, f, indent=2)

            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=8080, prompt="consent")

        # Save the credentials for the local engine
        with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

        print(f"\n[OK] Authorization Successful! Token saved to: {TOKEN_PATH}")

        # Provide encoded token for Render environment variable
        token_str = creds.to_json()
        encoded_token = base64.b64encode(token_str.encode("utf-8")).decode("utf-8")
        
        print("\n" + "-"*60)
        print("FOR RENDER DEPLOYMENT:")
        print("Set this in Render -> Environment Variables tab:")
        print("Key:   GMAIL_TOKEN_BASE64")
        print(f"Value: {encoded_token}")
        print("-"*60 + "\n")

    return creds

if __name__ == "__main__":
    authenticate()
