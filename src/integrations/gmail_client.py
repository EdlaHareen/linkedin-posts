"""
Gmail API client for fetching and validating newsletter emails.

This module provides functionality to:
- Fetch emails by message ID using Gmail API
- Extract sender information from email headers
- Validate senders against an allowlist
- Handle authentication and API errors gracefully
"""

import os
import re
from typing import Dict, List, Optional
from datetime import datetime
import base64
from email.utils import parseaddr
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..utils.logger import log_step_start, log_step_success, log_step_failure
from ..utils.retry import retry_with_backoff


class GmailClientError(Exception):
    """Base exception for Gmail client errors."""
    pass


class EmailNotFoundError(GmailClientError):
    """Raised when email with given message ID doesn't exist."""
    pass


class SenderNotAllowedError(GmailClientError):
    """Raised when sender is not in the allowlist."""
    pass


class GmailAuthError(GmailClientError):
    """Raised when Gmail API authentication fails."""
    pass


class GmailClient:
    """
    Client for interacting with Gmail API.
    
    Handles email fetching, sender validation, and authentication.
    Uses OAuth 2.0 tokens for personal Gmail accounts.
    """
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, credentials_path: Optional[str] = None, allowed_senders: Optional[str] = None):
        """
        Initialize Gmail client.
        
        Args:
            credentials_path: Path to OAuth token JSON file.
                            If None, reads from GMAIL_TOKEN_PATH env var,
                            falling back to config/gmail-token.json.
            allowed_senders: Comma-separated list of allowed sender domains.
                           If None, reads from ALLOWED_SENDERS env var.
        
        Raises:
            GmailAuthError: If credentials are invalid or missing.
        """
        # Token file path (OAuth 2.0 token)
        self.token_path = credentials_path or os.getenv(
            'GMAIL_TOKEN_PATH',
            str(Path(__file__).parent.parent.parent / 'config' / 'gmail-token.json')
        )
        self.allowed_senders_raw = allowed_senders or os.getenv('ALLOWED_SENDERS', '')
        
        # Parse allowed senders list
        self.allowed_senders = self._parse_allowed_senders(self.allowed_senders_raw)
        
        # Initialize Gmail service
        self.service = self._initialize_service()
    
    def _parse_allowed_senders(self, raw_senders: str) -> List[str]:
        """
        Parse comma-separated allowed senders string.
        
        Args:
            raw_senders: Comma-separated string of allowed domains/emails
        
        Returns:
            List of cleaned sender domains/emails
        """
        if not raw_senders or not raw_senders.strip():
            log_step_failure(
                step_name="parse_allowed_senders",
                error=ValueError("No allowed senders configured - all emails will be rejected")
            )
            return []
        
        senders = [s.strip().lower() for s in raw_senders.split(',') if s.strip()]
        return senders
    
    def _initialize_service(self):
        """
        Initialize Gmail API service with OAuth 2.0 tokens.
        
        Loads tokens from the token file and auto-refreshes if expired.
        
        Returns:
            Authenticated Gmail API service object
        
        Raises:
            GmailAuthError: If authentication fails
        """
        try:
            if not self.token_path or not os.path.exists(self.token_path):
                raise GmailAuthError(
                    f"Gmail token file not found: {self.token_path}. "
                    f"Run 'python scripts/get_gmail_token.py' to authenticate."
                )
            
            creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
            
            # Refresh token if expired
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Save refreshed token
                with open(self.token_path, 'w') as f:
                    f.write(creds.to_json())
            
            if not creds or not creds.valid:
                raise GmailAuthError(
                    "Gmail token is invalid or expired. "
                    "Run 'python scripts/get_gmail_token.py' to re-authenticate."
                )
            
            service = build('gmail', 'v1', credentials=creds)
            
            log_step_success(
                step_name="gmail_auth",
                output_summary="Gmail API service initialized with OAuth 2.0"
            )
            
            return service
            
        except GmailAuthError:
            raise
        except Exception as e:
            log_step_failure(
                step_name="gmail_auth",
                error=e
            )
            raise GmailAuthError(f"Gmail authentication failed: {str(e)}")
    
    def _extract_sender_email(self, from_header: str) -> str:
        """
        Extract email address from 'From' header.
        
        Handles formats:
        - "Name <email@domain.com>"
        - "email@domain.com"
        - "<email@domain.com>"
        
        Args:
            from_header: Raw 'From' header value
        
        Returns:
            Extracted email address in lowercase
        """
        # Use email.utils.parseaddr for robust parsing
        name, email = parseaddr(from_header)
        
        if email:
            return email.lower().strip()
        
        # Fallback: regex extraction
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        match = re.search(email_pattern, from_header)
        
        if match:
            return match.group(0).lower().strip()
        
        return from_header.lower().strip()
    
    def _extract_sender_domain(self, email: str) -> str:
        """
        Extract domain from email address.
        
        Args:
            email: Email address
        
        Returns:
            Domain portion (e.g., "example.com")
        """
        if '@' in email:
            return email.split('@')[1].lower()
        return email.lower()
    
    def is_sender_allowed(self, sender_email: str) -> bool:
        """
        Check if sender is in the allowlist.
        
        Matches against both full email addresses and domains.
        
        Args:
            sender_email: Email address to validate
        
        Returns:
            True if sender is allowed, False otherwise
        """
        if not self.allowed_senders:
            return False
        
        sender_email = sender_email.lower().strip()
        sender_domain = self._extract_sender_domain(sender_email)
        
        # Check both full email and domain
        for allowed in self.allowed_senders:
            if allowed == sender_email or allowed == sender_domain:
                return True
            
            # Support wildcard domains (e.g., "*.example.com")
            if allowed.startswith('*.'):
                allowed_domain = allowed[2:]
                if sender_domain.endswith(allowed_domain):
                    return True
        
        return False
    
    @retry_with_backoff(
        max_attempts=3,
        base_delay=2,
        retryable_exceptions=[HttpError, ConnectionError, TimeoutError]
    )
    def fetch_email(self, message_id: str) -> Dict[str, any]:
        """
        Fetch email by message ID from Gmail.
        
        Args:
            message_id: Gmail message ID
        
        Returns:
            Dictionary with email data:
            {
                'sender': str,
                'subject': str,
                'body_html': str,
                'body_text': str,
                'message_id': str,
                'received_date': str (ISO8601)
            }
        
        Raises:
            EmailNotFoundError: If message ID doesn't exist
            SenderNotAllowedError: If sender is not in allowlist
            GmailClientError: For other API errors
        """
        log_step_start(
            step_name="fetch_email",
            metadata={"message_id": message_id}
        )
        
        start_time = datetime.now()
        
        try:
            # Fetch message with full format to get headers and body
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Extract headers
            headers = {
                header['name'].lower(): header['value']
                for header in message['payload']['headers']
            }
            
            sender_raw = headers.get('from', '')
            sender_email = self._extract_sender_email(sender_raw)
            subject = headers.get('subject', '')
            date_header = headers.get('date', '')
            
            # Validate sender
            if not self.is_sender_allowed(sender_email):
                log_step_failure(
                    step_name="fetch_email",
                    error=SenderNotAllowedError(f"Sender rejected: {sender_email} (not in allowlist)")
                )
                raise SenderNotAllowedError(
                    f"Sender {sender_email} is not in the allowlist"
                )
            
            # Extract body
            body_html, body_text = self._extract_body(message['payload'])
            
            # Parse received date
            try:
                from email.utils import parsedate_to_datetime
                received_date = parsedate_to_datetime(date_header).isoformat()
            except:
                received_date = datetime.now().isoformat()
            
            email_data = {
                'sender': sender_email,
                'subject': subject,
                'body_html': body_html,
                'body_text': body_text,
                'message_id': message_id,
                'received_date': received_date
            }
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            log_step_success(
                step_name="fetch_email",
                output_summary=f"Fetched email from {sender_email}: {subject[:50]}",
                metadata={"duration_ms": duration_ms}
            )
            
            return email_data
            
        except HttpError as e:
            if e.resp.status == 404:
                log_step_failure(
                    step_name="fetch_email",
                    error=e
                )
                raise EmailNotFoundError(f"Message ID {message_id} not found")
            
            log_step_failure(
                step_name="fetch_email",
                error=e
            )
            raise GmailClientError(f"Failed to fetch email: {str(e)}")
        
        except SenderNotAllowedError:
            # Re-raise without wrapping
            raise
        
        except Exception as e:
            log_step_failure(
                step_name="fetch_email",
                error=e
            )
            raise GmailClientError(f"Failed to fetch email: {str(e)}")
    
    def _extract_body(self, payload: Dict) -> tuple[str, str]:
        """
        Extract HTML and plain text body from email payload.
        
        Args:
            payload: Gmail message payload
        
        Returns:
            Tuple of (html_body, text_body)
        """
        html_body = ""
        text_body = ""
        
        def parse_parts(parts):
            nonlocal html_body, text_body
            
            for part in parts:
                mime_type = part.get('mimeType', '')
                
                # Recursive for multipart
                if 'parts' in part:
                    parse_parts(part['parts'])
                
                # Extract body data
                elif mime_type == 'text/html' and 'data' in part.get('body', {}):
                    html_body = base64.urlsafe_b64decode(
                        part['body']['data']
                    ).decode('utf-8', errors='ignore')
                
                elif mime_type == 'text/plain' and 'data' in part.get('body', {}):
                    text_body = base64.urlsafe_b64decode(
                        part['body']['data']
                    ).decode('utf-8', errors='ignore')
        
        # Handle single-part messages
        if 'parts' in payload:
            parse_parts(payload['parts'])
        elif 'body' in payload and 'data' in payload['body']:
            mime_type = payload.get('mimeType', '')
            body_data = base64.urlsafe_b64decode(
                payload['body']['data']
            ).decode('utf-8', errors='ignore')
            
            if mime_type == 'text/html':
                html_body = body_data
            else:
                text_body = body_data
        
        return html_body, text_body
    
    def validate_sender(self, sender_email: str) -> None:
        """
        Validate sender against allowlist.
        
        Args:
            sender_email: Email address to validate
        
        Raises:
            SenderNotAllowedError: If sender is not allowed
        """
        if not self.is_sender_allowed(sender_email):
            raise SenderNotAllowedError(
                f"Sender {sender_email} is not in the allowlist"
            )


def create_gmail_client() -> GmailClient:
    """
    Factory function to create Gmail client with environment configuration.
    
    Returns:
        Configured GmailClient instance
    """
    return GmailClient()
