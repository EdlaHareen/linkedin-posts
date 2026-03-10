"""
Email Deduplication Service

Tracks processed message IDs using Google Sheets to prevent duplicate processing.
Implements fail-open strategy when Sheets API is unavailable.
"""

import logging
from datetime import datetime
from typing import Optional

from src.integrations.sheets_client import SheetsClient, SheetsAuthError


logger = logging.getLogger(__name__)


class DeduplicationError(Exception):
    """Base exception for deduplication operations."""
    pass


class DeduplicationService:
    """
    Manages email deduplication using Google Sheets as the persistence layer.
    
    The service maintains a "Processed IDs" sheet with columns:
    - Message ID: Gmail message identifier
    - Processed At: ISO8601 timestamp
    - Status: Processing result (success/failed/rejected)
    """
    
    SHEET_NAME = "Processed IDs"
    COLUMNS = ["Message ID", "Processed At", "Status"]
    
    def __init__(self, sheets_client: SheetsClient, sheet_id: str):
        """
        Initialize deduplication service.
        
        Args:
            sheets_client: Configured Google Sheets client
            sheet_id: Target spreadsheet ID
        """
        self.sheets_client = sheets_client
        self.sheet_id = sheet_id
        self._ensure_sheet_exists()
    
    def _ensure_sheet_exists(self) -> None:
        """
        Verify the Processed IDs sheet exists with correct headers.
        Creates sheet and headers if missing.
        """
        try:
            # Try to read first row to check if sheet exists
            range_name = f"{self.SHEET_NAME}!A1:C1"
            result = self.sheets_client.read_range(self.sheet_id, range_name)
            
            if not result or not result.get('values'):
                # Sheet exists but no headers - add them
                logger.info(f"Adding headers to {self.SHEET_NAME} sheet")
                self.sheets_client.append_row(
                    self.sheet_id,
                    f"{self.SHEET_NAME}!A1",
                    [self.COLUMNS]
                )
            elif result['values'][0] != self.COLUMNS:
                logger.warning(
                    f"Sheet headers mismatch. Expected {self.COLUMNS}, "
                    f"found {result['values'][0]}"
                )
        except Exception as e:
            logger.warning(
                f"Could not verify {self.SHEET_NAME} sheet structure: {e}. "
                "Proceeding with assumption sheet exists."
            )
    
    def is_duplicate(self, message_id: str) -> bool:
        """
        Check if message ID has been processed before.
        
        Implements fail-open strategy: if Sheets API is unavailable,
        returns False to allow processing (with warning logged).
        
        Args:
            message_id: Gmail message identifier to check
            
        Returns:
            True if message has been processed, False otherwise
        """
        if not message_id:
            logger.error("Cannot check duplicate for empty message_id")
            return False
        
        try:
            # Read all message IDs from column A (skip header row)
            range_name = f"{self.SHEET_NAME}!A2:A"
            result = self.sheets_client.read_range(self.sheet_id, range_name)
            
            if not result or not result.get('values'):
                # No processed messages yet
                logger.debug(f"No processed messages found - {message_id} is new")
                return False
            
            # Flatten the 2D array and check for message_id
            processed_ids = [row[0] for row in result['values'] if row]
            
            if message_id in processed_ids:
                logger.info(f"Duplicate email detected: {message_id}")
                return True
            
            logger.debug(f"Message ID {message_id} not found in processed list")
            return False
            
        except SheetsAuthError as e:
            logger.error(
                f"Authentication failed during deduplication check: {e}. "
                "This is a critical error - manual intervention required."
            )
            # For auth errors, fail-open to avoid blocking pipeline
            logger.warning("Deduplication check failed - proceeding with caution")
            return False
            
        except Exception as e:
            logger.warning(
                f"Deduplication check failed for {message_id}: {e}. "
                "Proceeding with caution (fail-open strategy)."
            )
            return False
    
    def mark_as_processed(
        self,
        message_id: str,
        status: str = "success",
        metadata: Optional[dict] = None
    ) -> bool:
        """
        Mark message as processed by appending to Sheets.
        
        Implements graceful degradation: logs error but does not raise
        exception if Sheets API fails.
        
        Args:
            message_id: Gmail message identifier
            status: Processing result (success/failed/rejected)
            metadata: Optional additional context (for logging only)
            
        Returns:
            True if successfully marked, False if failed
        """
        if not message_id:
            logger.error("Cannot mark empty message_id as processed")
            return False
        
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        try:
            row_data = [message_id, timestamp, status]
            self.sheets_client.append_row(
                self.sheet_id,
                f"{self.SHEET_NAME}!A:C",
                [row_data]
            )
            
            logger.info(
                f"Marked message {message_id} as processed with status: {status}",
                extra={"metadata": metadata} if metadata else {}
            )
            return True
            
        except SheetsAuthError as e:
            logger.error(
                f"Authentication failed while marking {message_id} as processed: {e}. "
                "Message may be reprocessed on next run."
            )
            return False
            
        except Exception as e:
            logger.error(
                f"Failed to mark {message_id} as processed: {e}. "
                "Message may be reprocessed on next run.",
                extra={"metadata": metadata} if metadata else {}
            )
            return False
    
    def get_recent_processed(self, limit: int = 20) -> list[dict]:
        """
        Retrieve recently processed messages for dashboard/monitoring.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of dicts with keys: message_id, processed_at, status
        """
        try:
            # Read last N rows (approximate - reads from end)
            range_name = f"{self.SHEET_NAME}!A2:C"
            result = self.sheets_client.read_range(self.sheet_id, range_name)
            
            if not result or not result.get('values'):
                return []
            
            rows = result['values']
            # Take last N rows and reverse to show newest first
            recent_rows = rows[-limit:] if len(rows) > limit else rows
            recent_rows.reverse()
            
            return [
                {
                    "message_id": row[0] if len(row) > 0 else "N/A",
                    "processed_at": row[1] if len(row) > 1 else "N/A",
                    "status": row[2] if len(row) > 2 else "unknown"
                }
                for row in recent_rows
            ]
            
        except Exception as e:
            logger.error(f"Failed to retrieve recent processed messages: {e}")
            return []
