"""Blocks non-local network for the whole test run (spec REQ-012); real services live on localhost."""

import socket

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}


class NetworkBlocked(RuntimeError):
    pass


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def _check(host: object) -> None:
    if host not in LOCAL_HOSTS:
        raise NetworkBlocked(f"tests may not reach {host}; only localhost is allowed")


def _guarded_connect(self: socket.socket, address: object) -> None:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _check(address[0])
    return _connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: object) -> int:
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _check(address[0])
    return _connect_ex(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host is not None:
        _check(host.decode() if isinstance(host, bytes) else host)
    return _getaddrinfo(host, *args, **kwargs)


def pytest_configure(config) -> None:
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.getaddrinfo = _guarded_getaddrinfo
