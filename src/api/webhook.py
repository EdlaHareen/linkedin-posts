"""
Gmail Pub/Sub webhook endpoint with security validation.
Handles incoming Gmail notifications and triggers email processing pipeline.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import base64
import json
import os
from typing import Dict, Any, Tuple

from src.utils.logger import get_logger, log_step_start, log_step_success, log_step_failure
from src.services.pipeline import NewsletterPipeline

logger = get_logger(__name__)
webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')

# Load secret token from environment
WEBHOOK_SECRET_TOKEN = os.getenv('WEBHOOK_SECRET_TOKEN')

if not WEBHOOK_SECRET_TOKEN:
    logger.warning("WEBHOOK_SECRET_TOKEN not set - webhook endpoint will reject all requests")


def validate_webhook_token(token: str) -> bool:
    """
    Validate the webhook secret token.
    
    Args:
        token: Token from request header
        
    Returns:
        bool: True if token is valid, False otherwise
    """
    if not WEBHOOK_SECRET_TOKEN:
        logger.error("No WEBHOOK_SECRET_TOKEN configured")
        return False
    
    return token == WEBHOOK_SECRET_TOKEN


def decode_pubsub_message(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decode Gmail Pub/Sub message payload.
    
    Args:
        request_data: Request JSON data
        
    Returns:
        dict: Decoded message data with 'message_id' and 'email_address'
        
    Raises:
        ValueError: If payload is malformed or cannot be decoded
    """
    try:
        # Extract message from Pub/Sub envelope
        message = request_data.get('message', {})
        
        if not message:
            raise ValueError("Missing 'message' field in request")
        
        # Decode base64 data
        data_b64 = message.get('data', '')
        if not data_b64:
            raise ValueError("Missing 'data' field in message")
        
        # Decode and parse JSON
        data_bytes = base64.b64decode(data_b64)
        data_json = json.loads(data_bytes.decode('utf-8'))
        
        # Extract Gmail-specific fields
        email_address = data_json.get('emailAddress')
        history_id = data_json.get('historyId')
        
        logger.debug(f"Decoded Pub/Sub message - email: {email_address}, historyId: {history_id}")
        
        return {
            'email_address': email_address,
            'history_id': history_id,
            'raw_data': data_json
        }
        
    except (base64.binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Failed to decode Pub/Sub message: {str(e)}")


@webhook_bp.route('/health', methods=['GET'])
def health_check() -> Tuple[Dict[str, Any], int]:
    """
    Health check endpoint. Verifies all external service dependencies are reachable.
    Returns 200 if healthy, 503 if any critical service is degraded.
    """
    from src.integrations.gmail_client import GmailClient, GmailAuthError
    from src.integrations.sheets_client import SheetsClient, SheetsAuthError
    from src.services.content_transformer import ContentTransformer, AITransformError

    status = "healthy"
    issues = []

    # Gmail API
    try:
        client = GmailClient()
        client.service.users().getProfile(userId='me').execute()
    except Exception as e:
        status = "degraded"
        issues.append(f"Gmail API: {type(e).__name__} - {str(e)}")

    # Google Sheets API
    try:
        sheet_id = os.getenv('GOOGLE_SHEETS_ID', '')
        sheets = SheetsClient()
        sheets.service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    except Exception as e:
        status = "degraded"
        issues.append(f"Sheets API: {type(e).__name__} - {str(e)}")

    # OpenAI client (init check only — no API call to avoid cost)
    try:
        ContentTransformer()
    except AITransformError as e:
        status = "degraded"
        issues.append(f"OpenAI: {str(e)}")
    except Exception as e:
        status = "degraded"
        issues.append(f"OpenAI: {type(e).__name__} - {str(e)}")

    response = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "issues": issues,
    }
    http_status = 200 if status == "healthy" else 503
    logger.info("Health check", extra={"status": status, "issues": issues})
    return jsonify(response), http_status


