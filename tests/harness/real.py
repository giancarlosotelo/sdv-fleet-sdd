import os
import socket

import pytest

# CI sets FLEET_REQUIRE_REAL=1 so real-service tests fail instead of skipping (spec REQ-132).
REQUIRED = os.environ.get("FLEET_REQUIRE_REAL") == "1"


def require_service(name: str, port: int, host: str = "127.0.0.1") -> None:
    try:
        socket.create_connection((host, port), timeout=1).close()
    except OSError:
        message = f"real {name} not reachable on {host}:{port}; run: docker compose -f deploy/compose.yaml up -d"
        if REQUIRED:
            pytest.fail(message)
        pytest.skip(message)
