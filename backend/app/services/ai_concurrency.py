from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from weakref import WeakKeyDictionary

from app.core.config import settings
from app.core.logger import logger


class AIConcurrencyTimeoutError(RuntimeError):
    """Raised when an AI request cannot enter the configured concurrency window."""


@dataclass
class AIConcurrencyLease:
    operation: str
    model: str
    limit: int
    queue_wait_ms: int
    active_at_acquire: int
    queued_ahead: int
    held_ms: int = 0
    timed_out: bool = False

    def as_dict(self) -> dict[str, int | str | bool]:
        return {
            "operation": self.operation,
            "model": self.model,
            "limit": self.limit,
            "queue_wait_ms": self.queue_wait_ms,
            "active_at_acquire": self.active_at_acquire,
            "queued_ahead": self.queued_ahead,
            "held_ms": self.held_ms,
            "timed_out": self.timed_out,
        }


@dataclass
class _LoopGate:
    semaphore: asyncio.Semaphore
    active: int = 0
    waiting: int = 0


_registry_lock = Lock()
_loop_gates: WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopGate] = WeakKeyDictionary()


def _current_gate() -> _LoopGate:
    loop = asyncio.get_running_loop()
    with _registry_lock:
        gate = _loop_gates.get(loop)
        if gate is None:
            gate = _LoopGate(asyncio.Semaphore(settings.MAX_CONCURRENCY))
            _loop_gates[loop] = gate
        return gate


@asynccontextmanager
async def ai_concurrency_slot(
    operation: str,
    model: str,
    *,
    metrics_sink: dict | None = None,
) -> AsyncIterator[AIConcurrencyLease]:
    gate = _current_gate()
    queued_ahead = gate.waiting
    gate.waiting += 1
    waiting_started_at = perf_counter()
    acquired = False
    try:
        try:
            await asyncio.wait_for(
                gate.semaphore.acquire(),
                timeout=settings.AI_CONCURRENCY_WAIT_TIMEOUT_SECONDS,
            )
            acquired = True
        except asyncio.TimeoutError as error:
            wait_ms = round((perf_counter() - waiting_started_at) * 1000)
            if metrics_sink is not None:
                metrics_sink["concurrency"] = {
                    "operation": operation,
                    "model": model,
                    "limit": settings.MAX_CONCURRENCY,
                    "queue_wait_ms": wait_ms,
                    "active_at_acquire": gate.active,
                    "queued_ahead": queued_ahead,
                    "held_ms": 0,
                    "timed_out": True,
                }
            logger.warning(
                f"AI concurrency queue timed out | operation={operation} | "
                f"model={model} | wait_ms={wait_ms} | limit={settings.MAX_CONCURRENCY}"
            )
            raise AIConcurrencyTimeoutError(
                f"AI concurrency queue exceeded "
                f"{settings.AI_CONCURRENCY_WAIT_TIMEOUT_SECONDS:g} seconds"
            ) from error
    finally:
        gate.waiting = max(0, gate.waiting - 1)

    gate.active += 1
    lease = AIConcurrencyLease(
        operation=operation,
        model=model,
        limit=settings.MAX_CONCURRENCY,
        queue_wait_ms=round((perf_counter() - waiting_started_at) * 1000),
        active_at_acquire=gate.active,
        queued_ahead=queued_ahead,
    )
    if metrics_sink is not None:
        metrics_sink["concurrency"] = lease.as_dict()
    logger.info(
        f"AI concurrency slot acquired | operation={operation} | model={model} | "
        f"wait_ms={lease.queue_wait_ms} | active={lease.active_at_acquire}/"
        f"{lease.limit} | queued_ahead={lease.queued_ahead}"
    )
    held_started_at = perf_counter()
    try:
        yield lease
    finally:
        lease.held_ms = round((perf_counter() - held_started_at) * 1000)
        if metrics_sink is not None:
            metrics_sink["concurrency"] = lease.as_dict()
        gate.active = max(0, gate.active - 1)
        if acquired:
            gate.semaphore.release()
