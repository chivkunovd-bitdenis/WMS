"""Test-only fault injection toggles for WB emulator routes."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

_faults: dict[str, SellerFaults] = {}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def maybe_raise_env_fault() -> None:
    """Global env toggles: WB_EMULATOR_FAULT_TIMEOUT / WB_EMULATOR_FAULT_409."""
    if _env_truthy("WB_EMULATOR_FAULT_409"):
        raise HTTPException(status_code=409, detail="injected conflict (WB_EMULATOR_FAULT_409)")
    if _env_truthy("WB_EMULATOR_FAULT_TIMEOUT"):
        delay_raw = os.environ.get("WB_EMULATOR_FAULT_TIMEOUT_SECONDS", "30")
        try:
            delay = float(delay_raw)
        except ValueError:
            delay = 30.0
        time.sleep(max(delay, 0.0))
        raise HTTPException(status_code=504, detail="injected timeout (WB_EMULATOR_FAULT_TIMEOUT)")


@dataclass
class SellerFaults:
    timeout_ms: int = 0
    supply_conflict_409: bool = False
    meta_validation_fail: bool = False
    incomplete_stickers: bool = False
    delayed_qr_ms: int = 0
    partial_status_ids: set[int] = field(default_factory=set)


def reset_fault_store() -> None:
    _faults.clear()


def get_faults(seller_key: str) -> SellerFaults:
    return _faults.setdefault(seller_key, SellerFaults())


def set_faults(seller_key: str, payload: dict[str, Any]) -> SellerFaults:
    current = get_faults(seller_key)
    if "timeout_ms" in payload:
        current.timeout_ms = max(0, int(payload["timeout_ms"]))
    if "supply_conflict_409" in payload:
        current.supply_conflict_409 = bool(payload["supply_conflict_409"])
    if "meta_validation_fail" in payload:
        current.meta_validation_fail = bool(payload["meta_validation_fail"])
    if "incomplete_stickers" in payload:
        current.incomplete_stickers = bool(payload["incomplete_stickers"])
    if "delayed_qr_ms" in payload:
        current.delayed_qr_ms = max(0, int(payload["delayed_qr_ms"]))
    if "partial_status_ids" in payload:
        raw = payload["partial_status_ids"]
        if isinstance(raw, list):
            current.partial_status_ids = {int(item) for item in raw}
    return current


def faults_snapshot(seller_key: str | None = None) -> dict[str, Any]:
    if seller_key is not None:
        faults = get_faults(seller_key)
        return {
            "seller": seller_key,
            "timeout_ms": faults.timeout_ms,
            "supply_conflict_409": faults.supply_conflict_409,
            "meta_validation_fail": faults.meta_validation_fail,
            "incomplete_stickers": faults.incomplete_stickers,
            "delayed_qr_ms": faults.delayed_qr_ms,
            "partial_status_ids": sorted(faults.partial_status_ids),
        }
    return {key: faults_snapshot(key) for key in sorted(_faults)}


async def maybe_delay(seller_key: str, *, qr: bool = False) -> None:
    faults = get_faults(seller_key)
    delay_ms = faults.delayed_qr_ms if qr else faults.timeout_ms
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)
