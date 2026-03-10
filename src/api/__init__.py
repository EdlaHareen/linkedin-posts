"""
API module initialization.
Exports Flask application factory and route blueprints.
"""

from flask import Flask
from src.utils.logger import get_logger
import os

logger = get_logger(__name__)


def create_app():
    """
    Flask application factory.
    
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['JSON_SORT_KEYS'] = False
    
    # Register blueprints
    from src.api.webhook import webhook_bp
    app.register_blueprint(webhook_bp)
    
    logger.info("Flask application created successfully")
    
    return app


__all__ = ['create_app']
