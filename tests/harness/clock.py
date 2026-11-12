import asyncio


class FakeClock:
    """Wall clock for tests: sleep advances time instantly."""

    def __init__(self, start_ms: int = 1_794_000_000_000):
        self.ms = start_ms
        self.slept_s = 0.0

    def now_ms(self) -> int:
        return self.ms

    async def sleep(self, seconds: float) -> None:
        self.slept_s += seconds
        self.ms += round(seconds * 1000)
        await asyncio.sleep(0)
