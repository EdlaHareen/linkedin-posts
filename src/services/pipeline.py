"""
Newsletter Processing Pipeline

Orchestrates the full flow:
  Gmail history → fetch email → deduplicate → transform → log to Sheets → notify Telegram
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from googleapiclient.errors import HttpError

from src.integrations.gmail_client import GmailClient, SenderNotAllowedError, GmailClientError
from src.integrations.sheets_client import SheetsClient
from src.integrations.telegram_client import TelegramClient
from src.services.content_transformer import ContentTransformer, AITransformError
from src.services.deduplication import DeduplicationService
from src.utils.logger import get_logger, log_step_start, log_step_success, log_step_failure

logger = get_logger(__name__)

SHEETS_RANGE = "Sheet1!A:D"


class NewsletterPipeline:
    """
    Orchestrates newsletter-to-LinkedIn-post processing.

    Lazy-initialises all clients so the webhook can return 200 quickly
    before the background thread begins actual work.
    """

    def __init__(self):
        self._gmail_client: Optional[GmailClient] = None
        self._sheets_client: Optional[SheetsClient] = None
        self._telegram_client: Optional[TelegramClient] = None
        self._transformer: Optional[ContentTransformer] = None
        self._dedup: Optional[DeduplicationService] = None

        self.sheet_id = os.getenv("GOOGLE_SHEETS_ID", "")
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    # ------------------------------------------------------------------
    # Lazy client accessors
    # ------------------------------------------------------------------

    @property
    def gmail_client(self) -> GmailClient:
        if self._gmail_client is None:
            self._gmail_client = GmailClient()
        return self._gmail_client

    @property
    def sheets_client(self) -> SheetsClient:
        if self._sheets_client is None:
            self._sheets_client = SheetsClient()
        return self._sheets_client

    @property
    def telegram_client(self) -> TelegramClient:
        if self._telegram_client is None:
            self._telegram_client = TelegramClient(self.bot_token, self.chat_id)
        return self._telegram_client

    @property
    def transformer(self) -> ContentTransformer:
        if self._transformer is None:
            self._transformer = ContentTransformer()
        return self._transformer

    @property
    def dedup(self) -> DeduplicationService:
        if self._dedup is None:
            self._dedup = DeduplicationService(self.sheets_client, self.sheet_id)
        return self._dedup

    # ------------------------------------------------------------------
    # Public entry point called by webhook
    # ------------------------------------------------------------------

    def process_from_history(self, history_id: str, email_address: str) -> None:
        """
        Fetch messages added since history_id and process each one.

        Args:
            history_id: Gmail historyId from the Pub/Sub notification
            email_address: Gmail address that received the notification
        """
        log_step_start("process_from_history", {
            "history_id": history_id,
            "email_address": email_address,
        })

        try:
            message_ids = self._get_new_message_ids(history_id)
        except Exception as e:
            logger.error(
                "Failed to fetch history from Gmail",
                extra={"history_id": history_id, "error": str(e)},
                exc_info=True,
            )
            self.telegram_client.send_error_alert(
                error_type="GmailHistoryError",
                error_message=str(e),
                context={"history_id": history_id},
            )
            return

        if not message_ids:
            logger.info("No new messages in history window", extra={"history_id": history_id})
            return

        logger.info(f"Found {len(message_ids)} new message(s) to process")

        for message_id in message_ids:
            self._process_single_message(message_id)

        log_step_success("process_from_history", 0, f"Processed {len(message_ids)} message(s)")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_fallback_log(
        self,
        message_id: str,
        sender: str,
        subject: str,
        post_text: str,
        timestamp: str,
        sheets_error: str,
    ) -> None:
        """Write a local JSON fallback when both Sheets and Telegram are unavailable."""
        try:
            fallback_dir = Path("logs/fallback")
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fallback_file = fallback_dir / f"{message_id}.json"
            with open(fallback_file, "w") as f:
                json.dump({
                    "message_id": message_id,
                    "sender": sender,
                    "subject": subject,
                    "post_text": post_text,
                    "timestamp": timestamp,
                    "errors": {"sheets": sheets_error, "telegram": "send_notification returned False"},
                }, f, indent=2)
            logger.warning(
                "Both Sheets and Telegram failed — fallback log written",
                extra={"message_id": message_id, "fallback_file": str(fallback_file)},
            )
        except Exception as e:
            logger.error(
                "Failed to write fallback log",
                extra={"message_id": message_id, "error": str(e)},
                exc_info=True,
            )

    def _get_new_message_ids(self, history_id: str) -> list[str]:
        """
        Call Gmail History API to get message IDs added since history_id.

        Returns:
            List of message IDs for newly received messages.
        """
        service = self.gmail_client.service
        history = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=history_id,
                historyTypes=["messageAdded"],
            )
            .execute()
        )

        message_ids = []
        for record in history.get("history", []):
            for added in record.get("messagesAdded", []):
                msg_id = added.get("message", {}).get("id")
                if msg_id:
                    message_ids.append(msg_id)

        return message_ids

    def _process_single_message(self, message_id: str) -> None:
        """
        Run the full pipeline for one Gmail message ID.

        Steps:
          1. Deduplication check
          2. Fetch email via Gmail API
          3. Transform to LinkedIn post via GPT-4o-mini
          4. Append row to Google Sheets
          5. Send Telegram notification
          6. Mark message as processed
        """
        logger.info("Processing message", extra={"message_id": message_id})

        # 1. Deduplication
        if self.dedup.is_duplicate(message_id):
            logger.info("Skipping duplicate message", extra={"message_id": message_id})
            return

        # 2. Fetch email
        try:
            email_data = self.gmail_client.fetch_email(message_id)
        except SenderNotAllowedError as e:
            logger.info(str(e), extra={"message_id": message_id})
            self.dedup.mark_as_processed(message_id, status="rejected")
            return
        except GmailClientError as e:
            logger.error(
                "Gmail fetch failed",
                extra={"message_id": message_id, "error": str(e)},
                exc_info=True,
            )
            self.dedup.mark_as_processed(message_id, status="failed")
            self.telegram_client.send_error_alert(
                error_type="GmailFetchError",
                error_message=str(e),
                context={"message_id": message_id},
            )
            return

        subject = email_data["subject"]
        sender = email_data["sender"]
        body = email_data["body_html"] or email_data["body_text"]

        # 3. Transform to LinkedIn post
        try:
            result = self.transformer.transform_to_linkedin_post(body, subject)
            post_text = result["post_text"]
        except AITransformError as e:
            logger.error(
                "Content transformation failed",
                extra={"message_id": message_id, "subject": subject, "error": str(e)},
                exc_info=True,
            )
            self.dedup.mark_as_processed(message_id, status="failed")
            self.telegram_client.send_error_alert(
                error_type="AITransformError",
                error_message=str(e),
                context={"message_id": message_id, "subject": subject},
            )
            return

        # 4. Log to Google Sheets
        processed_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sheets_error: Optional[str] = None
        try:
            self.sheets_client.append_row(
                sheet_id=self.sheet_id,
                range_name=SHEETS_RANGE,
                values=[processed_date, subject, post_text, ""],
            )
            logger.info("Appended row to Sheets", extra={"message_id": message_id})
        except Exception as e:
            sheets_error = str(e)
            logger.error(
                "Failed to log to Google Sheets",
                extra={"message_id": message_id, "error": sheets_error},
                exc_info=True,
            )
            self.telegram_client.send_error_alert(
                error_type="SheetsLoggingError",
                error_message=sheets_error,
                context={"message_id": message_id, "subject": subject},
            )

        # 5. Telegram notification
        telegram_ok = self.telegram_client.send_notification(
            post_content=post_text,
            metadata={
                "sender": sender,
                "subject": subject,
                "timestamp": processed_date,
                "status": "Success",
            },
        )

        # Fallback: if both Sheets and Telegram failed, write local JSON
        if sheets_error and not telegram_ok:
            self._write_fallback_log(
                message_id=message_id,
                sender=sender,
                subject=subject,
                post_text=post_text,
                timestamp=processed_date,
                sheets_error=sheets_error,
            )

        # 6. Mark as processed
        self.dedup.mark_as_processed(
            message_id,
            status="success",
            metadata={"subject": subject, "sender": sender},
        )

        logger.info(
            "Message processed successfully",
            extra={"message_id": message_id, "subject": subject},
        )
