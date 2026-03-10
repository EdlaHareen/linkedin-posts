"""
One-time script to generate Gmail OAuth 2.0 tokens.

Run this script after creating OAuth 2.0 Desktop credentials in Google Cloud Console.
It will open a browser for you to authorize access, then save the token for the app.

Usage:
    python scripts/get_gmail_token.py
"""

import os
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# File paths
PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / 'config' / 'oauth-credentials.json'
TOKEN_FILE = PROJECT_ROOT / 'config' / 'gmail-token.json'


def main():
    """Run OAuth 2.0 flow and save tokens."""
    
    if not CREDENTIALS_FILE.exists():
        print(f"\n❌ OAuth credentials file not found at: {CREDENTIALS_FILE}")
        print("\nTo create one:")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Click '+ CREATE CREDENTIALS' → 'OAuth client ID'")
        print("3. Application type: 'Desktop app'")
        print("4. Name: 'LinkedIn Posts Automation'")
        print("5. Download the JSON and save it as:")
        print(f"   {CREDENTIALS_FILE}")
        sys.exit(1)
    
    creds = None
    
    # Check if token already exists
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    # If no valid credentials, run the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("🌐 Opening browser for Gmail authorization...")
            print("   Please sign in with: edlahareen01@gmail.com\n")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=8090)
    
    # Save the token
    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())
    
    print(f"\n✅ Token saved to: {TOKEN_FILE}")
    print(f"   Access Token: {creds.token[:20]}...")
    print(f"   Refresh Token: {'Yes' if creds.refresh_token else 'No'}")
    print(f"   Expiry: {creds.expiry}")
    print("\n🎉 Gmail OAuth setup complete! Your app can now access Gmail.")


if __name__ == '__main__':
    main()
