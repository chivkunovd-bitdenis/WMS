#!/usr/bin/env python3
"""Run a test command with deny-by-default marketplace egress protection."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
TESTING_DIR = ROOT / "scripts" / "testing"
LIVE_MARKETPLACE_SUFFIXES = ("wildberries.ru", "ozon.ru")
DEFAULT_ALLOW_HOSTS = "127.0.0.1,::1,localhost,*.test,wb-emulator,db,redis"
BASE_URL_ENV_NAMES = (
    "WILDBERRIES_CONTENT_API_BASE",
    "WILDBERRIES_SUPPLIES_API_BASE",
    "WILDBERRIES_MARKETPLACE_API_BASE",
    "OZON_API_BASE",
    "OZON_SELLER_API_BASE",
)


def is_live_marketplace_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in LIVE_MARKETPLACE_SUFFIXES
    )


def configured_live_marketplace_urls(env: dict[str, str]) -> list[str]:
    if env.get("WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES") == "1":
        return []

    violations: list[str] = []
    for name in BASE_URL_ENV_NAMES:
        value = env.get(name, "").strip()
        if not value:
            continue
        host = urlparse(value).hostname
        if host and is_live_marketplace_host(host):
            violations.append(f"{name}={value}")
    return violations


def guarded_env(base_env: dict[str, str]) -> dict[str, str]:
    env = base_env.copy()
    env["WMS_TEST_EGRESS"] = "deny"
    env.setdefault("WMS_TEST_EGRESS_ALLOW_HOSTS", DEFAULT_ALLOW_HOSTS)
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"

    python_path = str(TESTING_DIR)
    if existing_python_path := env.get("PYTHONPATH"):
        python_path = os.pathsep.join((python_path, existing_python_path))
    env["PYTHONPATH"] = python_path

    node_hook = f"--require {TESTING_DIR / 'test_egress_node.cjs'}"
    env["NODE_OPTIONS"] = " ".join(filter(None, (node_hook, env.get("NODE_OPTIONS", ""))))
    return env


def check(env: dict[str, str]) -> int:
    violations = configured_live_marketplace_urls(env)
    if violations:
        print(
            "test egress guard: live marketplace URL is forbidden without opt-in:",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        print(
            "Set WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES=1 only for an explicitly approved live test.",
            file=sys.stderr,
        )
        return 1
    print("test egress guard: configuration is fail-closed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="validate the current test egress environment"
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run after --")
    args = parser.parse_args()

    env = guarded_env(dict(os.environ))
    if check(env):
        return 1
    if args.check:
        return 0
    if not args.command:
        parser.error("a test command is required after --")
    if args.command[0] == "--":
        args.command.pop(0)
    if not args.command:
        parser.error("a test command is required after --")
    return subprocess.run(args.command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
