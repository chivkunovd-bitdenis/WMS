"""Run the installed bot on original texts with real models and recording transports.

This is an audit harness, not a bot implementation. No prepared analysis, report,
question history, card, model session, or owner history is copied into the run.
Only SQLite test state and transport adapters differ from the installed service.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx

from support_agent.config import load_config
from support_agent.llm import LlmRouter
from support_agent.pipeline import InlinePool
from support_agent.redact import scrub
from support_agent.runner import build_agent
from support_agent.telegram import Bots, Inbound, flush_outbox
from support_agent.trello import TrelloClient


ROOT = Path(__file__).resolve().parents[4]
LABEL = sys.argv[1] if len(sys.argv) > 1 else "initial"
STATE = ROOT / ".bot-audit-20261003" / ("autonomy-" + LABEL)
OUTPUT = Path(__file__).with_name("autonomy-" + LABEL + "-2026-10-03.json")
STATE.mkdir(parents=True, exist_ok=True)
assert not (STATE / "state.db").exists(), "Use a fresh run label; do not reuse finished state"
cfg = load_config(str(Path.home() / ".wms-support-agent/config.json"))
cfg.state_dir = str(STATE)
trace: list[dict] = []
transports: list[dict] = []
result: dict = {
    "scenario": LABEL,
    "installed_import_path": str(Path(__import__("support_agent").__file__).resolve()),
    "ready_model_outputs_supplied": False,
    "fresh_model_sessions": True,
    "live_telegram_delivery": False,
    "live_trello_mutation": False,
    "source_voice": "previously saved real transcription; audio transcription not rerun",
    "calls": trace,
    "transport_calls": transports,
}


def save() -> None:
    OUTPUT.write_text(scrub(cfg, json.dumps(result, ensure_ascii=False, indent=2)) + "\n")


class AuditRouter(LlmRouter):
    def ask(self, role: str, prompt: str, **kwargs):
        item = {
            "role": role,
            "mode": kwargs.get("mode", "text"),
            "ticket_id": kwargs.get("ticket_id"),
            "prompt": prompt,
            "context": kwargs.get("context"),
            "system": kwargs.get("system"),
            "started_at": time.time(),
        }
        trace.append(item)
        save()
        print(json.dumps({"event": "llm_started", "role": role, "ticket": item["ticket_id"]}), flush=True)
        try:
            answer = super().ask(role, prompt, **kwargs)
        except Exception as exc:
            item.update(error_type=type(exc).__name__, finished_at=time.time())
            save()
            raise
        item.update(cli=answer.cli, model=answer.model, answer=answer.text, finished_at=time.time())
        save()
        print(json.dumps({"event": "llm_completed", "role": role, "model": answer.model}), flush=True)
        return answer


class TelegramRecorder:
    def __init__(self, role: str) -> None:
        self.role = role

    def send_message(self, chat_id, text, reply_to=None):
        mid = "test-" + str(len(transports) + 1)
        transports.append({"service": "telegram", "role": self.role, "chat_id": chat_id,
                           "text": text, "reply_to": reply_to, "test_message_id": mid})
        save()
        return mid

    def send_document(self, chat_id, path, caption="", reply_to=None):
        return self.send_message(chat_id, caption + "\n" + Path(path).read_text(), reply_to)


cards: dict[str, dict] = {}


def trello_transport(request: httpx.Request) -> httpx.Response:
    if request.method != "POST" or request.url.path != "/1/cards":
        raise AssertionError("Unexpected Trello request: " + request.method + " " + request.url.path)
    from urllib.parse import parse_qs

    payload = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
    card_id = "test-card-" + str(len(cards) + 1)
    payload.update(id=card_id, shortUrl="https://trello.invalid/c/" + card_id)
    cards[card_id] = payload
    transports.append({"service": "trello", "method": "POST", "test_card": payload})
    save()
    return httpx.Response(200, json=payload)


source = sqlite3.connect("file:" + str(Path.home() / ".wms-support-agent/state.db") + "?mode=ro", uri=True)
source.row_factory = sqlite3.Row
client_rows = [dict(r) for r in source.execute(
    "SELECT * FROM messages WHERE chat_id=-4899527415 AND role='client' ORDER BY ts,id"
)]
binding_rows = [dict(r) for r in source.execute("SELECT * FROM chat_bindings WHERE chat_id=-4899527415")]
result["source_message_ids"] = [r["id"] for r in client_rows]
result["source_text_sha256"] = hashlib.sha256(json.dumps(client_rows, ensure_ascii=False).encode()).hexdigest()
result["live_client_outbox_before"] = [r[0] for r in source.execute("SELECT id FROM outbox WHERE purpose='client' ORDER BY id")]
agent = build_agent(cfg)
pipe, store = agent.pipe, agent.store
for row in binding_rows:
    columns = list(row)
    store.execute("INSERT INTO chat_bindings(" + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in columns) + ")", tuple(row.values()))
pipe.register_bound_chats()
pipe.pool = InlinePool()
router = AuditRouter(cfg, store)
router.role_ensurer, router.role_alert = pipe.llm.role_ensurer, pipe.llm.role_alert
pipe.llm = router
pipe.bots = Bots(TelegramRecorder("intake"), TelegramRecorder("owner"), cfg.telegram.owner_chat_id)
pipe.trello = TrelloClient(cfg.trello, httpx.Client(transport=httpx.MockTransport(trello_transport)), redact=lambda s: scrub(cfg, s))
clock_value = [time.time()]
pipe.clock = lambda: clock_value[0]

try:
    for row in client_rows:
        incoming = Inbound(source=row["source"], chat_id=row["chat_id"], msg_id=row["msg_id"], role=row["role"],
                          author_id=row["author_id"], author_name=row["author_name"], ts=row["ts"],
                          kind="text", text=row["text"], reply_to=row["reply_to"])
        pipe.ingest(incoming)
    result["initial_ticket_count"] = len(store.rows("SELECT * FROM tickets"))
    result["initial_outbox_count"] = len(store.rows("SELECT * FROM outbox"))
    save()
    # Original ingress/routing, filtering, classification, fresh analysis and summary.
    pipe.tick()
    clock_value[0] += cfg.limits.quiet_sec + 1
    pipe.tick()
    clock_value[0] += cfg.limits.batch_wait_sec + 1
    pipe.tick()
    flush_outbox(store, pipe.bots, cfg)
    result["before_owner_question"] = [{**dict(t), "data": store.data(t["id"])} for t in store.rows("SELECT * FROM tickets")]
    # Explicitly a test conversation, never written into the live inbox.
    question = "Что по Империи ФФ? Какие задачи созданы и что уже сделано?"
    result["owner_test_question"] = question
    pipe.ingest(Inbound(source="telegram", chat_id=cfg.telegram.owner_chat_id, msg_id="900001",
                        role="owner", author_id=str(cfg.telegram.owner_user_id), author_name="owner-test",
                        ts=clock_value[0], kind="text", text=question))
    pipe.tick()
    flush_outbox(store, pipe.bots, cfg)
    result["run_completed"] = True
except BaseException as exc:
    result["run_completed"] = False
    result["stop_error_type"] = type(exc).__name__
    raise
finally:
    result["tickets"] = [{**dict(t), "data": store.data(t["id"])} for t in store.rows("SELECT * FROM tickets")]
    result["messages"] = [dict(r) for r in store.rows("SELECT id,msg_id,role,text,status,ticket_id FROM messages ORDER BY id")]
    result["outbox"] = [dict(r) for r in store.rows("SELECT * FROM outbox ORDER BY id")]
    result["llm_calls"] = [dict(r) for r in store.rows("SELECT * FROM llm_calls ORDER BY id")]
    result["live_client_outbox_after"] = [r[0] for r in source.execute("SELECT id FROM outbox WHERE purpose='client' ORDER BY id")]
    result["completed_at"] = time.time()
    save()
    print(json.dumps({"event": "finished", "artifact": str(OUTPUT), "ticket_stages": [t["stage"] for t in result["tickets"]]}), flush=True)
