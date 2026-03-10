"""
Pytest configuration and shared fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

# Add src directory to Python path for tests
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def mock_env_vars(monkeypatch):
    """
    Fixture to set up mock environment variables for testing.
    """
    env_vars = {
        "GMAIL_CREDENTIALS_PATH": "config/test-credentials.json",
        "OPENAI_API_KEY": "test-openai-key",
        "TELEGRAM_BOT_TOKEN": "test-telegram-token",
        "TELEGRAM_CHAT_ID": "test-chat-id",
        "GOOGLE_SHEETS_ID": "test-sheets-id",
        "WEBHOOK_SECRET_TOKEN": "test-secret-token",
        "ALLOWED_SENDERS": "beehiiv.com,therundown.ai",
        "FLASK_ENV": "testing",
        "LOG_LEVEL": "DEBUG",
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return env_vars


@pytest.fixture
def sample_email_data():
    """
    Fixture providing sample email data for testing.
    """
    return {
        "message_id": "test-message-123",
        "sender": "newsletter@beehiiv.com",
        "subject": "Weekly Tech Newsletter",
        "body_html": "<html><body><h1>Latest Tech News</h1><p>AI is transforming everything...</p></body></html>",
        "body_text": "Latest Tech News\n\nAI is transforming everything...",
        "received_date": "2025-01-24T12:00:00Z",
    }


@pytest.fixture
def sample_linkedin_post():
    """
    Fixture providing sample LinkedIn post data.
    """
    return {
        "post_text": "🚀 AI is transforming the tech landscape! This week's insights on machine learning trends. #AI #TechNews #Innovation",
        "char_count": 125,
        "hashtags_used": ["AI", "TechNews", "Innovation"],
    }
