import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fleet.cloud.service import CloudService
from fleet.config import FleetConfig

STATIC = Path(__file__).parent / "static"


class Hub:
    """Fans service events out to every connected dashboard."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, event: dict[str, Any]) -> None:
        text = json.dumps(event)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except (WebSocketDisconnect, RuntimeError):
                self.clients.discard(ws)


def create_app(
    service: CloudService, cfg: FleetConfig, routes: dict[str, tuple[tuple[float, float], ...]]
) -> FastAPI:
    app = FastAPI(title="SDV Fleet Monitor")
    hub = Hub()
    service.listen(hub.broadcast)
    route_list = [
        {
            "id": rid,
            "name": cfg.routes[rid].name,
            "speed_limit_kmh": cfg.routes[rid].speed_limit_kmh,
            "polyline": polyline,
        }
        for rid, polyline in routes.items()
    ]

    def snapshot(include_resolved: bool) -> dict[str, Any]:
        return service.snapshot(include_resolved) | {"routes": route_list}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/snapshot")
    def get_snapshot(include_resolved: bool = False) -> dict[str, Any]:
        return snapshot(include_resolved)

    @app.post("/api/alerts/{alert_id}/ack")
    async def ack(alert_id: str) -> dict[str, Any]:
        alert = await service.ack(alert_id)
        if alert is None:
            raise HTTPException(404, f"no alert {alert_id}")
        return alert.__dict__

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_text(json.dumps({"type": "snapshot"} | snapshot(False)))
        hub.clients.add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            hub.clients.discard(ws)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
