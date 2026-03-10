"""
Set up Gmail Pub/Sub watch for real-time email notifications.

This script:
1. Creates a Pub/Sub topic (if it doesn't exist)
2. Grants Gmail publish permissions on the topic
3. Creates a push subscription pointing to your webhook URL
4. Calls Gmail users.watch() to start receiving notifications

Usage:
    python scripts/setup_gmail_watch.py <NGROK_URL>
    
Example:
    python scripts/setup_gmail_watch.py https://abc123.ngrok-free.dev
"""

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Paths
TOKEN_FILE = PROJECT_ROOT / 'config' / 'gmail-token.json'
SA_CREDENTIALS = PROJECT_ROOT / 'config' / 'n8nproject-473914-a2077b5636e0.json'

# Config
PROJECT_ID = 'n8nproject-473914'
TOPIC_NAME = 'gmail-newsletter-notifications'
SUBSCRIPTION_NAME = 'gmail-newsletter-push'
FULL_TOPIC = f'projects/{PROJECT_ID}/topics/{TOPIC_NAME}'


def get_gmail_service():
    """Get Gmail API service using OAuth token."""
    if not TOKEN_FILE.exists():
        print("❌ Gmail token not found. Run: python scripts/get_gmail_token.py")
        sys.exit(1)
    
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)


def get_pubsub_service():
    """Get Pub/Sub API service using service account."""
    if not SA_CREDENTIALS.exists():
        print(f"❌ Service account credentials not found: {SA_CREDENTIALS}")
        sys.exit(1)
    
    creds = service_account.Credentials.from_service_account_file(
        str(SA_CREDENTIALS),
        scopes=['https://www.googleapis.com/auth/pubsub']
    )
    return build('pubsub', 'v1', credentials=creds)


def setup_topic(pubsub):
    """Create Pub/Sub topic if it doesn't exist."""
    try:
        pubsub.projects().topics().get(topic=FULL_TOPIC).execute()
        print(f"✅ Topic already exists: {FULL_TOPIC}")
    except Exception:
        try:
            pubsub.projects().topics().create(
                name=FULL_TOPIC, body={}
            ).execute()
            print(f"✅ Created topic: {FULL_TOPIC}")
        except Exception as e:
            print(f"❌ Failed to create topic: {e}")
            sys.exit(1)


def grant_gmail_publish_permission(pubsub):
    """Grant Gmail API permission to publish to the topic."""
    try:
        policy = pubsub.projects().topics().getIamPolicy(
            resource=FULL_TOPIC
        ).execute()
        
        gmail_binding = {
            'role': 'roles/pubsub.publisher',
            'members': ['serviceAccount:gmail-api-push@system.gserviceaccount.com']
        }
        
        bindings = policy.get('bindings', [])
        
        # Check if already granted
        for b in bindings:
            if b['role'] == 'roles/pubsub.publisher':
                if 'serviceAccount:gmail-api-push@system.gserviceaccount.com' in b.get('members', []):
                    print("✅ Gmail publish permission already granted")
                    return
                b['members'].append('serviceAccount:gmail-api-push@system.gserviceaccount.com')
                policy['bindings'] = bindings
                pubsub.projects().topics().setIamPolicy(
                    resource=FULL_TOPIC,
                    body={'policy': policy}
                ).execute()
                print("✅ Gmail publish permission granted")
                return
        
        bindings.append(gmail_binding)
        policy['bindings'] = bindings
        pubsub.projects().topics().setIamPolicy(
            resource=FULL_TOPIC,
            body={'policy': policy}
        ).execute()
        print("✅ Gmail publish permission granted")
        
    except Exception as e:
        print(f"❌ Failed to set IAM policy: {e}")
        sys.exit(1)


def setup_subscription(pubsub, webhook_url):
    """Create a push subscription pointing to the webhook URL."""
    full_sub = f'projects/{PROJECT_ID}/subscriptions/{SUBSCRIPTION_NAME}'
    webhook_secret = os.getenv('WEBHOOK_SECRET_TOKEN', '')
    
    push_endpoint = f"{webhook_url}/webhook/gmail"
    
    try:
        # Try to get existing subscription
        existing = pubsub.projects().subscriptions().get(
            subscription=full_sub
        ).execute()
        
        # Update push config if URL changed
        current_url = existing.get('pushConfig', {}).get('pushEndpoint', '')
        if current_url != push_endpoint:
            pubsub.projects().subscriptions().modifyPushConfig(
                subscription=full_sub,
                body={
                    'pushConfig': {
                        'pushEndpoint': push_endpoint,
                        'attributes': {
                            'x-goog-channel-token': webhook_secret
                        }
                    }
                }
            ).execute()
            print(f"✅ Updated subscription push URL: {push_endpoint}")
        else:
            print(f"✅ Subscription already configured: {push_endpoint}")
        
    except Exception:
        try:
            pubsub.projects().subscriptions().create(
                name=full_sub,
                body={
                    'topic': FULL_TOPIC,
                    'pushConfig': {
                        'pushEndpoint': push_endpoint,
                        'attributes': {
                            'x-goog-channel-token': webhook_secret
                        }
                    },
                    'ackDeadlineSeconds': 60,
                    'expirationPolicy': {
                        'ttl': '2678400s'  # 31 days
                    }
                }
            ).execute()
            print(f"✅ Created push subscription: {push_endpoint}")
        except Exception as e:
            print(f"❌ Failed to create subscription: {e}")
            sys.exit(1)


def setup_gmail_watch(gmail):
    """Call Gmail users.watch() to start receiving notifications."""
    try:
        result = gmail.users().watch(
            userId='me',
            body={
                'topicName': FULL_TOPIC,
                'labelIds': ['INBOX']
            }
        ).execute()
        
        history_id = result.get('historyId')
        expiration = result.get('expiration')
        
        print(f"✅ Gmail watch activated!")
        print(f"   History ID: {history_id}")
        print(f"   Expiration: {expiration}")
        print(f"   (Watch expires after ~7 days — run this script again to renew)")
        
    except Exception as e:
        print(f"❌ Failed to set up Gmail watch: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/setup_gmail_watch.py <NGROK_URL>")
        print("Example: python scripts/setup_gmail_watch.py https://abc123.ngrok-free.dev")
        sys.exit(1)
    
    ngrok_url = sys.argv[1].rstrip('/')
    
    print(f"\n🔧 Setting up Gmail Pub/Sub watch")
    print(f"   Project: {PROJECT_ID}")
    print(f"   Topic: {FULL_TOPIC}")
    print(f"   Webhook: {ngrok_url}/webhook/gmail\n")
    
    # Enable Pub/Sub API might be needed
    print("--- Step 1: Pub/Sub Topic ---")
    pubsub = get_pubsub_service()
    setup_topic(pubsub)
    
    print("\n--- Step 2: Gmail Publish Permission ---")
    grant_gmail_publish_permission(pubsub)
    
    print("\n--- Step 3: Push Subscription ---")
    setup_subscription(pubsub, ngrok_url)
    
    print("\n--- Step 4: Gmail Watch ---")
    gmail = get_gmail_service()
    setup_gmail_watch(gmail)
    
    print(f"\n🎉 All done! Your app will now receive Gmail notifications at:")
    print(f"   {ngrok_url}/webhook/gmail")
    print(f"\n⚠️  Remember:")
    print(f"   - ngrok URL changes each restart (re-run this script)")
    print(f"   - Gmail watch expires after ~7 days (re-run to renew)")


if __name__ == '__main__':
    main()
