"""
Google Sheets API client for logging newsletter processing activity.
Handles authentication, row appending, and connection testing.
"""

import os
from typing import List, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

from src.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class SheetsAuthError(Exception):
    """Raised when Google Sheets authentication fails."""
    pass


class SheetsClient:
    """
    Client for interacting with Google Sheets API.
    
    Attributes:
        credentials_path: Path to service account JSON credentials file
        scopes: Google API scopes required for Sheets access
        service: Authenticated Google Sheets API service instance
    """
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize Sheets client with service account credentials.
        
        Args:
            credentials_path: Path to service account JSON file.
                            If None, reads from GMAIL_CREDENTIALS_PATH env var.
        
        Raises:
            SheetsAuthError: If credentials file not found or authentication fails
        """
        self.credentials_path = credentials_path or os.getenv('GMAIL_CREDENTIALS_PATH')
        
        if not self.credentials_path:
            raise SheetsAuthError(
                "Credentials path not provided. Set GMAIL_CREDENTIALS_PATH environment variable."
            )
        
        if not os.path.exists(self.credentials_path):
            raise SheetsAuthError(
                f"Credentials file not found at: {self.credentials_path}"
            )
        
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.SCOPES
            )
            self.service = build('sheets', 'v4', credentials=credentials)
            logger.info(f"Sheets client initialized with credentials from {self.credentials_path}")
        except Exception as e:
            raise SheetsAuthError(
                f"Failed to authenticate with Google Sheets API: {str(e)}"
            )
    
    @retry_with_backoff(
        max_attempts=3,
        base_delay=2,
        retryable_exceptions=(HttpError, ConnectionError, TimeoutError)
    )
    def read_range(self, sheet_id: str, range_name: str) -> dict:
        """
        Read values from a specified range in the Google Sheet.

        Args:
            sheet_id: The ID of the Google Sheet
            range_name: A1 notation range (e.g., 'Processed IDs!A2:A')

        Returns:
            dict: API response with 'values' key containing list of rows

        Raises:
            SheetsAuthError: If authentication fails
            HttpError: If API request fails for other reasons
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_name
            ).execute()
            return result
        except HttpError as e:
            if e.resp.status in [401, 403]:
                raise SheetsAuthError(
                    f"Authentication/authorization failed: {e.error_details}"
                )
            logger.error(f"Failed to read range {range_name} from Sheets: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading range from Sheets: {str(e)}")
            raise

    @retry_with_backoff(
        max_attempts=3,
        base_delay=2,
        retryable_exceptions=(HttpError, ConnectionError, TimeoutError)
    )
    def append_row(
        self,
        sheet_id: str,
        range_name: str,
        values: List[Any]
    ) -> dict:
        """
        Append a single row to the specified Google Sheet.
        
        Args:
            sheet_id: The ID of the Google Sheet (from URL)
            range_name: The A1 notation range (e.g., 'Sheet1!A:F')
            values: List of values to append as a single row
        
        Returns:
            dict: Response from Sheets API containing update details
        
        Raises:
            SheetsAuthError: If authentication fails during API call
            HttpError: If API request fails for other reasons
        
        Example:
            >>> client = SheetsClient()
            >>> client.append_row(
            ...     sheet_id='1abc123',
            ...     range_name='Logs!A:F',
            ...     values=['2025-01-24T12:00:00Z', 'sender@example.com', 'Subject', 'Post content', 'Success', '0']
            ... )
        """
        try:
            body = {
                'values': [values]
            }
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            logger.info(
                f"Successfully appended row to sheet {sheet_id}, range {range_name}. "
                f"Updated {result.get('updates', {}).get('updatedRows', 0)} rows."
            )
            
            return result
            
        except HttpError as e:
            if e.resp.status in [401, 403]:
                raise SheetsAuthError(
                    f"Authentication/authorization failed: {e.error_details}"
                )
            logger.error(f"Failed to append row to Sheets: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error appending row to Sheets: {str(e)}")
            raise
    
    def test_connection(self, sheet_id: str) -> bool:
        """
        Test connection to Google Sheets by attempting to read sheet metadata.
        
        Args:
            sheet_id: The ID of the Google Sheet to test access
        
        Returns:
            bool: True if connection successful and write access verified, False otherwise
        
        Example:
            >>> client = SheetsClient()
            >>> if client.test_connection('1abc123'):
            ...     print("Connection successful")
        """
        try:
            # Try to get spreadsheet metadata
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=sheet_id
            ).execute()
            
            sheet_title = spreadsheet.get('properties', {}).get('title', 'Unknown')
            logger.info(f"Successfully connected to sheet: {sheet_title}")
            
            # Try to append a test row to verify write access
            test_range = 'Sheet1!A1'  # Minimal range for testing
            test_values = ['Connection test']
            
            self.service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=test_range,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [test_values]}
            ).execute()
            
            logger.info(f"Write access verified for sheet {sheet_id}")
            return True
            
        except HttpError as e:
            if e.resp.status in [401, 403]:
                logger.error(f"Authentication/authorization failed: {e.error_details}")
            else:
                logger.error(f"HTTP error testing connection: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error testing connection: {str(e)}")
            return False


def test_sheets_connection(credentials_path: Optional[str] = None, sheet_id: Optional[str] = None) -> bool:
    """
    Standalone function to test Google Sheets connection.
    
    Args:
        credentials_path: Path to service account JSON. If None, uses env var.
        sheet_id: Sheet ID to test. If None, uses GOOGLE_SHEETS_ID env var.
    
    Returns:
        bool: True if connection and write access verified, False otherwise
    
    Example:
        >>> if test_sheets_connection():
        ...     print("Sheets integration ready")
    """
    try:
        client = SheetsClient(credentials_path)
        test_sheet_id = sheet_id or os.getenv('GOOGLE_SHEETS_ID')
        
        if not test_sheet_id:
            logger.error("No sheet ID provided for connection test")
            return False
        
        return client.test_connection(test_sheet_id)
    except SheetsAuthError as e:
        logger.error(f"Authentication error during connection test: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during connection test: {str(e)}")
        return False
