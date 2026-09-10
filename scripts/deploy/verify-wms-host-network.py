#!/usr/bin/env python3
"""WMS-270/377: verify the existing host topology without changing networks."""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path

WMS_SUBNET = "172.21.0.0/16"
WMS_GATEWAY = "172.21.0.1"
EDGE_SUBNET = "172.18.0.0/16"
EDGE_GATEWAY = "172.18.0.1"


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def one_id(value: str, description: str) -> str:
    ids = value.split()
    require(len(ids) == 1, f"Expected one existing {description}")
    return ids[0]


def endpoints(container: str) -> dict:
    return json.loads(docker(
        "inspect", container, "--format", "{{json .NetworkSettings.Networks}}",
    ))


def verify(db_container: str, repo: Path) -> None:
    # Verify the code being applied agrees with this host contract, too.
    overlay = (repo / "docker-compose.wms-host-8088.yml").read_text()
    caddy = (repo / "deploy/Caddyfile.http").read_text()
    trusted = re.search(r"^\s*trusted_proxies static ([^\n]+)$", caddy, re.MULTILINE)
    require(bool(re.search(r'FORWARDED_ALLOW_IPS:\s*"172\.21\.0\.0/16"', overlay)),
            "Overlay API trust does not match the verified host contract")
    require('"172.18.0.1:8088:80"' in overlay, "Overlay listener does not match the edge gateway")
    require(trusted is not None and set(trusted[1].split()) == {EDGE_SUBNET, WMS_GATEWAY + "/32"},
            "Caddy trust does not match the verified host contract")
    require(bool(re.search(r"^\s*trusted_proxies_strict\s*$", caddy, re.MULTILINE)),
            "Strict proxy-chain parsing is missing")
    project = docker("inspect", db_container, "--format",
                     '{{index .Config.Labels "com.docker.compose.project"}}')
    require(bool(project) and project != "<no value>", "Database has no Compose project")
    network_id = one_id(docker(
        "network", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}",
        "--filter", "label=com.docker.compose.network=default",
    ), "WMS default network")
    network = json.loads(docker("network", "inspect", network_id))[0]
    require(network["IPAM"]["Config"] == [{"Subnet": WMS_SUBNET, "Gateway": WMS_GATEWAY}],
            "WMS subnet/gateway changed; review proxy trust before deployment")
    for service in ("api", "web"):
        container = one_id(docker(
            "ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
            "--filter", f"label=com.docker.compose.service={service}",
        ), f"WMS {service} container")
        attached = endpoints(container).get(network["Name"])
        require(attached is not None and attached["NetworkID"] == network["Id"]
                and attached["Gateway"] == WMS_GATEWAY
                and attached["IPPrefixLen"] == 16
                and ipaddress.ip_address(attached["IPAddress"]) in ipaddress.ip_network(WMS_SUBNET),
                f"WMS {service} is outside the verified proxy network")
    edge = one_id(docker("ps", "-q", "--filter", "publish=443"), "HTTPS edge container")
    edge_endpoints = [e for e in endpoints(edge).values() if e.get("Gateway") == EDGE_GATEWAY]
    require(len(edge_endpoints) == 1, "HTTPS edge no longer uses the listener gateway")
    endpoint = edge_endpoints[0]
    edge_network = json.loads(docker("network", "inspect", endpoint["NetworkID"]))[0]
    require(edge_network["IPAM"]["Config"] == [{"Subnet": EDGE_SUBNET, "Gateway": EDGE_GATEWAY}]
            and endpoint["IPPrefixLen"] == 16
            and ipaddress.ip_address(endpoint["IPAddress"]) in ipaddress.ip_network(EDGE_SUBNET),
            "HTTPS edge subnet/gateway changed; review Caddy trust before deployment")


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2 and bool(sys.argv[1]), "Pass the existing Compose database ID")
        verify(sys.argv[1], Path.cwd())
    except (ValueError, KeyError, IndexError, OSError, subprocess.CalledProcessError) as exc:
        # No full container inspection/environment or Docker stderr is printed.
        print(f"ERROR: WMS proxy topology not verified: {exc}", file=sys.stderr)
        sys.exit(1)
    print("WMS proxy topology verified; no network or container was changed.")
