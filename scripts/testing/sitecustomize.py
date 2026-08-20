"""Socket-level deny-by-default egress guard, enabled by test_egress_guard.py."""

from __future__ import annotations

import ipaddress
import os
import socket


LIVE_MARKETPLACE_SUFFIXES = ("wildberries.ru", "ozon.ru")
DEFAULT_ALLOW_HOSTS = "127.0.0.1,::1,localhost,*.test,wb-emulator,db,redis"
_resolved_allowed_addresses: set[str] = set()
_original_getaddrinfo = socket.getaddrinfo
_original_connect = socket.socket.connect


def _allow_patterns() -> tuple[str, ...]:
    raw = os.environ.get("WMS_TEST_EGRESS_ALLOW_HOSTS", DEFAULT_ALLOW_HOSTS)
    patterns = [item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip()]
    if os.environ.get("WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES") == "1":
        patterns.extend(LIVE_MARKETPLACE_SUFFIXES)
        patterns.extend(f"*.{suffix}" for suffix in LIVE_MARKETPLACE_SUFFIXES)
    return tuple(patterns)


def _matches_allowlist(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        pass
    for pattern in _allow_patterns():
        if pattern.startswith("*.") and normalized.endswith(pattern[1:]):
            return True
        if normalized == pattern:
            return True
    return False


def _blocked(host: object) -> PermissionError:
    return PermissionError(f"WMS test egress denied host: {host}")


def guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> list[tuple[object, ...]]:
    if isinstance(host, bytes):
        host = host.decode("idna")
    if not isinstance(host, str) or not _matches_allowlist(host):
        raise _blocked(host)
    result = _original_getaddrinfo(host, *args, **kwargs)
    _resolved_allowed_addresses.update(str(item[4][0]) for item in result if item[4])
    return result


def guarded_connect(self: socket.socket, address: object) -> object:
    if isinstance(address, tuple) and address:
        host = str(address[0])
        if not _matches_allowlist(host) and host not in _resolved_allowed_addresses:
            raise _blocked(host)
    return _original_connect(self, address)


if os.environ.get("WMS_TEST_EGRESS") == "deny":
    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.connect = guarded_connect
