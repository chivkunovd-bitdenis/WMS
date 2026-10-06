"""Run existing pytest nodes; permit only this synthetic asyncpg endpoint.

This is an audit harness, not a product mock. HTTP uses existing ASGI/mock
fixtures unchanged. Python socket audit hooks reject external DNS/connections
before app imports. Use asyncpg, which uses Python sockets (not libpq).
"""
import json
import os
from pathlib import Path
import socket
import sys

port = int(os.environ["AUDIT_PG_PORT"])
attempts = []
connections = []


def boundary(event, args):
    if event == "socket.getaddrinfo":
        host, target_port = args[:2]
        if host not in {"127.0.0.1", "::1", "localhost"} or target_port != port:
            attempts.append({"event": event, "host": str(host), "port": str(target_port)})
            raise RuntimeError("Audit network boundary: external DNS prohibited")
    elif event == "socket.connect":
        sock, address = args
        if sock.family not in {socket.AF_INET, socket.AF_INET6}:
            raise RuntimeError("Audit network boundary: non-IP connection prohibited")
        if address[0] not in {"127.0.0.1", "::1"} or address[1] != port:
            attempts.append({"event": event, "host": str(address[0]), "port": str(address[1])})
            raise RuntimeError("Audit network boundary: external connection prohibited")
        connections.append({"host": address[0], "port": address[1]})


sys.addaudithook(boundary)
import pytest

result = pytest.main(sys.argv[1:])
Path(os.environ["AUDIT_NETWORK_REPORT"]).write_text(json.dumps({
    "allowed_endpoint": ["127.0.0.1", port],
    "allowed_connections": len(connections),
    "blocked_attempts": attempts,
    "pytest_exit_code": int(result),
}, indent=2) + "\n")
raise SystemExit(result)
