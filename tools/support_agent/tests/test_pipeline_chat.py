"""R1-R3, R7-R18: приём, фильтр, ворох, классификация, разбор, вопросы клиенту, карточки."""

from __future__ import annotations

import re
from typing import Any

from support_agent.llm import LlmUnavailable
from support_agent.pipeline import FORBIDDEN_IN_SUMMARY
from support_agent.telegram import Inbound, flush_outbox, normalize_update

from .conftest import CLIENT_CHAT, OWNER_CHAT, OWNER_ID

ANALYSIS_BUG: dict[str, Any] = {
    "category": "bug", "urgent": True, "urgency_reason": "не может передать поставку",
    "need_data": None, "problem_steps": ["Оператор нажимает «Передать»", "Появляется ошибка"],
    "why": "не срабатывает проверка статуса", "proposed_solution": "поправить проверку статуса",
    "why_this_solution": "это единственное место", "info_answer": None, "improvement_card": None,
    "hotfix": {"safe": True, "reason": "одна правка", "needs_migration": False,
               "single_process": True, "touches_frontend": False, "affected": ["передача поставки"]},
}


def script(env: Any, analysis: dict[str, Any] | None = None, category: str = "bug",
           confidence: str = "high") -> None:
    llm = env.llm

    def filt(prompt: str, kw: Any) -> dict[str, Any]:
        body = prompt.split("<<<ДАННЫЕ\n")[1].split("\nДАННЫЕ>>>")[0]
        if "привет" in body.lower():
            return {"relevant": False, "ticket_id": None}
        if "[новая]" in body:
            return {"relevant": True, "ticket_id": None}
        match = re.search(r"- обращение (\d+):", prompt)
        return {"relevant": True, "ticket_id": int(match.group(1)) if match else None}

    llm.on("filter", "Новое сообщение из клиентского чата", filt)
    llm.on("filter", "Классифицируй", {"category": category, "confidence": confidence,
                                      "title": "Не передаётся поставка"})
    llm.on("analyst", "Разберись", analysis or ANALYSIS_BUG)
    llm.on("routine", "короткую сводку", "Что не работает: передача поставки.\nПочему: статус.\nРешение: правка.")
    llm.on("routine", "Перепиши сводку", "Переписанная сводка без техники.")
    llm.on("review", "что ещё сломается", {"verdict": "safe", "risks": [], "affected": []})


def run_until_report(env: Any) -> None:
    env.pipe.tick()
    env.clock.advance(130)
    env.pipe.tick()


def test_unlisted_chat_and_foreign_owner_chat_messages_are_not_stored(env: Any) -> None:
    cfg = env.cfg
    good = {"update_id": 1, "message": {"message_id": 7, "chat": {"id": CLIENT_CHAT}, "date": 100,
            "from": {"id": 5, "first_name": "Анна"}, "text": "не открывается поставка"}}
    alien = {"update_id": 2, "message": {"message_id": 8, "chat": {"id": -555}, "date": 100,
             "from": {"id": 5}, "text": "реклама"}}
    foreign_in_owner = {"update_id": 3, "message": {"message_id": 9, "chat": {"id": OWNER_CHAT},
                        "date": 100, "from": {"id": 777}, "text": "кати"}}
    bot = {"update_id": 4, "message": {"message_id": 10, "chat": {"id": CLIENT_CHAT}, "date": 1,
           "from": {"id": 9, "is_bot": True}, "text": "x"}}
    got = [normalize_update(u, cfg) for u in (good, alien, foreign_in_owner, bot)]
    assert got[0] is not None and got[0].role == "client" and got[0].text.startswith("не открывается")
    assert got[1] is None and got[2] is None and got[3] is None
    owner = {"update_id": 5, "message": {"message_id": 11, "chat": {"id": OWNER_CHAT}, "date": 1,
             "from": {"id": OWNER_ID}, "text": "кати"}}
    assert normalize_update(owner, cfg).role == "owner"  # type: ignore[union-attr]


def test_same_message_delivered_twice_is_stored_once(env: Any) -> None:
    script(env)
    assert env.say(CLIENT_CHAT, "не открывается", msg_id="77") is not None
    assert env.say(CLIENT_CHAT, "не открывается", msg_id="77") is None
    assert len(env.store.rows("SELECT * FROM messages")) == 1


