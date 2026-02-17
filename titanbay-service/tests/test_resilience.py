"""
Unit tests for resilience patterns — Circuit Breaker & retry with backoff.

Tests cover:
- CircuitBreaker state machine: CLOSED → OPEN → HALF_OPEN → CLOSED
- Fast-fail behaviour when circuit is open
- Automatic OPEN → HALF_OPEN transition after recovery timeout
- Success/failure recording
- CircuitBreakerError attributes
- get_status() health-check dict
- retry_with_backoff: retries, exhaustion, non-retryable passthrough
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.core.resilience import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    retry_with_backoff,
)

# ────────────────────────────────────────────────────────────────────────────
# CircuitBreakerError tests
# ────────────────────────────────────────────────────────────────────────────


class TestCircuitBreakerError:
    """Tests for the CircuitBreakerError exception class."""

    def test_attributes(self):
        err = CircuitBreakerError("db", 5.5)
        assert err.name == "db"
        assert err.retry_after == 5.5
        assert "db" in str(err)
        assert "OPEN" in str(err)

    def test_is_exception(self):
        err = CircuitBreakerError("db", 1.0)
        assert isinstance(err, Exception)


# ────────────────────────────────────────────────────────────────────────────
# CircuitBreaker tests
# ────────────────────────────────────────────────────────────────────────────


class TestCircuitBreakerClosed:
    """Tests for normal (CLOSED) operation."""

    @pytest.fixture()
    def cb(self):
        return CircuitBreaker(
            name="test",
            failure_threshold=3,
            recovery_timeout=1.0,
            expected_exceptions=(ValueError, ConnectionError),
        )

    @pytest.mark.asyncio
    async def test_successful_call(self, cb):
        func = AsyncMock(return_value="ok")
        result = await cb.call(func)
        assert result == "ok"
        func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_state_starts_closed(self, cb):
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_success_increments_counter(self, cb):
        func = AsyncMock(return_value="ok")
        await cb.call(func)
        assert cb._success_count == 1
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_failure_below_threshold_stays_closed(self, cb):
        func = AsyncMock(side_effect=ValueError("boom"))
        for _ in range(2):  # threshold is 3
            with pytest.raises(ValueError):
                await cb.call(func)
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 2


class TestCircuitBreakerOpen:
    """Tests for OPEN state behaviour."""

    @pytest.fixture()
    def cb(self):
        return CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=5.0,
            expected_exceptions=(ValueError,),
        )

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self, cb):
        func = AsyncMock(side_effect=ValueError("fail"))
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(func)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_raises_circuit_breaker_error(self, cb):
        func = AsyncMock(side_effect=ValueError("fail"))
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(func)

        with pytest.raises(CircuitBreakerError) as exc_info:
            await cb.call(func)
        assert exc_info.value.name == "test"
        assert exc_info.value.retry_after >= 0

    @pytest.mark.asyncio
    async def test_open_circuit_does_not_call_function(self, cb):
        fail_func = AsyncMock(side_effect=ValueError("fail"))
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail_func)

        success_func = AsyncMock(return_value="ok")
        with pytest.raises(CircuitBreakerError):
            await cb.call(success_func)
        success_func.assert_not_awaited()


class TestCircuitBreakerHalfOpen:
    """Tests for HALF_OPEN state and recovery."""

    @pytest.fixture()
    def cb(self):
        return CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.01,  # very short for testing
            expected_exceptions=(ValueError,),
        )

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, cb):
        func = AsyncMock(side_effect=ValueError("fail"))
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(func)
        assert cb._state == CircuitState.OPEN

        # Simulate recovery timeout by backdating the last failure time
        cb._last_failure_time = time.monotonic() - 1.0
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_successful_probe_closes_circuit(self, cb):
        fail_func = AsyncMock(side_effect=ValueError("fail"))
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail_func)

        cb._last_failure_time = time.monotonic() - 1.0  # trigger half-open

        success_func = AsyncMock(return_value="recovered")
        result = await cb.call(success_func)
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_failed_probe_reopens_circuit(self, cb):
        fail_func = AsyncMock(side_effect=ValueError("fail"))
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail_func)

        cb._last_failure_time = time.monotonic() - 1.0  # trigger half-open

        with pytest.raises(ValueError):
            await cb.call(fail_func)
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerNonExpected:
    """Tests for exceptions NOT in expected_exceptions."""

    @pytest.mark.asyncio
    async def test_unexpected_exception_passes_through(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=5.0,
            expected_exceptions=(ValueError,),
        )
        func = AsyncMock(side_effect=TypeError("not expected"))
        with pytest.raises(TypeError):
            await cb.call(func)
        # Should not affect failure count
        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerGetStatus:
    """Tests for get_status()."""

    def test_status_dict_keys(self):
        cb = CircuitBreaker(name="db", failure_threshold=5, recovery_timeout=30.0)
        status = cb.get_status()
        assert status["name"] == "db"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 5
        assert status["success_count"] == 0
        assert status["recovery_timeout_s"] == 30.0


# ────────────────────────────────────────────────────────────────────────────
# retry_with_backoff tests
# ────────────────────────────────────────────────────────────────────────────


class TestRetryWithBackoff:
    """Tests for the retry decorator."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            base_delay=0.001,
            jitter=False,
            retryable_exceptions=(ConnectionError,),
        )
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_exception(self):
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            base_delay=0.001,
            jitter=False,
            retryable_exceptions=(ConnectionError,),
        )
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("down")
            return "recovered"

        result = await fail_twice()
        assert result == "recovered"
        assert call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_raises(self):
        call_count = 0

        @retry_with_backoff(
            max_retries=2,
            base_delay=0.001,
            jitter=False,
            retryable_exceptions=(ConnectionError,),
        )
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("permanent failure")

        with pytest.raises(ConnectionError, match="permanent failure"):
            await always_fail()
        assert call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        call_count = 0

        @retry_with_backoff(
            max_retries=3,
            base_delay=0.001,
            jitter=False,
            retryable_exceptions=(ConnectionError,),
        )
        async def raise_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            await raise_value_error()
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_zero_retries_means_single_attempt(self):
        call_count = 0

        @retry_with_backoff(
            max_retries=0,
            base_delay=0.001,
            jitter=False,
            retryable_exceptions=(ConnectionError,),
        )
        async def fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            await fail()
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_delay_respects_max_delay(self):
        """Verify the delay doesn't exceed max_delay."""
        call_count = 0

        @retry_with_backoff(
            max_retries=5,
            base_delay=1.0,
            max_delay=2.0,
            jitter=False,
            retryable_exceptions=(ConnectionError,),
        )
        async def fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        # Patch asyncio.sleep to capture delays without actually sleeping
        with patch("app.core.resilience.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ConnectionError):
                await fail()
            # All delays should be <= max_delay (2.0)
            for call in mock_sleep.call_args_list:
                delay = call[0][0]
                assert delay <= 2.0
