#!/usr/bin/env python3
"""Autonomous MT04/MT22/MT40 checks; never starts LMS/WMS or controller."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.replay import EffectReplayGuard, recover_task, recover_wave  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def append_jsonl(path: Path, *events: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def task(task_id: str, stages: list[str], done: str | None, receipt: str) -> dict:
    next_index = 0 if done is None else stages.index(done) + 1
    verdicts = {stage: {"verdict": "PASS"} for stage in stages[:next_index]}
    return {
        "task_id": task_id,
        "required_stages": stages,
        "current_stage": stages[next_index],
        "status": "RUNNING",
        "last_valid_receipt": receipt if done else None,
        "verdicts": verdicts,
    }


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pipeline-replay-metatests-") as raw_root:
        root = Path(raw_root)

        # MT04: the last receipt survives a torn final journal line.
        mt04_state = root / "mt04" / "state.json"
        mt04_journal = mt04_state.with_name("journal.jsonl")
        write_json(mt04_state, task("MT04", ["S01", "S02", "S03"], "S02", "receipt-s02"))
        append_jsonl(mt04_journal, {"type": "STAGE_ADVANCED", "stage_id": "S02"})
        mt04_journal.write_text(mt04_journal.read_text() + '{"type":"CRASHED"', encoding="utf-8")
        recovered = recover_task(mt04_state, mt04_journal)
        if recovered["next_stage"] != "S03" or recovered["last_valid_receipt"] != "receipt-s02":
            failures.append("MT04: recovery did not resume after the last durable receipt")

        # MT22: restart restores every independent task in the wave.
        write_json(root / "wave" / "task-a" / "state.json", task("task-a", ["S01", "S02"], "S01", "r-a"))
        write_json(root / "wave" / "task-b" / "state.json", task("task-b", ["S01", "S02"], None, ""))
        wave = recover_wave(root / "wave")
        cursors = {item["task_id"]: item["next_stage"] for item in wave}
        if cursors != {"task-a": "S02", "task-b": "S01"}:
            failures.append(f"MT22: wave recovery lost a task or cursor: {cursors!r}")

        # MT40: state update may be lost, but a committed effect key fences replay.
        mt40_journal = root / "mt40" / "journal.jsonl"
        calls = 0

        def external_effect() -> None:
            nonlocal calls
            calls += 1

        if not EffectReplayGuard(mt40_journal).apply_once("shipment:42:label", external_effect):
            failures.append("MT40: first effect was unexpectedly suppressed")
        if EffectReplayGuard(mt40_journal).apply_once("shipment:42:label", external_effect) or calls != 1:
            failures.append("MT40: replay repeated a committed external effect")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("PASS: MT04 stage crash, MT22 wave restart, MT40 effect replay fence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