def test_new_source_goes_through_same_steps_without_changes(env: Any) -> None:
    """C2: заглушка нового источника выдаёт Inbound и проходит фильтр, разбор и сводку."""
    script(env)
    env.pipe.ingest(Inbound(source="stub-source", chat_id=CLIENT_CHAT, msg_id="s1", role="client",
                            author_id="1", author_name="Заглушка", ts=env.clock.now, kind="text",
                            text="не работает передача поставки"))
    run_until_report(env)
    assert env.store.tickets_in("await_urgency")


def test_chatter_is_dropped_without_reply_or_summary(env: Any) -> None:
    script(env)
    env.say(CLIENT_CHAT, "Привет всем!")
    env.pipe.tick()
    env.flush()
    assert env.store.messages_with_status("dropped")
    assert env.tg.sent == [] and not env.store.rows("SELECT * FROM tickets")


def test_burst_is_one_ticket_late_message_attaches_new_topic_is_new(env: Any) -> None:
    script(env)
    for i in range(5):
        env.say(CLIENT_CHAT, f"не работает передача поставки {i}")
    env.clock.advance(10)
    assert len(env.store.rows("SELECT * FROM tickets")) == 1
    assert len(env.store.ticket_messages(1)) == 5
    env.pipe.tick()  # тишины ещё нет: разбор не начался
    assert env.store.ticket(1)["stage"] == "collecting"
    env.clock.advance(130)
    env.pipe.tick()
    assert env.store.ticket(1)["stage"] == "await_urgency"
    env.say(CLIENT_CHAT, "и ещё та же поставка")  # позже, та же тема
    assert len(env.store.rows("SELECT * FROM tickets")) == 1
    assert len(env.store.ticket_messages(1)) == 6
    env.say(CLIENT_CHAT, "[новая] нужна выгрузка")
    assert len(env.store.rows("SELECT * FROM tickets")) == 2


def test_doubt_is_not_dropped(env: Any) -> None:
    script(env)
    env.llm.on("filter", "Новое сообщение из клиентского чата", {"relevant": "unsure", "ticket_id": None})
    env.say(CLIENT_CHAT, "[новая] что-то странное")
    assert env.store.rows("SELECT * FROM tickets")


def test_bug_asks_urgency_once_and_no_answer_is_noted(env: Any) -> None:
    script(env)
    env.say(CLIENT_CHAT, "не работает передача поставки", msg_id="500")
    run_until_report(env)
    env.flush()
    assert env.tg.sent == [(CLIENT_CHAT, "Подскажите, пожалуйста: это прямо сейчас мешает работе или "
                            "можно исправить позже?", "500")]
    env.clock.advance(1000)  # клиент молчит дольше срока
    env.pipe.tick()
    env.clock.advance(60)
    env.pipe.tick()
    env.flush()
    assert len(env.tg.to(CLIENT_CHAT)) == 1  # повторного вопроса нет
    report = env.store.data(1)["report"]["body"]
    assert "не ответил" in report
    assert env.store.ticket(1)["stage"] == "await_owner"


def test_client_answer_is_attached_and_disagreement_shown(env: Any) -> None:
    analysis = dict(ANALYSIS_BUG, urgent=False, urgency_reason="есть обходной путь")
    script(env, analysis)
    env.say(CLIENT_CHAT, "не работает передача поставки", msg_id="500")
    run_until_report(env)
    env.flush()
    question_id = env.store.rows("SELECT tg_message_id FROM outbox")[0]["tg_message_id"]
    env.say(CLIENT_CHAT, "срочно, мы встали и не можем работать", reply_to=question_id)
    env.pipe.tick()
    assert env.store.data(1)["urgency_client"].startswith("срочно")
    env.clock.advance(60)
    env.pipe.tick()
    body = env.store.data(1)["report"]["body"]
    assert "расходится" in body


