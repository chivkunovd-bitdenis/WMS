"""Actual CLI transport smoke in an isolated synthetic workspace, no client messages."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools" / "support_agent"))
from support_agent.config import Config  # noqa: E402
from support_agent.llm import LlmRouter  # noqa: E402
from support_agent.store import Store  # noqa: E402


def main() -> None:
    work = ROOT / ".bot-audit-20261003" / "native-fixture"
    work.mkdir(parents=True, exist_ok=True)
    (work / "seed.csv").write_text("sku,units\nA,2\nB,3\nA,4\n", encoding="utf-8")
    cfg = Config(repo=str(work), state_dir=str(work / "state"))
    cfg.llm.codex_effort = "medium"
    store = Store(work / "smoke.db")
    llm = LlmRouter(cfg, store)
    called: list[dict] = []

    def record(name: str, args: dict) -> dict:
        called.append({"name": name, "args": args})
        return {"recorded": True, "receipt": "transport-probe-ok"}

    spec = {"name": "record_probe", "description": "Record the verified sum from seed.csv.",
            "inputSchema": {"type": "object", "properties": {"units": {"type": "integer"}},
                            "required": ["units"], "additionalProperties": False}}
    evidence: dict = {"scope": "synthetic fixture only; actual model calls; no Telegram/Trello writes"}
    result = llm.agent_turn(
        "Проверка транспорта WMS. Прочитай seed.csv инструментом чтения проекта. "
        "Сложи units всех строк, вызови record_probe с суммой и верни его receipt. "
        "Файлы не меняй. Это тестовые данные, не обращение клиента.",
        session_key="native-smoke-read", model="gpt-5.6-sol", provider="codex",
        tools=[spec], tool_handler=record, cwd=str(work), timeout=240,
    )
    assert called and called[-1]["args"].get("units") == 9, called
    assert result.text.strip(), "Codex final answer was not captured"
    evidence["codex_read_and_tool"] = {"model": result.model, "reply": result.text, "calls": called.copy()}
    print(json.dumps({"passed": "codex_read_and_tool"}), flush=True)
    result = llm.agent_turn(
        "Проверка универсальной выгрузки WMS на синтетических данных. В этой папке seed.csv. "
        "Родными файловыми инструментами или shell создай export.csv: заголовок sku,units; "
        "сумма units по sku, сортировка по sku. Не меняй ничего вне этой папки. "
        "Не отправляй сообщения и не выполняй сетевые действия. Это только тест транспорта, "
        "не реализация функции WMS: не запускай аналитиков и не меняй код проекта. "
        "Проверь созданный файл и сообщи путь.",
        session_key="native-smoke-export", model="gpt-5.6-sol", provider="codex",
        mode="owner", owner_authorized=True, cwd=str(work), timeout=240,
    )
    with (work / "export.csv").open() as fh:
        exported = list(csv.DictReader(fh))
    assert exported == [{"sku": "A", "units": "6"}, {"sku": "B", "units": "3"}], exported
    assert result.text.strip(), "Codex export final answer was not captured"
    evidence["codex_native_export"] = {"model": result.model, "reply": result.text, "rows": exported}
    print(json.dumps({"passed": "codex_native_export"}), flush=True)
    called.clear()
    result = llm.agent_turn(
        "Проверка сервисного инструмента. Вызови record_probe с units=9 и верни receipt. "
        "Это тест транспорта WMS, ничего больше не делай.",
        session_key="native-smoke-claude", model="sonnet", provider="claude",
        tools=[spec], tool_handler=record, cwd=str(work), timeout=180,
    )
    assert called and called[-1]["args"].get("units") == 9, called
    evidence["claude_service_tool"] = {"model": result.model, "reply": result.text, "calls": called}
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": "claude_service_tool", "evidence": str(out)}), flush=True)


if __name__ == "__main__":
    main()
