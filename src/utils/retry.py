"""
Retry logic with exponential backoff for external API calls.

This module provides a decorator that automatically retries failed API calls
with exponential backoff, distinguishing between retryable and non-retryable errors.
"""

import time
import functools
from typing import Callable, Type, Tuple, Any
from requests.exceptions import ConnectionError, Timeout
from http.client import HTTPException


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""
    pass


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        TimeoutError,
        ConnectionError,
        Timeout,
        HTTPException,
    )
):
    """
    Decorator that retries a function with exponential backoff on retryable errors.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds before first retry (default: 2.0)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)
        retryable_exceptions: Tuple of exception types that should trigger retries
        
    Returns:
        Decorated function with retry logic
        
    Example:
        @retry_with_backoff(max_attempts=3, base_delay=2)
        def call_external_api():
            # API call logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            import logging
            logger = logging.getLogger(__name__)
            function_name = func.__name__
            
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    if attempt > 1:
                        logger.info(
                            f"Retry attempt {attempt}/{max_attempts} for {function_name}"
                        )
                    
                    result = func(*args, **kwargs)
                    
                    if attempt > 1:
                        logger.info(
                            f"Retry successful on attempt {attempt} for {function_name}"
                        )
                    
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    # Check if error is retryable
                    is_retryable = _is_retryable_error(e, retryable_exceptions)
                    
                    if not is_retryable:
                        logger.error(
                            f"Non-retryable error in {function_name}: {type(e).__name__} - {str(e)}"
                        )
                        raise
                    
                    # If this was the last attempt, don't delay
                    if attempt >= max_attempts:
                        logger.error(
                            f"All retry attempts failed for {function_name} "
                            f"after {max_attempts} attempts"
                        )
                        break
                    
                    # Calculate delay with exponential backoff
                    delay = base_delay * (backoff_multiplier ** (attempt - 1))
                    
                    logger.warning(
                        f"Retryable error in {function_name} (attempt {attempt}/{max_attempts}): "
                        f"{type(e).__name__} - {str(e)}. Retrying after {delay}s delay"
                    )
                    
                    time.sleep(delay)
            
            # All retries exhausted
            raise RetryExhaustedError(
                f"All {max_attempts} retry attempts failed for {function_name}"
            ) from last_exception
        
        return wrapper
    return decorator


def _is_retryable_error(
    exception: Exception,
    retryable_exceptions: Tuple[Type[Exception], ...]
) -> bool:
    """
    Determine if an error should trigger retry logic.
    
    Args:
        exception: The exception that was raised
        retryable_exceptions: Tuple of exception types that are retryable
        
    Returns:
        True if the error is retryable, False otherwise
    """
    # Check if exception is an instance of any retryable exception type
    if isinstance(exception, retryable_exceptions):
        return True
    
    # Special handling for HTTP errors
    if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
        status_code = exception.response.status_code
        
        # Non-retryable HTTP status codes (client errors)
        non_retryable_codes = {400, 401, 403, 404, 405, 409, 410, 422}
        if status_code in non_retryable_codes:
            return False
        
        # Retryable HTTP status codes (server errors and rate limiting)
        retryable_codes = {429, 500, 502, 503, 504}
        if status_code in retryable_codes:
            return True
    
    # Check for specific error messages that indicate retryable conditions
    error_message = str(exception).lower()
    retryable_keywords = [
        'timeout',
        'connection',
        'network',
        'temporarily unavailable',
        'rate limit',
        'too many requests'
    ]
    
    for keyword in retryable_keywords:
        if keyword in error_message:
            return True
    
    return False


def retry_async_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        TimeoutError,
        ConnectionError,
        Timeout,
        HTTPException,
    )
):
    """
    Async version of retry_with_backoff decorator.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds before first retry (default: 2.0)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)
        retryable_exceptions: Tuple of exception types that should trigger retries
        
    Returns:
        Decorated async function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            import asyncio
            import logging
            
            logger = logging.getLogger(__name__)
            function_name = func.__name__
            
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    if attempt > 1:
                        logger.info(
                            f"Retry attempt {attempt}/{max_attempts} for {function_name}"
                        )
                    
                    result = await func(*args, **kwargs)
                    
                    if attempt > 1:
                        logger.info(
                            f"Retry successful on attempt {attempt} for {function_name}"
                        )
                    
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    is_retryable = _is_retryable_error(e, retryable_exceptions)
                    
                    if not is_retryable:
                        logger.error(
                            f"Non-retryable error in {function_name}: {type(e).__name__} - {str(e)}"
                        )
                        raise
                    
                    if attempt >= max_attempts:
                        logger.error(
                            f"All retry attempts failed for {function_name} "
                            f"after {max_attempts} attempts"
                        )
                        break
                    
                    delay = base_delay * (backoff_multiplier ** (attempt - 1))
                    
                    logger.warning(
                        f"Retryable error in {function_name} (attempt {attempt}/{max_attempts}): "
                        f"{type(e).__name__} - {str(e)}. Retrying after {delay}s delay"
                    )
                    
                    await asyncio.sleep(delay)
            
            raise RetryExhaustedError(
                f"All {max_attempts} retry attempts failed for {function_name}"
            ) from last_exception
        
        return wrapper
    return decorator


class RetryConfig:
    """Configuration class for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 2.0,
        backoff_multiplier: float = 2.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = None
    ):
        """
        Initialize retry configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Initial delay in seconds before first retry
            backoff_multiplier: Multiplier for exponential backoff
            retryable_exceptions: Tuple of exception types that should trigger retries
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.backoff_multiplier = backoff_multiplier
        self.retryable_exceptions = retryable_exceptions or (
            TimeoutError,
            ConnectionError,
            Timeout,
            HTTPException,
        )
    
    def create_decorator(self):
        """Create a retry decorator with this configuration."""
        return retry_with_backoff(
            max_attempts=self.max_attempts,
            base_delay=self.base_delay,
            backoff_multiplier=self.backoff_multiplier,
            retryable_exceptions=self.retryable_exceptions
        )