def test_hotfix_verdict_needs_crosscheck_and_migration_means_no(env: Any) -> None:
    script(env)
    env.say(CLIENT_CHAT, "не работает передача поставки")
    run_until_report(env)
    env.pipe.tick()
    env.clock.advance(1000)
    env.pipe.tick()
    env.clock.advance(60)
    env.pipe.tick()
    data = env.store.data(1)
    assert data["verdict"] == "hotfix" and data["hotfix_ok"] is True
    assert data["cross"]["verdict"] == "safe"
    review_calls = [c for c in env.llm.calls if c["role"] == "review"]
    assert len(review_calls) == 1 and review_calls[0]["exclude_cli"] == "claude"
    # миграция схемы или несколько процессов -> «нельзя коротким» (R15), даже если модель сказала safe
    env.say(CLIENT_CHAT, "[новая] другая проблема")
    migr = dict(ANALYSIS_BUG, hotfix={**ANALYSIS_BUG["hotfix"], "needs_migration": True})
    env.llm.on("analyst", "Разберись", migr)
    env.clock.advance(130)
    env.pipe.tick()
    env.clock.advance(1000)
    env.pipe.tick()
    env.clock.advance(60)
    env.pipe.tick()
    second = env.store.data(2)
    assert second["verdict"] == "bug_no_hotfix" and second["hotfix_ok"] is False
    assert second["cross"] is None  # нет хотфикса — нечего перепроверять


def test_crosscheck_unavailable_is_stated_honestly(env: Any) -> None:
    script(env)

    def review(prompt: str, kw: Any) -> Any:
        raise LlmUnavailable("codex_limit")

    env.llm.on("review", "что ещё сломается", review)
    env.say(CLIENT_CHAT, "не работает передача поставки")
    run_until_report(env)
    env.clock.advance(1000)
    env.pipe.tick()
    env.clock.advance(60)
    env.pipe.tick()
    assert "Перекрёстная проверка не проведена" in env.store.data(1)["report"]["body"]


def test_ask_for_data_once_answer_joins_same_ticket_and_session(env: Any) -> None:
    need = dict(ANALYSIS_BUG, need_data={"why": "найти поставку", "points": ["номер поставки", "скриншот"]})
    script(env, need)
    env.say(CLIENT_CHAT, "не получается передать поставку", msg_id="9")
    run_until_report(env)
    env.clock.advance(1000)
    env.pipe.tick()  # срочность: молчание -> разбор
    env.flush()
    texts = env.tg.to(CLIENT_CHAT)
    assert any(t.startswith("Чтобы разобраться, пришлите") and "1. номер поставки" in t for t in texts)
    asks_before = len(texts)
    env.say(CLIENT_CHAT, "номер 12345", user=5)
    env.llm.on("analyst", "Разберись", ANALYSIS_BUG)
    env.pipe.tick()
    env.flush()
    assert len(env.tg.to(CLIENT_CHAT)) == asks_before  # второй просьбы по той же нехватке нет
    assert len(env.store.rows("SELECT * FROM tickets")) == 1
    analyst_calls = [c for c in env.llm.calls if c["role"] == "analyst"]
    assert all(c["session_key"] == "analyst" and c["ticket_id"] == 1 for c in analyst_calls)
    assert "Клиент ответил" in analyst_calls[-1]["prompt"]


def test_no_question_when_data_is_enough(env: Any) -> None:
    script(env)
    env.say(CLIENT_CHAT, "не работает передача поставки")
    run_until_report(env)
    env.clock.advance(1000)
    env.pipe.tick()
    env.flush()
    assert not any(t.startswith("Чтобы разобраться") for t in env.tg.to(CLIENT_CHAT))


def test_only_allowed_messages_go_to_client(env: Any) -> None:
    script(env)
    env.say(CLIENT_CHAT, "не работает передача поставки")
    run_until_report(env)
    env.clock.advance(1000)
    env.pipe.tick()
    env.clock.advance(60)
    env.pipe.tick()
    env.flush()
    for text in env.tg.to(CLIENT_CHAT):
        assert "приняли" not in text.lower() and "срок" not in text.lower()
    assert len(env.tg.to(CLIENT_CHAT)) == 1  # только вопрос о срочности


def test_improvement_creates_exactly_one_card_with_label_and_marker(env: Any) -> None:
    improvement = dict(ANALYSIS_BUG, category="improvement", urgent=False,
                       improvement_card={"title": "Кнопка массового переноса", "description": "хочу удобнее"})
    script(env, improvement, category="improvement")
    env.say(CLIENT_CHAT, "хотим кнопку массового переноса", msg_id="31")
    run_until_report(env)
    env.pipe.tick()
    assert env.trello.creates == 1
    card = next(iter(env.trello.cards.values()))
    assert card["idList"] == "L_CLIENT" and card["label"] == "LABEL_CLIENT"
    assert "Клиент: ИП Тест" in card["name"] and "WMS-AGENT-ID: ticket:1" in card["desc"].splitlines()
    assert "t.me/c/" in card["desc"]
    env.clock.advance(100)
    env.pipe.tick()
    assert len(env.store.rows("SELECT * FROM outbox WHERE purpose='summary'")) == 1
    env.pipe._card_for(1, improvement)  # повторная обработка
    assert env.trello.creates == 1
    assert env.store.ticket(1)["stage"] == "done"


