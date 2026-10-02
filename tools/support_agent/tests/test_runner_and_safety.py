"""R32-R35, R37: простой и возвращение, перезапуск, параллельность, отправка, секреты."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from support_agent.config import config_from_dict
from support_agent.pipeline import InlinePool, Pipeline, ThreadPool
from support_agent.runner import Agent, RedactFilter
from support_agent.store import Store
from support_agent.telegram import (
    TelegramClient,
    TelegramError,
    flush_outbox,
    recover_after_restart,
)
from support_agent.trello import TrelloClient, TrelloError

from .conftest import (
    CLIENT_CHAT,
    OWNER_CHAT,
    OWNER_ID,
    Clock,
    FakeLlm,
    FakeTelegram,
    FakeTranscriber,
    FakeTrello,
    FakeWms,
    make_config,
)
from .test_pipeline_chat import script


def make_agent(env: Any) -> Agent:
    return Agent(env.cfg, env.store, env.tg, env.pipe, clock=env.clock)


def update(uid: int, text: str, chat: int = CLIENT_CHAT, user: int = 5) -> dict[str, Any]:
    return {"update_id": uid, "message": {"message_id": uid, "chat": {"id": chat}, "date": 1,
            "from": {"id": user, "first_name": "Анна"}, "text": text}}


def test_agent_reports_downtime_once_after_catching_up(env: Any) -> None:
    script(env)
    env.store.kv_set("heartbeat", env.clock.now - 3 * 3600)
    agent = make_agent(env)
    agent.startup()
    env.tg.updates = [update(1, "не работает передача"), update(2, "и ещё")]
    agent.loop_once()
    env.flush()
    assert env.tg.to(OWNER_CHAT) == []  # ещё догоняем
    env.tg.updates = []
    agent.loop_once()
    agent.loop_once()
    env.flush()
    notes = [t for t in env.tg.to(OWNER_CHAT) if "снова работает" in t]
    assert len(notes) == 1 and "сообщений из чатов 2" in notes[0] and "потерял" not in notes[0]


def test_downtime_over_24h_warns_about_possible_loss(env: Any) -> None:
    env.store.kv_set("heartbeat", env.clock.now - 30 * 3600)
    agent = make_agent(env)
    agent.startup()
    agent.loop_once()
    env.flush()
    assert any("могла потеряться" in t for t in env.tg.to(OWNER_CHAT))


def test_first_start_and_short_pause_send_no_downtime_notice(env: Any) -> None:
    agent = make_agent(env)
    agent.startup()
    agent.loop_once()
    env.store.kv_set("heartbeat", env.clock.now - 30)
    agent.startup()
    agent.loop_once()
    env.flush()
    assert env.tg.to(OWNER_CHAT) == []


def test_telegram_offset_is_saved_and_duplicates_are_ignored(env: Any) -> None:
    script(env)
    agent = make_agent(env)
    env.tg.updates = [update(5, "не работает передача")]
    agent.loop_once()
    assert env.store.kv_get("tg_offset:intake") == 6
    agent.loop_once()  # Telegram повторно отдал то же обновление (потерян ответ)
    env.store.kv_set("tg_offset", 0)
    agent.loop_once()
    assert len(env.store.rows("SELECT * FROM messages")) == 1


def test_state_survives_restart_and_summary_is_not_resent(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    clock = Clock()
    store = Store(cfg.db_path)
    tg, llm = FakeTelegram(), FakeLlm()

    def build(store: Store) -> Pipeline:
        return Pipeline(cfg, store, tg, llm, FakeTrello(), FakeWms(), FakeTranscriber(),  # type: ignore[arg-type]
                        pool=InlinePool(), clock=clock)

    class E:  # минимальный env для script()
        pass

    e = E()
    e.llm = llm  # type: ignore[attr-defined]
    script(e)
    pipe = build(store)
    from support_agent.telegram import Inbound

    pipe.ingest(Inbound("telegram", CLIENT_CHAT, "1", "client", "5", "Анна", clock.now, "text",
                        "не работает передача"))
    pipe.tick()
    clock.advance(130)
    pipe.tick()
    clock.advance(1000)
    pipe.tick()
    clock.advance(100)
    pipe.tick()
    flush_outbox(store, tg, cfg)  # type: ignore[arg-type]
    owner_before = len(tg.to(OWNER_CHAT))
    assert store.ticket(1)["stage"] == "await_owner" and owner_before == 1
    store.db.close()
    store2 = Store(cfg.db_path)  # «перезапуск мака»
    pipe2 = build(store2)
    for _ in range(3):
        clock.advance(500)
        pipe2.tick()
        flush_outbox(store2, tg, cfg)  # type: ignore[arg-type]
    assert store2.ticket(1)["stage"] == "await_owner"  # ждёт «кати», не сдвинулось
    assert len(tg.to(OWNER_CHAT)) == owner_before  # повторной сводки нет


def test_killed_between_send_and_record_is_not_repeated_and_owner_is_told(env: Any) -> None:
    env.store.queue_message(key="q", chat_id=CLIENT_CHAT, text="Подскажите...", ticket_id=3)
    item = env.store.outbox_pending()[0]
    assert env.store.claim_outbox(item["id"])  # намерение записано, процесс «убит» до ответа
    recover_after_restart(env.store, env.cfg)
    flush_outbox(env.store, env.tg, env.cfg)
    flush_outbox(env.store, env.tg, env.cfg)
    assert env.tg.to(CLIENT_CHAT) == []  # клиенту не повторяем
    assert env.store.outbox_by_key("q")["status"] == "unknown"
    assert [t for t in env.tg.to(OWNER_CHAT) if "не подтверждена" in t] == [
        "Отправка сообщения клиенту не подтверждена (обращение 3): связь оборвалась в момент "
        "отправки. Повторно я его не отправляю, чтобы не дублировать. Проверьте чат."]


def test_lost_telegram_response_to_client_is_not_repeated_but_owner_messages_are(env: Any) -> None:
    env.tg.fail = [TelegramError("unknown", "ReadTimeout")]
    env.store.queue_message(key="c", chat_id=CLIENT_CHAT, text="клиенту", ticket_id=1)
    env.flush()
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == [] and env.store.outbox_by_key("c")["status"] == "unknown"
    env.tg.fail = [TelegramError("unknown", "ReadTimeout")]
    env.store.queue_message(key="o", chat_id=OWNER_CHAT, text="владельцу", repeat_ok=True)
    env.flush()
    env.flush()
    assert "владельцу" in env.tg.to(OWNER_CHAT)


def test_not_sent_errors_are_retried_and_rejection_is_final(env: Any) -> None:
    env.tg.fail = [TelegramError("not_sent", "connect")]
    env.store.queue_message(key="a", chat_id=CLIENT_CHAT, text="a")
    env.flush()
    assert env.tg.sent == []
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == ["a"]
    env.tg.fail = [TelegramError("rejected", "http_403")]
    env.store.queue_message(key="b", chat_id=CLIENT_CHAT, text="b")
    env.flush()
    env.flush()
    assert env.store.outbox_by_key("b")["status"] == "failed" and env.tg.to(CLIENT_CHAT) == ["a"]


def test_parallel_sessions_are_limited_and_same_key_not_run_twice() -> None:
    pool = ThreadPool(2)
    lock = threading.Lock()
    state = {"now": 0, "max": 0, "runs": 0}
    gate = threading.Event()

    def job() -> None:
        with lock:
            state["now"] += 1
            state["runs"] += 1
            state["max"] = max(state["max"], state["now"])
        gate.wait(2)
        with lock:
            state["now"] -= 1

    for i in range(4):
        pool.submit(f"ticket:{i}", job)
    pool.submit("ticket:0", job)  # тот же ключ, пока занят: не запускается второй раз
    time.sleep(0.2)
    assert state["max"] == 2 and state["runs"] == 2  # третий и четвёртый ждут
    gate.set()
    pool.executor.shutdown(wait=True)
    assert state["runs"] == 4 and state["max"] == 2


def test_reply_goes_into_the_session_of_its_own_ticket(env: Any) -> None:
    script(env)
    env.say(CLIENT_CHAT, "[новая] первая беда", msg_id="1")
    env.say(CLIENT_CHAT, "[новая] вторая беда", user=6, msg_id="2")
    env.clock.advance(130)
    env.pipe.tick()
    env.flush()
    questions = env.store.rows("SELECT ticket_id, tg_message_id FROM outbox WHERE purpose='client'")
    second = next(q for q in questions if q["ticket_id"] == 2)
    env.say(CLIENT_CHAT, "срочно", user=6, reply_to=second["tg_message_id"], msg_id="3")
    assert [m["text"] for m in env.store.ticket_messages(2)][-1] == "срочно"
    assert [m["text"] for m in env.store.ticket_messages(1)] == ["[новая] первая беда"]


# ------------------------------------------------------------------------- секреты
def test_secrets_are_redacted_from_logs(env: Any, caplog: Any) -> None:
    logger = logging.getLogger("t")
    flt = RedactFilter(env.cfg)
    logger.addFilter(flt)
    with caplog.at_level(logging.INFO, logger="t"):
        logger.info("ошибка %s и %s", env.cfg.telegram.bot_token, env.cfg.trello.token)
    caplog.handler.addFilter(flt)
    assert "SECRET-BOT-TOKEN" not in caplog.text and "TRELLO-TOKEN-VALUE" not in caplog.text


def test_error_texts_of_clients_do_not_contain_tokens(env: Any) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout for " + str(request.url))

    tg = TelegramClient("123456:SECRET-BOT-TOKEN", httpx.Client(transport=httpx.MockTransport(boom)))
    try:
        tg.send_message(1, "x")
    except TelegramError as exc:
        assert "SECRET" not in str(exc) and exc.outcome == "unknown"
    trello = TrelloClient(env.cfg.trello, httpx.Client(transport=httpx.MockTransport(boom)))
    try:
        trello.get_card("c")
    except TrelloError as exc:
        assert "TRELLO-KEY" not in str(exc) and "TRELLO-TOKEN" not in str(exc)


def test_telegram_http_outcomes_are_classified() -> None:
    def answer(code: int, body: dict[str, Any]) -> TelegramClient:
        return TelegramClient("t", httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(code, json=body))))

    assert answer(200, {"ok": True, "result": {"message_id": 5}}).send_message(1, "x") == "5"
    for code, body, outcome in ((429, {"ok": False}, "not_sent"), (500, {"ok": False}, "unknown"),
                                (403, {"ok": False}, "rejected")):
        try:
            answer(code, body).send_message(1, "x")
        except TelegramError as exc:
            assert exc.outcome == outcome
        else:
            raise AssertionError("must raise")


def test_no_secret_values_leak_into_messages_or_model_prompts(env: Any) -> None:
    script(env)
    env.say(CLIENT_CHAT, "не работает передача поставки")
    env.pipe.tick()
    env.clock.advance(2000)
    for _ in range(4):
        env.pipe.tick()
        env.clock.advance(100)
    env.flush()
    blob = "\n".join(t for _, t, _ in env.tg.sent) + "\n".join(c["prompt"] for c in env.llm.calls)
    blob += "\n".join(r["text"] for r in env.store.rows("SELECT text FROM outbox"))
    for secret in env.cfg.secrets():
        assert secret not in blob


def test_client_chats_are_isolated_in_summaries_and_questions(env: Any, tmp_path: Path) -> None:
    cfg = config_from_dict({
        "state_dir": str(tmp_path / "s2"), "telegram": {
            "bot_token": "x", "owner_user_id": OWNER_ID, "owner_chat_id": OWNER_CHAT,
            "chats": {"-1": {"role": "client", "seller": "Селлер А"},
                      "-2": {"role": "client", "seller": "Селлер Б"}}}})
    store = Store(cfg.db_path)
    llm, tg = FakeLlm(), FakeTelegram()
    pipe = Pipeline(cfg, store, tg, llm, FakeTrello(), FakeWms(), FakeTranscriber(),  # type: ignore[arg-type]
                    pool=InlinePool(), clock=env.clock)

    class E:
        pass

    e = E()
    e.llm = llm  # type: ignore[attr-defined]
    script(e)
    from support_agent.telegram import Inbound

    for chat, txt in ((-1, "[новая] у А проблема"), (-2, "[новая] у Б проблема")):
        pipe.ingest(Inbound("telegram", chat, "1", "client", "5", "x", env.clock.now, "text", txt))
    pipe.route_messages()
    env.clock.advance(130)
    pipe.tick()
    flush_outbox(store, tg, cfg)  # type: ignore[arg-type]
    for chat, name in ((-1, "Селлер Б"), (-2, "Селлер А")):
        assert not any(name in t for t in tg.to(chat))
    tickets = {t["chat_id"]: t["seller"] for t in store.rows("SELECT * FROM tickets")}
    assert tickets == {-1: "Селлер А", -2: "Селлер Б"}
    assert all("у Б" not in c["prompt"] for c in llm.calls if "Селлер А" in c["prompt"] and "Разберись" in c["prompt"])


def test_send_document_uploads_file_and_classifies_errors(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    f = tmp_path / "x.csv"
    f.write_text("a;b", encoding="utf-8")
    tg = TelegramClient("TOK", httpx.Client(transport=httpx.MockTransport(handle)))
    assert tg.send_document(5, str(f), "подпись", reply_to="3") == "9"
    body = seen[0].read()
    assert seen[0].url.path.endswith("/sendDocument") and b'filename="x.csv"' in body
    assert b"a;b" in body and b"\r\n5\r\n" in body
    bad = TelegramClient("TOK", httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500, json={"ok": False}))))
    try:
        bad.send_document(5, str(f))
    except TelegramError as exc:
        assert exc.outcome == "unknown"


def test_full_http_path_to_log_handler_has_no_secrets(env: Any) -> None:
    """F1: настоящие клиенты httpx -> logging -> обработчик; секретов в журнале нет."""
    import io

    from support_agent.runner import install_logging

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    old_level, old_handlers = root.level, list(root.handlers)
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    try:
        install_logging(env.cfg)

        def answer(request: httpx.Request) -> httpx.Response:
            if "telegram" in request.url.host:
                return httpx.Response(200, json={"ok": True, "result": []})
            return httpx.Response(200, json={"id": "c"})

        http = httpx.Client(transport=httpx.MockTransport(answer))
        TelegramClient(env.cfg.telegram.bot_token, http).get_updates(0, 1)
        TrelloClient(env.cfg.trello, http).get_card("c1")
        # даже если кто-то поднимет httpx до INFO, URL с токенами маскируется обработчиком
        logging.getLogger("httpx").setLevel(logging.INFO)
        http.get(f"https://api.telegram.org/bot{env.cfg.telegram.bot_token}/getMe")
        http.get(f"https://api.trello.com/1/cards/c?key={env.cfg.trello.api_key}&token={env.cfg.trello.token}")
        try:
            raise RuntimeError(f"падение с {env.cfg.trello.token} и bot{env.cfg.telegram.bot_token}")
        except RuntimeError:
            logging.getLogger("support_agent.test").exception("ошибка %s", env.cfg.wms.agent_key)
        logging.getLogger("support_agent.test").warning("Bearer sk-abcdefghijklmnop1234 token=zzzzzzzzz")
    finally:
        root.handlers = old_handlers
        root.setLevel(old_level)
        logging.getLogger("httpx").setLevel(logging.WARNING)
    out = stream.getvalue()
    assert out  # запись действительно дошла до обработчика
    for secret in (*env.cfg.secrets(), "SECRET-BOT-TOKEN", "abcdefghijklmnop1234", "zzzzzzzzz"):
        assert secret not in out, secret
    assert "bot***" in out and "Traceback" in out
