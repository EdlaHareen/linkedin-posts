"""
Tests for main application initialization.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.main import create_app


def test_create_app_success(mock_env_vars):
    """Test successful app creation with all required env vars."""
    app = create_app()
    
    assert app is not None
    assert app.name == "src.main"


def test_create_app_missing_env_vars(monkeypatch):
    """Test app creation fails with missing environment variables."""
    # Clear all env vars
    for var in [
        "GMAIL_CREDENTIALS_PATH",
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GOOGLE_SHEETS_ID",
        "WEBHOOK_SECRET_TOKEN",
    ]:
        monkeypatch.delenv(var, raising=False)
    
    with pytest.raises(EnvironmentError) as exc_info:
        create_app()
    
    assert "Missing required environment variables" in str(exc_info.value)


def test_create_app_empty_allowed_senders(mock_env_vars, monkeypatch, caplog):
    """Test app logs warning when ALLOWED_SENDERS is empty."""
    monkeypatch.setenv("ALLOWED_SENDERS", "")
    
    app = create_app()
    
    assert app is not None
    # Check that warning was logged
    assert any(
        "No allowed senders configured" in record.message
        for record in caplog.records
    )


def test_create_app_registers_blueprints(mock_env_vars):
    """Test that Flask blueprints are registered."""
    app = create_app()
    
    # Check that webhook blueprint is registered
    assert any(bp.name == "webhook" for bp in app.blueprints.values())