@webhook_bp.route('/gmail', methods=['POST'])
def gmail_webhook() -> Tuple[Dict[str, Any], int]:
    """
    Gmail Pub/Sub webhook endpoint.
    
    Validates incoming requests, decodes message payload, and triggers
    email processing pipeline asynchronously.
    
    Returns:
        tuple: (JSON response, HTTP status code)
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    source_ip = request.remote_addr
    
    log_step_start(
        "gmail_webhook",
        {
            "source_ip": source_ip,
            "user_agent": request.headers.get('User-Agent', 'Unknown')
        }
    )
    
    # Validate secret token
    token = request.headers.get('X-Goog-Channel-Token')
    
    if not token:
        logger.warning(
            f"Webhook request rejected - missing token",
            extra={
                "source_ip": source_ip,
                "reason": "Missing X-Goog-Channel-Token header"
            }
        )
        log_step_failure(
            "gmail_webhook",
            "Unauthorized - missing token",
            None
        )
        return jsonify({
            "error": "Unauthorized",
            "timestamp": timestamp,
            "reason": "Missing authentication token"
        }), 401
    
    if not validate_webhook_token(token):
        logger.warning(
            f"Webhook request rejected - invalid token",
            extra={
                "source_ip": source_ip,
                "reason": "Invalid token",
                "token_prefix": token[:8] + "..." if len(token) > 8 else token
            }
        )
        log_step_failure(
            "gmail_webhook",
            "Unauthorized - invalid token",
            None
        )
        return jsonify({
            "error": "Unauthorized",
            "timestamp": timestamp,
            "reason": "Invalid authentication token"
        }), 401
    
    # Parse request body
    try:
        request_data = request.get_json(force=True)
    except Exception as e:
        logger.error(
            f"Failed to parse request JSON",
            extra={
                "source_ip": source_ip,
                "error": str(e),
                "raw_data": request.get_data(as_text=True)[:500]
            }
        )
        log_step_failure(
            "gmail_webhook",
            f"Invalid JSON: {str(e)}",
            None
        )
        return jsonify({
            "error": "Invalid payload",
            "timestamp": timestamp,
            "details": "Request body is not valid JSON"
        }), 400
    
    # Decode Pub/Sub message
    try:
        decoded_message = decode_pubsub_message(request_data)
        email_address = decoded_message.get('email_address')
        history_id = decoded_message.get('history_id')
        
        logger.info(
            f"Valid webhook request received",
            extra={
                "source_ip": source_ip,
                "email_address": email_address,
                "history_id": history_id
            }
        )
        
    except ValueError as e:
        logger.error(
            f"Failed to decode Pub/Sub message",
            extra={
                "source_ip": source_ip,
                "error": str(e),
                "raw_payload": json.dumps(request_data)[:500]
            }
        )
        log_step_failure(
            "gmail_webhook",
            f"Malformed payload: {str(e)}",
            None
        )
        return jsonify({
            "error": "Invalid payload",
            "timestamp": timestamp,
            "details": str(e)
        }), 400
    
    # Queue email processing (asynchronous)
    # Note: In production, this should use a task queue (Celery, Cloud Tasks, etc.)
    # For now, we'll trigger synchronously but return immediately
    try:
        # Import here to avoid circular dependency
        from threading import Thread
        
        def process_async():
            """Process newsletter in background thread."""
            try:
                pipeline = NewsletterPipeline()
                # We need to fetch new messages using history API
                # For this implementation, we'll use the history_id
                pipeline.process_from_history(history_id, email_address)
            except Exception as e:
                logger.error(
                    f"Background processing failed",
                    extra={
                        "history_id": history_id,
                        "error": str(e)
                    },
                    exc_info=True
                )
        
        # Start background thread
        thread = Thread(target=process_async, daemon=True)
        thread.start()
        
        log_step_success(
            "gmail_webhook",
            0,  # Duration not measured for async
            f"Queued processing for history_id: {history_id}"
        )
        
        return jsonify({
            "status": "received",
            "timestamp": timestamp,
            "history_id": history_id,
            "email_address": email_address
        }), 200
        
    except Exception as e:
        logger.error(
            f"Failed to queue email processing",
            extra={
                "history_id": history_id,
                "error": str(e)
            },
            exc_info=True
        )
        log_step_failure(
            "gmail_webhook",
            f"Queue error: {str(e)}",
            None
        )
        return jsonify({
            "error": "Internal server error",
            "timestamp": timestamp,
            "details": "Failed to queue processing task"
        }), 500
