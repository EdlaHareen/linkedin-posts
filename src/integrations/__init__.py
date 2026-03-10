"""
External service integrations package.

This package contains client modules for interacting with external APIs:
- Gmail API
- Google Sheets API
- OpenAI API
- Telegram Bot API
"""

from src.integrations.telegram_client import TelegramClient

__all__ = ["TelegramClient"]
