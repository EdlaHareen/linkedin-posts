"""
End-to-end test: feeds a sample newsletter through the pipeline.
Tests: GPT-4o-mini transformation → Google Sheets logging → Telegram notification.

Usage:
    python scripts/test_pipeline.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Setup paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from src.services.content_transformer import ContentTransformer
from src.integrations.sheets_client import SheetsClient
from src.integrations.telegram_client import TelegramClient

# Sample newsletter content
SAMPLE_SUBJECT = "AI Weekly: OpenAI launches GPT-5 with reasoning capabilities"
SAMPLE_BODY = """
OpenAI just dropped GPT-5, and it's not just another upgrade — it's a complete paradigm shift.

Here's what's new:

1. Real-time reasoning: GPT-5 can now solve multi-step problems by "thinking" through them step by step, 
   showing its work like a brilliant tutor. Early benchmarks show a 40% improvement on complex math and coding tasks.

2. Native multimodal: It can process images, audio, and video simultaneously. No more separate models 
   for each modality. One model to rule them all.

3. 1M token context window: You can now feed it an entire codebase or a full book and it maintains 
   coherence throughout.

4. 3x cheaper than GPT-4: Despite being more powerful, OpenAI dropped the price dramatically. 
   GPT-5 costs $5 per million tokens (input) vs GPT-4's $15.

The implications are staggering. Companies like Stripe are already using it to automate 60% of their 
customer support. Duolingo reported a 25% increase in learning outcomes after switching.

But here's the catch: GPT-5 is so good that it's raising serious concerns about AI safety. 
Several researchers have called for a temporary pause to evaluate the societal impact.

What does this mean for you? If you're a developer, the bar just got raised. If you're a business owner, 
the ROI on AI integration just became impossible to ignore.

The AI revolution isn't coming — it's here.
"""


def main():
    print("🧪 Testing LinkedIn Posts Pipeline\n")
    
    # Step 1: Transform newsletter to LinkedIn post
    print("--- Step 1: AI Transformation (GPT-4o-mini) ---")
    try:
        transformer = ContentTransformer()
        result = transformer.transform_to_linkedin_post(SAMPLE_BODY, SAMPLE_SUBJECT)
        post_text = result['post_text']
        char_count = result['char_count']
        hashtags = result.get('hashtags_used', [])
        
        print(f"✅ Generated post ({char_count} chars, {len(hashtags)} hashtags)")
        print(f"\n{'='*60}")
        print(post_text)
        print(f"{'='*60}\n")
    except Exception as e:
        print(f"❌ AI transformation failed: {e}")
        sys.exit(1)
    
    # Step 2: Log to Google Sheets
    print("--- Step 2: Google Sheets Logging ---")
    try:
        sheets = SheetsClient()
        sheet_id = os.getenv('GOOGLE_SHEETS_ID')
        
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            SAMPLE_SUBJECT,
            post_text,
            ""  # No image URL
        ]
        
        sheets.service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Sheet1!A:D",
            valueInputOption="USER_ENTERED",
            body={"values": [row]}
        ).execute()
        
        print(f"✅ Row appended to Google Sheet")
    except Exception as e:
        print(f"❌ Sheets logging failed: {e}")
    
    # Step 3: Send to Telegram
    print("\n--- Step 3: Telegram Notification ---")
    try:
        import requests
        
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        message = f"📋 *Test Pipeline Result*\n\n"
        message += f"📰 *Subject:* {SAMPLE_SUBJECT}\n\n"
        message += f"---\n\n{post_text}"
        
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
        )
        
        if resp.json().get('ok'):
            print(f"✅ Post sent to Telegram!")
        else:
            print(f"❌ Telegram API error: {resp.json()}")
    except Exception as e:
        print(f"❌ Telegram notification failed: {e}")
    
    print("\n🎉 Pipeline test complete!")


if __name__ == '__main__':
    main()
