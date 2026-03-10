"""
Telegram notification client for sending LinkedIn post updates and error alerts.

This module implements the Telegram Bot API integration for sending formatted
notifications about processed newsletters and critical system errors.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from telegram import Bot
from telegram.error import TelegramError, InvalidToken, NetworkError, TimedOut
from telegram.constants import ParseMode

from src.utils.retry import retry_with_backoff
from src.utils.logger import log_step_start, log_step_success, log_step_failure

logger = logging.getLogger(__name__)


class TelegramClient:
    """Client for sending notifications via Telegram Bot API."""
    
    # Telegram message length limit
    MAX_MESSAGE_LENGTH = 4096
    TRUNCATION_SUFFIX = "..."
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram client.
        
        Args:
            bot_token: Telegram bot authentication token
            chat_id: Target chat ID for notifications
            
        Raises:
            ValueError: If bot_token or chat_id is empty
        """
        if not bot_token:
            raise ValueError("Telegram bot token cannot be empty")
        if not chat_id:
            raise ValueError("Telegram chat ID cannot be empty")
            
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._bot: Optional[Bot] = None
        
        logger.info(f"TelegramClient initialized for chat ID: {chat_id}")
    
    @property
    def bot(self) -> Bot:
        """Lazy-load Telegram Bot instance."""
        if self._bot is None:
            try:
                self._bot = Bot(token=self.bot_token)
                logger.debug("Telegram Bot instance created")
            except InvalidToken as e:
                logger.error(f"Invalid Telegram bot token: {e}")
                raise
        return self._bot
    
    def _truncate_message(self, message: str) -> str:
        """
        Truncate message to Telegram's length limit.
        
        Args:
            message: Original message text
            
        Returns:
            Truncated message if needed, otherwise original
        """
        if len(message) <= self.MAX_MESSAGE_LENGTH:
            return message
        
        max_length = self.MAX_MESSAGE_LENGTH - len(self.TRUNCATION_SUFFIX)
        truncated = message[:max_length] + self.TRUNCATION_SUFFIX
        
        logger.warning(
            f"Message truncated from {len(message)} to {len(truncated)} characters"
        )
        
        return truncated
    
    @retry_with_backoff(
        max_attempts=3,
        base_delay=2,
        backoff_multiplier=2,
        retryable_exceptions=(NetworkError, TimedOut)
    )
    def send_notification(
        self,
        post_content: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Send formatted notification about generated LinkedIn post.
        
        Args:
            post_content: The generated LinkedIn post text
            metadata: Additional context (sender, subject, timestamp, etc.)
            
        Returns:
            True if message sent successfully, False otherwise
            
        Note:
            This method implements graceful degradation - errors are logged
            but do not raise exceptions to prevent pipeline failures.
        """
        step_name = "telegram_notification"
        log_step_start(step_name, {
            "chat_id": self.chat_id,
            "post_length": len(post_content),
            "metadata_keys": list(metadata.keys())
        })
        
        start_time = datetime.now()
        
        try:
            # Extract metadata with safe defaults
            sender = metadata.get("sender", "Unknown")
            subject = metadata.get("subject", "No subject")
            timestamp = metadata.get("timestamp", datetime.now().isoformat())
            status = metadata.get("status", "Success")
            
            # Format message
            message = self._format_notification_message(
                post_content=post_content,
                sender=sender,
                subject=subject,
                timestamp=timestamp,
                status=status
            )
            
            # Truncate if needed
            message = self._truncate_message(message)
            
            # Send message
            self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            log_step_success(
                step_name,
                duration_ms,
                f"Notification sent ({len(message)} chars)"
            )
            
            return True
            
        except InvalidToken as e:
            # Non-retryable authentication error
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = f"Invalid Telegram bot token: {str(e)}"
            log_step_failure(step_name, "InvalidToken", error_msg)
            logger.error(error_msg)
            return False
            
        except TelegramError as e:
            # Other Telegram API errors (network, rate limit, etc.)
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = f"Telegram API error: {str(e)}"
            log_step_failure(step_name, type(e).__name__, error_msg)
            logger.error(error_msg)
            return False
            
        except Exception as e:
            # Unexpected errors
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = f"Unexpected error sending Telegram notification: {str(e)}"
            log_step_failure(step_name, type(e).__name__, error_msg)
            logger.exception(error_msg)
            return False
    
    @retry_with_backoff(
        max_attempts=3,
        base_delay=2,
        backoff_multiplier=2,
        retryable_exceptions=(NetworkError, TimedOut)
    )
    def send_error_alert(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send critical error alert notification.
        
        Args:
            error_type: Type/category of error (e.g., "SheetsAPIError")
            error_message: Detailed error message
            context: Optional context data (message_id, sender, etc.)
            
        Returns:
            True if alert sent successfully, False otherwise
            
        Note:
            This method implements graceful degradation - errors are logged
            but do not raise exceptions.
        """
        step_name = "telegram_error_alert"
        log_step_start(step_name, {
            "error_type": error_type,
            "has_context": context is not None
        })
        
        start_time = datetime.now()
        
        try:
            # Format error alert message
            message = self._format_error_alert_message(
                error_type=error_type,
                error_message=error_message,
                context=context or {}
            )
            
            # Truncate if needed
            message = self._truncate_message(message)
            
            # Send alert
            self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            log_step_success(
                step_name,
                duration_ms,
                f"Error alert sent for {error_type}"
            )
            
            return True
            
        except TelegramError as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = f"Failed to send error alert via Telegram: {str(e)}"
            log_step_failure(step_name, type(e).__name__, error_msg)
            logger.error(error_msg)
            return False
            
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            error_msg = f"Unexpected error sending error alert: {str(e)}"
            log_step_failure(step_name, type(e).__name__, error_msg)
            logger.exception(error_msg)
            return False
    
    def _format_notification_message(
        self,
        post_content: str,
        sender: str,
        subject: str,
        timestamp: str,
        status: str
    ) -> str:
        """
        Format notification message with LinkedIn post details.
        
        Args:
            post_content: Generated LinkedIn post text
            sender: Newsletter sender email
            subject: Email subject line
            timestamp: Processing timestamp
            status: Processing status
            
        Returns:
            Formatted HTML message
        """
        # Escape HTML special characters in user content
        post_content_escaped = self._escape_html(post_content)
        subject_escaped = self._escape_html(subject)
        sender_escaped = self._escape_html(sender)
        
        message = f"""📧 <b>New LinkedIn Post Generated</b>

{post_content_escaped}

━━━━━━━━━━━━━━━━━━━━
📊 <b>Source:</b> {sender_escaped}
📝 <b>Subject:</b> {subject_escaped}
📅 <b>Processed:</b> {timestamp}
✅ <b>Status:</b> {status}"""
        
        return message
    
    def _format_error_alert_message(
        self,
        error_type: str,
        error_message: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Format critical error alert message.
        
        Args:
            error_type: Error type/category
            error_message: Detailed error message
            context: Additional context data
            
        Returns:
            Formatted HTML message
        """
        error_type_escaped = self._escape_html(error_type)
        error_message_escaped = self._escape_html(error_message)
        
        message = f"""🚨 <b>CRITICAL ERROR: {error_type_escaped}</b>

<b>Error Details:</b>
{error_message_escaped}

━━━━━━━━━━━━━━━━━━━━
⏰ <b>Time:</b> {datetime.now().isoformat()}"""
        
        # Add context if available
        if context:
            message += "\n\n<b>Context:</b>"
            for key, value in context.items():
                key_escaped = self._escape_html(str(key))
                value_escaped = self._escape_html(str(value))
                message += f"\n• {key_escaped}: {value_escaped}"
        
        return message
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """
        Escape HTML special characters for Telegram HTML parse mode.
        
        Args:
            text: Raw text to escape
            
        Returns:
            HTML-escaped text
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
    
    def test_connection(self) -> bool:
        """
        Test Telegram bot connection and permissions.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            bot_info = self.bot.get_me()
            logger.info(f"Telegram connection test successful. Bot: @{bot_info.username}")
            return True
        except TelegramError as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False
