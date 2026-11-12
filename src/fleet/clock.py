import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    """Wall clock; injected so tests control time (spec §7)."""

    def now_ms(self) -> int: ...
    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now_ms(self) -> int:
        return time.time_ns() // 1_000_000

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
