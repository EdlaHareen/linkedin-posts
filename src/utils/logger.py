"""
Structured JSON logger for Newsletter to LinkedIn Post Automation.

Provides JSON-formatted logging with timestamps, step tracking, and metadata.
Supports pipeline step instrumentation with start/success/failure helpers.
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as JSON objects.
    
    Format:
    {
        "timestamp": "2025-01-24T12:00:00.000Z",
        "level": "INFO",
        "step": "email_fetch",
        "status": "success",
        "duration_ms": 1234,
        "metadata": {...},
        "message": "...",
        "error": "...",
        "stack_trace": "..."
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.
        
        Args:
            record: LogRecord instance from Python logging
            
        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        # Add custom fields from extra parameter
        if hasattr(record, "step"):
            log_data["step"] = record.step
        
        if hasattr(record, "status"):
            log_data["status"] = record.status
            
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
            
        if hasattr(record, "metadata"):
            log_data["metadata"] = record.metadata
            
        if hasattr(record, "error"):
            log_data["error"] = record.error
            
        # Add exception info if present
        if record.exc_info:
            log_data["stack_trace"] = self.formatException(record.exc_info)
        elif hasattr(record, "stack_trace"):
            log_data["stack_trace"] = record.stack_trace
            
        return json.dumps(log_data, default=str)


class PipelineLogger:
    """
    High-level logger interface for pipeline step tracking.
    
    Provides convenience methods for logging step lifecycle:
    - log_step_start: Mark beginning of pipeline step
    - log_step_success: Mark successful completion with metrics
    - log_step_failure: Mark failure with error details
    """
    
    def __init__(self, logger_name: str = "newsletter_pipeline"):
        """
        Initialize pipeline logger.
        
        Args:
            logger_name: Name for the logger instance
        """
        self.logger = logging.getLogger(logger_name)
        self._step_start_times: Dict[str, datetime] = {}

    # Standard logging delegation methods
    def info(self, msg, *args, **kwargs):
        """Delegate to underlying logger.info."""
        self.logger.info(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Delegate to underlying logger.error."""
        self.logger.error(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """Delegate to underlying logger.warning."""
        self.logger.warning(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        """Delegate to underlying logger.debug."""
        self.logger.debug(msg, *args, **kwargs)
    
    def log_step_start(self, step_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Log the start of a pipeline step.
        
        Args:
            step_name: Identifier for the step (e.g., "email_fetch", "ai_transform")
            metadata: Additional context data (sender, message_id, etc.)
        """
        self._step_start_times[step_name] = datetime.utcnow()
        
        self.logger.info(
            f"Starting step: {step_name}",
            extra={
                "step": step_name,
                "status": "started",
                "metadata": metadata or {}
            }
        )
    
    def log_step_success(
        self,
        step_name: str,
        output_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log successful completion of a pipeline step.
        
        Args:
            step_name: Identifier for the step
            output_summary: Brief description of output (e.g., "Generated 280-char post")
            metadata: Additional result data
        """
        duration_ms = self._calculate_duration(step_name)
        
        message = f"Step completed: {step_name}"
        if output_summary:
            message += f" - {output_summary}"
        
        log_metadata = metadata or {}
        if output_summary:
            log_metadata["output_summary"] = output_summary
        
        self.logger.info(
            message,
            extra={
                "step": step_name,
                "status": "success",
                "duration_ms": duration_ms,
                "metadata": log_metadata
            }
        )
        
        # Clean up start time
        self._step_start_times.pop(step_name, None)
    
    def log_step_failure(
        self,
        step_name: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        include_stack_trace: bool = True
    ) -> None:
        """
        Log failure of a pipeline step.
        
        Args:
            step_name: Identifier for the step
            error: Exception that caused the failure
            context: Additional context about the failure
            include_stack_trace: Whether to include full stack trace
        """
        duration_ms = self._calculate_duration(step_name)
        
        error_type = type(error).__name__
        error_message = str(error)
        
        log_metadata = context or {}
        log_metadata.update({
            "error_type": error_type,
            "error_message": error_message
        })
        
        extra = {
            "step": step_name,
            "status": "failed",
            "duration_ms": duration_ms,
            "error": f"{error_type}: {error_message}",
            "metadata": log_metadata
        }
        
        if include_stack_trace:
            extra["stack_trace"] = traceback.format_exc()
        
        self.logger.error(
            f"Step failed: {step_name} - {error_type}: {error_message}",
            extra=extra
        )
        
        # Clean up start time
        self._step_start_times.pop(step_name, None)
    
    def log_warning(
        self,
        step_name: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a warning during a pipeline step.
        
        Args:
            step_name: Identifier for the step
            message: Warning message
            metadata: Additional context
        """
        self.logger.warning(
            message,
            extra={
                "step": step_name,
                "status": "warning",
                "metadata": metadata or {}
            }
        )
    
    def log_info(
        self,
        message: str,
        step_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log general information.
        
        Args:
            message: Info message
            step_name: Optional step identifier
            metadata: Additional context
        """
        extra = {"metadata": metadata or {}}
        if step_name:
            extra["step"] = step_name
        
        self.logger.info(message, extra=extra)
    
    def log_critical(
        self,
        message: str,
        error: Optional[Exception] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log critical error that requires immediate attention.
        
        Args:
            message: Critical error message
            error: Optional exception
            metadata: Additional context
        """
        extra = {"metadata": metadata or {}}
        
        if error:
            extra["error"] = f"{type(error).__name__}: {str(error)}"
            extra["stack_trace"] = traceback.format_exc()
        
        self.logger.critical(message, extra=extra)
    
    def _calculate_duration(self, step_name: str) -> int:
        """
        Calculate duration in milliseconds since step start.
        
        Args:
            step_name: Identifier for the step
            
        Returns:
            Duration in milliseconds, or 0 if start time not found
        """
        start_time = self._step_start_times.get(step_name)
        if not start_time:
            return 0
        
        duration = datetime.utcnow() - start_time
        return int(duration.total_seconds() * 1000)


def get_logger(name: str = "newsletter_pipeline") -> PipelineLogger:
    """
    Get or create a PipelineLogger instance.
    
    Args:
        name: Logger name
        
    Returns:
        PipelineLogger instance
    """
    return PipelineLogger(name)


# Module-level convenience functions used by multiple modules
_default_logger = PipelineLogger("newsletter_pipeline")


def log_step_start(step_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Module-level convenience wrapper for PipelineLogger.log_step_start."""
    _default_logger.log_step_start(step_name, metadata)


def log_step_success(
    step_name: str,
    output_summary: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Module-level convenience wrapper for PipelineLogger.log_step_success."""
    _default_logger.log_step_success(step_name, output_summary, metadata)


def log_step_failure(
    step_name: str,
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    include_stack_trace: bool = True
) -> None:
    """Module-level convenience wrapper for PipelineLogger.log_step_failure."""
    _default_logger.log_step_failure(step_name, error, context, include_stack_trace)
