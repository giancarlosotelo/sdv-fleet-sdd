import asyncio

from contracts import HAZARD_KEYS, HAZARD_TOPIC, TELEMETRY_KEYS, TELEMETRY_TOPIC
from fleet.clock import Clock
from fleet.transport.outbox import Outbox
from fleet.transport.pubsub import PubSub
from fleet.transport.zenoh import Zenoh


class Bridge:
    """Forwards every Zenoh message to Pub/Sub unchanged (spec REQ-073)."""

    def __init__(self, zenoh: Zenoh, pubsub: PubSub, clock: Clock, buffer_size: int):
        self._zenoh = zenoh
        self.outbox = Outbox(pubsub.publish, clock, buffer_size)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self.outbox.run())

        async def on_telemetry(key: str, payload: bytes) -> None:
            await self.outbox.submit(TELEMETRY_TOPIC, payload)

        async def on_hazard(key: str, payload: bytes) -> None:
            await self.outbox.submit(HAZARD_TOPIC, payload, latest_key=key)

        await self._zenoh.subscribe(TELEMETRY_KEYS, on_telemetry)
        await self._zenoh.subscribe(HAZARD_KEYS, on_hazard)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
