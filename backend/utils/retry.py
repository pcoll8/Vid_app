"""
Retry Decorator with Exponential Backoff
Automatic retry logic for transient failures
"""

import asyncio
import functools
import random
from typing import Type, Tuple, Optional, Callable, Any

from .logger import get_logger
from .exceptions import ViralClipError, RateLimitError

logger = get_logger()


def retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Async retry decorator with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called on each retry (exception, attempt)
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except retryable_exceptions as e:
                    last_exception = e
                    
                    # Check for rate limit with specific retry time
                    if isinstance(e, RateLimitError) and e.details.get("retry_after"):
                        delay = e.details["retry_after"]
                    else:
                        # Calculate exponential backoff
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        
                        if jitter:
                            delay = delay * (0.5 + random.random())
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {delay:.1f}s: {str(e)[:100]}"
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}"
                        )
                        raise
                        
                except Exception as e:
                    # Non-retryable exception
                    logger.error(f"Non-retryable error in {func.__name__}: {e}")
                    raise
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_sync(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Sync retry decorator with exponential backoff
    """
    import time
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except retryable_exceptions as e:
                    last_exception = e
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    if jitter:
                        delay = delay * (0.5 + random.random())
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {delay:.1f}s: {str(e)[:100]}"
                        )
                        time.sleep(delay)
                    else:
                        raise
                        
                except Exception:
                    raise
            
            raise last_exception
        
        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern for protecting against cascading failures
    
    States:
        CLOSED: Normal operation, requests pass through
        OPEN: Failures exceeded threshold, requests fail immediately
        HALF_OPEN: Testing if service recovered
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "CLOSED"
    
    @property
    def state(self) -> str:
        if self._state == "OPEN":
            # Check if recovery timeout has passed
            import time
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "HALF_OPEN"
        return self._state
    
    def record_success(self):
        """Record a successful call"""
        self._failure_count = 0
        self._state = "CLOSED"
    
    def record_failure(self):
        """Record a failed call"""
        import time
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")
    
    def can_execute(self) -> bool:
        """Check if a call can proceed"""
        return self.state != "OPEN"
    
    def __call__(self, func):
        """Use as a decorator"""
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not self.can_execute():
                raise ViralClipError(
                    message="Service temporarily unavailable (circuit breaker open)",
                    code="CIRCUIT_BREAKER_OPEN",
                    recoverable=True,
                    recovery_hint=f"Wait {self.recovery_timeout}s and try again"
                )
            
            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except self.expected_exception as e:
                self.record_failure()
                raise
        
        return wrapper