def test_form_improvement_gets_only_a_comment_never_a_card(env: Any) -> None:
    improvement = dict(ANALYSIS_BUG, category="improvement", urgent=False)
    script(env, improvement, category="improvement")
    row = form_row("r-1", "improvement", card="cX")
    env.trello.cards["cX"] = {"id": "cX", "idList": "L_REVIEW", "desc": "WMS-REQUEST-ID: r-1",
                              "shortUrl": "u"}
    env.wms.rows = [row]
    env.pipe.poll_forms()
    env.pipe.tick()
    env.pipe.sync_form_cards()
    assert env.trello.creates == 0
    assert len(env.trello.comments_by["cX"]) == 1
    env.pipe.sync_form_cards()
    assert len(env.trello.comments_by["cX"]) == 1


def form_row(rid: str, typ: str, card: str | None = None) -> dict[str, Any]:
    return {"id": rid, "type": typ, "title": "Заголовок", "description": "Не работает" if typ == "bug" else None,
            "screen": "Упаковка" if typ != "bug" else None, "problem": "долго" if typ != "bug" else None,
            "proposal": "быстрее" if typ != "bug" else None, "page_url": "/fbs", "client_name": "Орг / Селлер",
            "status": "review", "created_at": f"2026-10-02T10:00:0{rid[-1]}+00:00", "updated_at": "x",
            "delivery_state": "linked" if card else "pending", "trello_card_id": card}


def test_form_ticket_never_asks_author_and_marks_type_mismatch(env: Any) -> None:
    """R7: у формы нет канала к автору; расхождение типа попадает в сводку."""
    script(env, dict(ANALYSIS_BUG, need_data={"why": "x", "points": ["номер поставки"]}),
           category="bug")
    env.wms.rows = [form_row("r-2", "improvement")]
    env.pipe.poll_forms()
    env.pipe.tick()
    env.flush()
    assert env.tg.sent == []  # ни вопросов, ни просьб клиенту
    d = env.store.data(1)
    assert d["type_mismatch"] is True
    env.clock.advance(100)
    env.pipe.tick()
    assert "Данных не хватает: номер поставки" in env.store.data(1)["report"]["body"]
    assert "Тип в форме не совпал" in env.store.data(1)["report"]["body"]


def test_form_polling_is_idempotent_and_no_card_without_link(env: Any) -> None:
    script(env)
    env.wms.rows = [form_row("r-3", "bug")]
    env.pipe.poll_forms()
    env.pipe.poll_forms()
    assert len(env.store.rows("SELECT * FROM tickets")) == 1
    env.pipe.tick()
    env.clock.advance(100)
    env.pipe.tick()
    env.pipe.sync_form_cards()
    assert env.trello.creates == 0 and env.trello.comments_by == {}
    # связь появилась -> один комментарий; описание и маркер карточки не тронуты
    env.wms.by_id["r-3"] = form_row("r-3", "bug", card="cZ")
    env.trello.cards["cZ"] = {"id": "cZ", "idList": "L_REVIEW", "desc": "WMS-REQUEST-ID: r-3",
                              "shortUrl": "u"}
    env.pipe.sync_form_cards()
    env.pipe.sync_form_cards()
    assert len(env.trello.comments_by["cZ"]) == 1
    assert env.trello.cards["cZ"]["desc"] == "WMS-REQUEST-ID: r-3"


def test_card_with_foreign_marker_is_not_commented(env: Any) -> None:
    script(env)
    env.wms.rows = [form_row("r-4", "bug", card="cW")]
    env.trello.cards["cW"] = {"id": "cW", "idList": "L", "desc": "чужая карточка", "shortUrl": "u"}
    env.pipe.poll_forms()
    env.pipe.tick()
    env.clock.advance(100)
    env.pipe.tick()
    env.pipe.sync_form_cards()
    assert env.trello.comments_by == {}


