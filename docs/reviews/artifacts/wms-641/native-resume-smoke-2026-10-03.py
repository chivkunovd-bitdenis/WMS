"""Two actual Codex turns with process/router restart and persistent dynamic tool."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/support_agent"))
from support_agent.config import Config
from support_agent.llm import LlmRouter
from support_agent.store import Store
work = ROOT / ".bot-audit-20261003/native-fixture"
cfg = Config(repo=str(work), state_dir=str(work / "state"))
cfg.llm.codex_effort = "medium"
spec = {"name": "resume_probe", "description": "Record transport probe and return a receipt.", "inputSchema": {"type": "object", "properties": {"turn": {"type": "integer"}}, "required": ["turn"], "additionalProperties": False}}
evidence = []
for n in (1, 2):
    calls = []
    def handler(name, args):
        calls.append({"name": name, "args": args})
        return {"receipt": f"resume-ok-{n}"}
    llm = LlmRouter(cfg, Store(work / "resume-smoke.db"))
    result = llm.agent_turn(f"Тест транспорта WMS. Вызови resume_probe с turn={n}, затем верни его receipt. Ничего больше не делай.", session_key="actual-resume-v1", model="gpt-5.6-sol", provider="codex", tools=[spec], tool_handler=handler, cwd=str(work), timeout=180)
    assert result.text.strip() and calls[-1]["args"]["turn"] == n
    evidence.append({"turn": n, "thread_id": result.session_id, "reply": result.text, "calls": calls})
    print(json.dumps({"passed_turn": n, "thread_id": result.session_id}), flush=True)
assert evidence[0]["thread_id"] == evidence[1]["thread_id"], evidence
Path(__file__).with_suffix(".json").write_text(json.dumps({"scope": "synthetic; actual model; no external writes", "same_thread_resumed": True, "turns": evidence}, ensure_ascii=False, indent=2) + "\n")
