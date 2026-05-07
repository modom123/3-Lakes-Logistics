"""Circuit breaker — stops hammering failing external services.

Usage:
    breaker = CircuitBreaker("stripe", failure_threshold=5, timeout=60)

    @breaker.call
    async def charge_driver():
        return await stripe.transfer.create(...)

States:
  CLOSED  — normal, requests pass through
  OPEN    — service is down, requests fail fast (returns fallback)
  HALF_OPEN — testing if service recovered
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable

from .logging_service import get_logger

log = get_logger(__name__)


class State(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: int = 60,
        success_threshold: int = 2,
    ):
        self.name              = name
        self.failure_threshold = failure_threshold
        self.timeout           = timeout          # seconds before retry
        self.success_threshold = success_threshold

        self._state          = State.CLOSED
        self._failure_count  = 0
        self._success_count  = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> State:
        if self._state == State.OPEN:
            if time.time() - (self._opened_at or 0) > self.timeout:
                log.info("Circuit [%s] → HALF_OPEN (testing recovery)", self.name)
                self._state = State.HALF_OPEN
        return self._state

    def _on_success(self):
        if self.state == State.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                log.info("Circuit [%s] → CLOSED (recovered)", self.name)
                self._state         = State.CLOSED
                self._failure_count = 0
                self._success_count = 0
        else:
            self._failure_count = 0

    def _on_failure(self, exc: Exception):
        self._failure_count += 1
        self._success_count = 0
        log.warning("Circuit [%s] failure %d/%d: %s",
                    self.name, self._failure_count, self.failure_threshold, exc)
        if self._failure_count >= self.failure_threshold:
            log.error("Circuit [%s] → OPEN (too many failures)", self.name)
            self._state     = State.OPEN
            self._opened_at = time.time()

    def call(self, fn: Callable) -> Callable:
        """Decorator — wraps an async function with circuit breaker."""
        async def wrapper(*args, **kwargs) -> Any:
            if self.state == State.OPEN:
                raise CircuitOpenError(
                    f"Service '{self.name}' is temporarily unavailable. "
                    f"Retry in {int(self.timeout - (time.time() - self._opened_at))}s."
                )
            try:
                result = await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) \
                         else fn(*args, **kwargs)
                self._on_success()
                return result
            except CircuitOpenError:
                raise
            except Exception as exc:
                self._on_failure(exc)
                raise
        return wrapper

    def status(self) -> dict:
        return {
            "name":           self.name,
            "state":          self.state.value,
            "failure_count":  self._failure_count,
            "opened_at":      self._opened_at,
        }


class CircuitOpenError(Exception):
    """Raised when circuit is OPEN and request is rejected."""
    pass


# ── Global breakers for each external service ─────────────────────────────────
breakers = {
    "stripe":    CircuitBreaker("stripe",    failure_threshold=3, timeout=60),
    "supabase":  CircuitBreaker("supabase",  failure_threshold=5, timeout=30),
    "twilio":    CircuitBreaker("twilio",    failure_threshold=5, timeout=60),
    "vapi":      CircuitBreaker("vapi",      failure_threshold=3, timeout=120),
    "firebase":  CircuitBreaker("firebase",  failure_threshold=5, timeout=60),
    "dat":       CircuitBreaker("dat",       failure_threshold=3, timeout=300),
    "truckstop": CircuitBreaker("truckstop", failure_threshold=3, timeout=300),
    "samsara":   CircuitBreaker("samsara",   failure_threshold=5, timeout=120),
    "motive":    CircuitBreaker("motive",    failure_threshold=5, timeout=120),
}


def get_breaker(name: str) -> CircuitBreaker:
    if name not in breakers:
        breakers[name] = CircuitBreaker(name)
    return breakers[name]
