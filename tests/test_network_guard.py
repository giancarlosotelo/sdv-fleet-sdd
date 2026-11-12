import socket

import pytest

from tests.harness.network import NetworkBlocked


def test_req012_external_network_is_blocked():
    with pytest.raises(NetworkBlocked, match="1.1.1.1"):
        socket.create_connection(("1.1.1.1", 443), timeout=1)


def test_req012_localhost_is_allowed():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    try:
        socket.create_connection(server.getsockname(), timeout=1).close()
    finally:
        server.close()


def test_req012_external_dns_lookup_is_blocked():
    with pytest.raises(NetworkBlocked, match="router.project-osrm.org"):
        socket.getaddrinfo("router.project-osrm.org", 443)
