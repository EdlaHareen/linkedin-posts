"""
Main application entry point.
Initializes Flask server and starts the webhook listener.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

# Add src directory and project root to Python path
src_path = Path(__file__).parent
project_root = src_path.parent
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

# Import after path setup
from api.webhook import webhook_bp
from config.logging_config import configure_logging_from_env as setup_logging
from utils.logger import get_logger

# Initialize logging
setup_logging()
logger = get_logger(__name__)


def create_app() -> Flask:
    """
    Create and configure Flask application.
    
    Returns:
        Configured Flask app instance
    """
    app = Flask(__name__)
    
    # Register blueprints
    app.register_blueprint(webhook_bp)
    
    # Validate required environment variables
    required_vars = [
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GOOGLE_SHEETS_ID",
        "WEBHOOK_SECRET_TOKEN",
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(
            "Missing required environment variables",
            extra={
                "step": "app_initialization",
                "status": "failed",
                "metadata": {"missing_vars": missing_vars}
            }
        )
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )
    
    # Validate ALLOWED_SENDERS
    allowed_senders = os.getenv("ALLOWED_SENDERS", "").strip()
    if not allowed_senders:
        logger.warning(
            "No allowed senders configured - all emails will be rejected",
            extra={
                "step": "app_initialization",
                "status": "warning",
                "metadata": {"config": "ALLOWED_SENDERS"}
            }
        )
    
    logger.info(
        "Application initialized successfully",
        extra={
            "step": "app_initialization",
            "status": "success",
            "metadata": {
                "allowed_senders": allowed_senders.split(",") if allowed_senders else [],
                "sheets_id": os.getenv("GOOGLE_SHEETS_ID"),
            }
        }
    )
    
    return app


def main():
    """Main application entry point."""
    try:
        app = create_app()
        
        # Get configuration from environment
        host = os.getenv("FLASK_HOST", "0.0.0.0")
        port = int(os.getenv("FLASK_PORT", "5000"))
        debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
        
        logger.info(
            "Starting Flask server",
            extra={
                "step": "server_start",
                "status": "started",
                "metadata": {
                    "host": host,
                    "port": port,
                    "debug": debug
                }
            }
        )
        
        app.run(host=host, port=port, debug=debug)
        
    except Exception as e:
        logger.error(
            "Application startup failed",
            extra={
                "step": "server_start",
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
