"""Block until the compose services accept TCP connections (CI and local `pytest -m real`)."""

import socket
import sys
import time

SERVICES = {
    "databroker-1": 55561,
    "databroker-2": 55562,
    "databroker-3": 55563,
    "zenoh": 7447,
    "pubsub": 8085,
}


def main(timeout_s: float = 90.0) -> int:
    deadline = time.monotonic() + timeout_s
    pending = dict(SERVICES)
    while pending and time.monotonic() < deadline:
        for name, port in list(pending.items()):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                print(f"{name} ready on {port}")
                del pending[name]
            except OSError:
                pass
        time.sleep(0.5)
    if pending:
        print(f"not ready: {', '.join(pending)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