def test_info_request_answer_waits_for_owner_go(env: Any) -> None:
    info = dict(ANALYSIS_BUG, category="info", info_answer="Не переданы короба 3 и 5", hotfix={})
    script(env, info, category="info")
    env.say(CLIENT_CHAT, "какие короба мы не отдали?", msg_id="60")
    run_until_report(env)
    env.clock.advance(100)
    env.pipe.tick()
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []  # клиенту ничего до «кати»
    assert env.store.data(1)["verdict"] == "info"
    assert "Не переданы короба 3 и 5" in env.tg.to(OWNER_CHAT)[0]
    script_owner(env, {"intent": "go", "ticket_ids": [1], "all": False})
    env.say(OWNER_CHAT, "кати", user=OWNER_ID, name="Владелец")
    env.pipe.tick()
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == ["Не переданы короба 3 и 5"]


def script_owner(env: Any, parsed: dict[str, Any]) -> None:
    env.llm.on("filter", "Владелец склада ответил", parsed)


def test_other_and_low_confidence_go_to_owner_without_card_or_hotfix(env: Any) -> None:
    script(env, category="bug", confidence="low")
    env.say(CLIENT_CHAT, "не знаю как сказать")
    run_until_report(env)
    env.clock.advance(100)
    env.pipe.tick()
    d = env.store.data(1)
    assert d["verdict"] == "other" and "hotfix_ok" not in d
    assert env.trello.creates == 0
    assert env.store.ticket(1)["stage"] == "await_owner"
    env.flush()
    assert env.tg.to(OWNER_CHAT)[0].startswith("Обращение №1 · Клиент: ИП Тест")


def test_summary_header_has_client_and_no_technical_details(env: Any) -> None:
    script(env)
    env.llm.on("routine", "короткую сводку", "Передача: см. services/foo.py и штрихкод 4600000000001")
    env.say(CLIENT_CHAT, "не работает передача поставки")
    run_until_report(env)
    env.clock.advance(1000)
    env.pipe.tick()
    env.clock.advance(60)
    env.pipe.tick()
    env.flush()
    owner = env.tg.to(OWNER_CHAT)
    assert owner and owner[0].startswith("Обращение №1 · Клиент: ИП Тест")
    assert not FORBIDDEN_IN_SUMMARY.search(owner[0])


def test_batch_of_hotfixes_gets_reconciliation_in_one_portion(env: Any) -> None:
    script(env)
    env.llm.on("analyst", "сверь", None)  # не используется
    env.llm.on("analyst", "Параллельно подготовлено", "Первое и второе правят один процесс: по очереди.")
    env.say(CLIENT_CHAT, "[новая] проблема один")
    env.say(CLIENT_CHAT, "[новая] проблема два", user=6)
    env.clock.advance(130)
    env.pipe.tick()
    env.clock.advance(1000)
    env.pipe.tick()
    env.clock.advance(60)
    env.pipe.tick()
    env.flush()
    owner = env.tg.to(OWNER_CHAT)
    assert any("Сверка хотфиксов" in t and "по очереди" in t for t in owner)
    assert sum(1 for t in owner if t.startswith("Обращение №")) == 2


def test_voice_is_transcribed_before_filter_and_marked(env: Any) -> None:
    script(env)
    env.tg.files["f1"] = b"audio"
    env.say(CLIENT_CHAT, "", voice=True)
    env.pipe.tick()
    msg = env.store.rows("SELECT * FROM messages")[0]
    assert msg["status"] == "attached" and msg["text"].startswith("(расшифровка голосового)")
    assert "не открывается поставка" in msg["text"]


def test_voice_failure_retries_then_tells_owner_and_not_client(env: Any) -> None:
    script(env)
    env.tg.files["f1"] = b"audio"
    env.tr.fail = 99
    env.say(CLIENT_CHAT, "", voice=True)
    for _ in range(6):
        env.pipe.tick()
        env.clock.advance(300)
    env.flush()
    assert env.store.messages_with_status("transcribe_failed")
    assert any("не расшифровано" in t for t in env.tg.to(OWNER_CHAT))
    assert env.tg.to(CLIENT_CHAT) == []
    # сообщение не потеряно: оно осталось в базе вместе с file_id
    assert env.store.rows("SELECT file_id FROM messages")[0]["file_id"] == "f1"


def test_outbox_key_makes_message_once(env: Any) -> None:
    assert env.store.queue_message(key="k", chat_id=CLIENT_CHAT, text="a")
    assert not env.store.queue_message(key="k", chat_id=CLIENT_CHAT, text="a")
    env.flush()
    env.flush()
    assert len(env.tg.sent) == 1
    flush_outbox(env.store, env.tg, env.cfg)
    assert len(env.tg.sent) == 1
