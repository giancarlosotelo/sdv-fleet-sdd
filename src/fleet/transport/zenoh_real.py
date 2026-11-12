import asyncio
import json

import zenoh

from fleet.transport import TransportUnavailable
from fleet.transport.zenoh import KeyHandler

DEFAULT_ENDPOINT = "tcp/127.0.0.1:7447"


class RealZenoh:
    """Zenoh client session against a router (deploy/compose.yaml)."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT):
        conf = zenoh.Config()
        conf.insert_json5("mode", '"client"')
        conf.insert_json5("connect/endpoints", json.dumps([endpoint]))
        conf.insert_json5("scouting/multicast/enabled", "false")
        try:
            self._session = zenoh.open(conf)
        except zenoh.ZError as ex:
            raise TransportUnavailable(f"zenoh router {endpoint}: {ex}") from ex
        self._subs: list = []
        self._tasks: list[asyncio.Task] = []

    async def put(self, key: str, payload: bytes) -> None:
        # Client-mode puts don't fail while the router is gone; check the link so the outbox buffers.
        if not list(self._session.info.routers_zid()):
            raise TransportUnavailable("zenoh router not connected")
        self._session.put(key, payload)

    async def subscribe(self, key_expr: str, handler: KeyHandler) -> None:
        loop, queue = asyncio.get_running_loop(), asyncio.Queue()

        def on_sample(sample: zenoh.Sample) -> None:
            item = (str(sample.key_expr), sample.payload.to_bytes())
            loop.call_soon_threadsafe(queue.put_nowait, item)

        async def drain() -> None:
            while True:
                await handler(*await queue.get())

        self._tasks.append(asyncio.create_task(drain()))
        self._subs.append(self._session.declare_subscriber(key_expr, on_sample))

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._session.close()
