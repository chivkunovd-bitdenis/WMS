"""Verify real deployment guard logic against changed Docker topology."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("change", ["", "container-ip", "wms-subnet", "edge-subnet",
                                    "detached-api", "missing-network", "two-edges", "stopped-api",
                                    "stopped-wrong-network"])
def test_host_network_guard(change: str, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "wms377_network_guard", repo / "scripts/deploy/verify-wms-host-network.py",
    )
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    calls: list[tuple[str, ...]] = []

    def docker(*args: str) -> str:
        calls.append(args)
        if args[:3] == ("network", "ls", "-q"):
            return "" if change == "missing-network" else "wms-network"
        if args[:2] == ("network", "inspect"):
            edge = args[2] == "edge-network"
            number = 18 if edge else 21
            if change == ("edge-subnet" if edge else "wms-subnet"):
                number = 22
            return json.dumps([{"Id": args[2], "Name": args[2], "IPAM": {"Config": [
                {"Subnet": f"172.{number}.0.0/16", "Gateway": f"172.{number}.0.1"},
            ]}}])
        if args[:2] == ("ps", "-q") or args[:3] == ("ps", "-a", "-q"):
            if "publish=443" in args:
                return "edge other-edge" if change == "two-edges" else "edge"
            return "api" if args[-1].endswith("service=api") else "web"
        if args[0] == "inspect":
            if "State.Running" in args[-1]:
                if args[1] == "api" and change.startswith("stopped"):
                    mode = "wrong-network" if change == "stopped-wrong-network" else "wms-network"
                    return f"false|{mode}"
                return "true|wms-network"
            if "Config.Labels" in args[-1]:
                return "wms-project"
            if args[1] == "api" and change == "detached-api":
                return "{}"
            edge = args[1] == "edge"
            network = "edge-network" if edge else "wms-network"
            number = 18 if edge else 21
            host = "8.99" if change == "container-ip" else "0.6"
            stopped = args[1] == "api" and change.startswith("stopped")
            return json.dumps({network: {
                "NetworkID": network, "Gateway": "" if stopped else f"172.{number}.0.1",
                "IPAddress": "" if stopped else f"172.{number}.{host}",
                "IPPrefixLen": 0 if stopped else 16,
            }})
        pytest.fail(f"Unexpected Docker operation: {args}")

    monkeypatch.setattr(guard, "docker", docker)
    if change in ("", "container-ip", "stopped-api"):
        guard.verify("db", repo)
    else:
        with pytest.raises(ValueError):
            guard.verify("db", repo)
    assert all(c[0] in ("inspect", "ps", "network") for c in calls)
