"""
Resilience patterns for production reliability.

Implements industry-standard fault-tolerance mechanisms:

1. **Circuit Breaker** — Prevents cascading failures by short-circuiting
   requests to a failing dependency (e.g. database) after a threshold of
   consecutive failures.  After a cool down period, a single "probe" request
   is allowed through to test recovery.

   States:
   - CLOSED  → Normal operation; failures are counted.
   - OPEN    → All calls fail immediately (fast-fail); avoids hammering a
               dead service, giving it time to recover.
   - HALF_OPEN → A single probe call is allowed; if it succeeds the circuit
                 closes, otherwise it re-opens.

2. **Retry with Exponential Backoff** — Retries transient failures (e.g.
   connection timeouts, deadlocks) with increasing delays and optional jitter
   to avoid thundering-herd effects when many replicas retry simultaneously.

Both patterns are implemented as decorators for clean, non-invasive
integration with existing service and repository methods.
"""

import asyncio
import functools
import logging
import random
import time
from enum import Enum
from typing import Any, Callable, Optional, Tuple, Type

from app.core.config import settings

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Circuit Breaker
# ────────────────────────────────────────────────────────────────────────────


class CircuitState(str, Enum):
    """Possible states of a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is OPEN — failing fast. "
            f"Retry after {retry_after:.1f}s."
        )


class CircuitBreaker:
    """
    Thread-safe async circuit breaker.

    Parameters
    ----------
    name : str
        Human-readable identifier (e.g. ``"database"``, ``"external-api"``).
    failure_threshold : int
        Number of consecutive failures before the circuit opens.
    recovery_timeout : float
        Seconds to wait in OPEN state before allowing a probe (HALF_OPEN).
    expected_exceptions : tuple
        Exception types that count as failures. All others pass through
        without affecting the circuit state.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._success_count = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state, with automatic OPEN → HALF_OPEN transition."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit '%s' → HALF_OPEN (recovery timeout elapsed after %.1fs)",
                    self.name,
                    elapsed,
                )
        return self._state

    def _record_success(self) -> None:
        """Reset failure counters on a successful call."""
        if self._state != CircuitState.CLOSED:
            logger.info(
                "Circuit '%s' → CLOSED (successful probe after %d failures)",
                self.name,
                self._failure_count,
            )
        self._failure_count = 0
        self._success_count += 1
        self._state = CircuitState.CLOSED

    def _record_failure(self) -> None:
        """Increment failure count; open circuit if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.error(
                "Circuit '%s' → OPEN (failure #%d reached threshold %d). "
                "Calls will fast-fail for %.1fs.",
                self.name,
                self._failure_count,
                self.failure_threshold,
                self.recovery_timeout,
            )
        else:
            logger.warning(
                "Circuit '%s' failure #%d/%d",
                self.name,
                self._failure_count,
                self.failure_threshold,
            )

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute ``func`` through the circuit breaker.

        Raises :class:`CircuitBreakerError` if the circuit is OPEN.
        """
        state = self.state  # triggers OPEN → HALF_OPEN check

        if state == CircuitState.OPEN:
            retry_after = self.recovery_timeout - (
                time.monotonic() - self._last_failure_time
            )
            raise CircuitBreakerError(self.name, max(retry_after, 0))

        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except self.expected_exceptions as exc:  # noqa: F841
            self._record_failure()
            raise

    def get_status(self) -> dict:
        """Return a dict suitable for health-check / monitoring endpoints."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "success_count": self._success_count,
            "recovery_timeout_s": self.recovery_timeout,
        }


# ── Global circuit breaker instance for database operations ──
db_circuit_breaker = CircuitBreaker(
    name="database",
    failure_threshold=settings.CB_FAILURE_THRESHOLD,
    recovery_timeout=settings.CB_RECOVERY_TIMEOUT,
    expected_exceptions=(
        ConnectionError,
        OSError,
        TimeoutError,
    ),
)


# ────────────────────────────────────────────────────────────────────────────
# Retry with Exponential Backoff
# ────────────────────────────────────────────────────────────────────────────


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        OSError,
        TimeoutError,
    ),
) -> Callable:
    """
    Decorator: retry an async function with exponential backoff.

    Parameters
    ----------
    max_retries : int
        Maximum number of retry attempts (0 = no retries, just the initial call).
    base_delay : float
        Initial delay in seconds before the first retry. Doubles each attempt.
    max_delay : float
        Cap on the delay between retries.
    jitter : bool
        If True, adds random jitter (0–50% of delay) to prevent thundering herd.
    retryable_exceptions : tuple
        Only these exception types trigger a retry. All others propagate immediately.

    Example::

        @retry_with_backoff(max_retries=3, base_delay=1.0)
        async def get_data():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            delay = base_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        actual_delay = min(delay, max_delay)
                        if jitter:
                            actual_delay += random.uniform(0, actual_delay * 0.5)
                        logger.warning(
                            "Retry %d/%d for %s after %.2fs — %s: %s",
                            attempt + 1,
                            max_retries,
                            func.__qualname__,
                            actual_delay,
                            type(exc).__name__,
                            exc,
                        )
                        await asyncio.sleep(actual_delay)
                        delay *= 2  # exponential backoff
                    else:
                        logger.error(
                            "All %d retries exhausted for %s — %s: %s",
                            max_retries,
                            func.__qualname__,
                            type(exc).__name__,
                            exc,
                        )

            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
