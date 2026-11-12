import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable

from fleet.clock import Clock
from fleet.transport import TransportUnavailable

log = logging.getLogger(__name__)
Send = Callable[[str, bytes], Awaitable[None]]


class Outbox:
    """Sends now if it can; otherwise buffers and retries with exponential backoff (spec REQ-074).

    Buffered: the last `buffer_size` ordinary messages, plus only the latest message per `latest_key`.
    """

    def __init__(
        self,
        send: Send,
        clock: Clock,
        buffer_size: int,
        base_backoff_s: float = 0.5,
        max_backoff_s: float = 8.0,
    ):
        self._send, self._clock = send, clock
        self._base, self._max = base_backoff_s, max_backoff_s
        self._queue: deque[tuple[str, bytes]] = deque(maxlen=buffer_size)
        self._latest: dict[str, tuple[str, bytes]] = {}
        self._wake = asyncio.Event()
        self.dropped = 0

    @property
    def pending(self) -> int:
        return len(self._queue) + len(self._latest)

    async def submit(self, dest: str, payload: bytes, latest_key: str | None = None) -> None:
        if not self.pending:
            try:
                await self._send(dest, payload)
                return
            except TransportUnavailable as ex:
                log.warning("send to %s failed, buffering: %s", dest, ex)
        if latest_key is not None:
            self._latest[latest_key] = (dest, payload)
        else:
            if len(self._queue) == self._queue.maxlen:
                self.dropped += 1
            self._queue.append((dest, payload))
        self._wake.set()

    async def run(self) -> None:
        backoff = self._base
        while True:
            await self._wake.wait()
            try:
                while self._latest:
                    key, (dest, payload) = next(iter(self._latest.items()))
                    await self._send(dest, payload)
                    if self._latest.get(key) == (dest, payload):
                        del self._latest[key]
                while self._queue:
                    await self._send(*self._queue[0])
                    self._queue.popleft()
                self._wake.clear()
                backoff = self._base
            except TransportUnavailable:
                await self._clock.sleep(backoff)
                backoff = min(backoff * 2, self._max)
