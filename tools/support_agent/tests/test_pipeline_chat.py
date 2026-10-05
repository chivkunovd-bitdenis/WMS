"""R1-R3, R7-R18: приём, фильтр, ворох, классификация, разбор, вопросы клиенту, карточки."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from support_agent.llm import ExecResult, LlmRouter, LlmUnavailable
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


def test_filter_gets_full_voice_request_and_numbered_followups_without_forced_merging(env: Any) -> None:
    script(env)
    voice = ("(расшифровка голосового) Денис, помнишь момент был, сейчас ещё Светлана напишет детали. "
             "Нужно вернуть работу с коробами в возврате, создавать заданное число коробов "
             "в приёмке и возврате и печатать номер короба с уникальным кодом и номером документа.")
    first_detail = "Создаём возврат и вводим 200 коробов вместо добавления каждого вручную."
    third_request = "2. Нужно вывести номер короба, уникальный код и номер документа на этикетку и лист подбора."
    env.say(CLIENT_CHAT, voice, msg_id="voice-source")
    assert env.store.data(1)["title"] == voice[:60]

    def followup(prompt: str, kw: Any) -> dict[str, Any]:
        current = prompt.split("<<<ДАННЫЕ\n")[1].split("\nДАННЫЕ>>>")[0]
        # Проверяется настоящий prompt Pipeline, а не отдельно собранный образец.
        assert voice in prompt
        assert "Нумерованное дополнение" in prompt
        if current == third_request:
            assert first_detail in prompt
        return {"relevant": True, "ticket_id": 1 if current in (first_detail, third_request) else None}

    env.llm.on("filter", "Новое сообщение из клиентского чата", followup)
    env.say(CLIENT_CHAT, first_detail, msg_id="followup-one", user=6)
    env.say(CLIENT_CHAT, third_request, msg_id="followup-two", user=6)
    assert len(env.store.rows("SELECT * FROM tickets")) == 1
    assert [m["text"] for m in env.store.ticket_messages(1)] == [voice, first_detail, third_request]
    env.say(CLIENT_CHAT, "Отдельная задача: нужен отчёт по стоимости хранения", msg_id="independent")
    assert len(env.store.rows("SELECT * FROM tickets")) == 2
    assert env.store.ticket_messages(2)[0]["text"].startswith("Отдельная задача")


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
    assert len(review_calls) == 1 and review_calls[0]["cli_only"] == "codex"
    assert review_calls[0]["session_key"] == "review"
    assert review_calls[0].get("exclude_cli") is None
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


def test_codex_analyst_crosscheck_reaches_astra_high_in_separate_session(env: Any) -> None:
    tid = env.store.add_ticket(kind="chat", source="telegram", chat_id=CLIENT_CHAT,
                               seller="seller", stage="analysis", data={"analyst_cli": "codex"})
    env.store.kv_set(f"background_context:role:{tid}:analyst:shared:readonly",
                     [{"prompt": "private analyst turn", "answer": "analyst hypothesis"}])
    calls = []

    def execute(argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        calls.append((argv, stdin))
        Path(argv[argv.index("-o") + 1]).write_text(json.dumps({
            "verdict": "safe", "risks": [], "affected": ["передача поставки"],
        }))
        return ExecResult(0, "", "")

    env.pipe.llm = LlmRouter(env.cfg, env.store, exec_fn=execute)
    result = env.pipe._crosscheck(tid, ANALYSIS_BUG, "codex")
    assert result["verdict"] == "safe" and result["by"] == "gpt-6-astra"
    assert len(calls) == 1
    argv, prompt = calls[0]
    assert argv[0] == "codex" and argv[argv.index("-m") + 1] == "gpt-6-astra"
    assert 'model_reasoning_effort="high"' in argv
    assert "private analyst turn" not in (prompt or "")
    history = env.store.kv_get(f"background_context:role:{tid}:review:shared:readonly")
    assert len(history) == 1 and "что ещё сломается" in history[0]["prompt"]


@pytest.mark.parametrize("failure", ["model_error", "cooldown"])
def test_codex_analyst_crosscheck_never_falls_back_when_astra_unavailable(
    env: Any, failure: str,
) -> None:
    tid = env.store.add_ticket(kind="chat", source="telegram", chat_id=CLIENT_CHAT,
                               seller="seller", stage="analysis")
    calls = []

    def execute(argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        calls.append(argv)
        return ExecResult(1, "", "Astra unavailable")

    env.pipe.llm = LlmRouter(env.cfg, env.store, exec_fn=execute)
    if failure == "cooldown":
        env.store.kv_set("cooldown:codex", 10**12)
    result = env.pipe._crosscheck(tid, ANALYSIS_BUG, "codex")
    assert result["verdict"] == "not_done"
    assert len(calls) == (1 if failure == "model_error" else 0)
    assert all(argv[0] == "codex" and argv[argv.index("-m") + 1] == "gpt-6-astra"
               and 'model_reasoning_effort="high"' in argv for argv in calls)


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


@pytest.mark.parametrize(("state", "expected"), [
    ("none", "Создание карточки в Trello не подтверждено."),
    ("not_configured", "Карточка в Trello не создана: Trello не настроен."),
    ("unknown", "Карточка в Trello: исход создания неизвестен, повторно не создаю."),
    ("rejected", "Карточку в Trello создать не удалось (отказ Trello)."),
    ("linked", "Карточка в Trello создана: https://trello.test/c1"),
])
def test_improvement_summary_gets_actual_card_outcome(env: Any, state: str, expected: str) -> None:
    improvement = dict(ANALYSIS_BUG, category="improvement", urgent=False)
    script(env, improvement, category="improvement")
    tid = env.store.add_ticket(kind="form" if state == "none" else "chat", source="test",
                               chat_id=CLIENT_CHAT, seller="ИП Тест", stage="analysis")
    if state == "not_configured":
        env.cfg.trello.api_key = ""
    elif state == "unknown":
        env.trello.lose_response_once = True
        env.trello.hide_after_lose = True
    elif state == "rejected":
        env.trello.reject = True
    card_note = env.pipe._card_for(tid, improvement)
    body = env.pipe._compose(tid, improvement, "trello", None, card_note)
    prompt = env.llm.calls[-1]["prompt"]
    trusted_note = prompt.split("\n\nМатериалы:")[0]
    assert "Вердикт: это улучшение." in trusted_note
    assert "ушло в Trello" not in trusted_note
    assert expected in trusted_note
    assert "Не утверждай создание карточки без подтверждения" in trusted_note
    if state == "linked":
        assert env.store.data(tid)["card_url"] == "https://trello.test/c1"
    else:
        assert "Карточка в Trello создана:" not in trusted_note
        assert "card_id" not in env.store.data(tid)
    if card_note:
        assert body.endswith(card_note)  # фактический исход добавляется кодом и к готовой сводке


@pytest.mark.parametrize(("kind", "need_data", "answer_needs_data", "keeps_missing"), [
    ("chat", None, False, False),
    ("form", None, False, True),
    ("chat", {"points": ["Какой лист подбора?"]}, False, True),
    ("chat", None, True, True),
])
def test_chat_summary_does_not_invent_a_question_from_form_only_field(
    env: Any, kind: str, need_data: Any, answer_needs_data: bool, keeps_missing: bool,
) -> None:
    missing = "Уточнить у клиента какой лист подбора"
    analysis = dict(ANALYSIS_BUG, category="improvement", need_data=need_data,
                    missing_for_owner=[missing], answer_needs_data=answer_needs_data)
    script(env, analysis)
    tid = env.store.add_ticket(kind=kind, source="test", chat_id=CLIENT_CHAT, seller="Клиент",
                               stage="analysis")
    card_note = " Карточка в Trello создана: https://trello.test/existing"
    env.pipe._compose(tid, analysis, "trello", None, card_note)
    prompt = env.llm.calls[-1]["prompt"]
    assert (missing in prompt) is keeps_missing
    assert card_note.strip() in prompt
    if not keeps_missing:
        assert "Новый вопрос клиенту не планируется" in prompt
        assert "не ставь передачу задачи в Trello в зависимость от уточнения" in prompt
    assert analysis["missing_for_owner"] == [missing]  # сохранённый результат аналитика не переписывается


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


def info_ticket(env: Any, text: str, msg_id: str, user: int = 5, file: str | None = None) -> None:
    analysis = dict(ANALYSIS_BUG, category="info", info_answer=text, hotfix={},
                    info_file={"filename": "short.csv", "content": file} if file else None)
    env.llm.on("analyst", "Разберись", analysis)
    env.llm.on("filter", "Классифицируй", {"category": "info", "confidence": "high", "title": "запрос"})
    env.say(CLIENT_CHAT, f"[новая] выгрузка нужна {msg_id}", msg_id=msg_id, user=user)


def finish_reports(env: Any) -> None:
    env.clock.advance(130)
    env.pipe.tick()
    env.clock.advance(100)
    env.pipe.tick()
    env.flush()


def test_info_answer_is_previewed_verbatim_and_sent_only_after_confirmation(env: Any) -> None:
    script(env, dict(ANALYSIS_BUG, category="info", info_answer="Не переданы короба 3 и 5", hotfix={}),
           category="info")
    env.say(CLIENT_CHAT, "какие короба мы не отдали?", msg_id="60")
    run_until_report(env)
    env.clock.advance(100)
    env.pipe.tick()
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []  # клиенту ничего до подтверждения
    assert env.store.data(1)["verdict"] == "info"
    owner = env.tg.to(OWNER_CHAT)
    preview = next(t for t in owner if t.startswith("Предпросмотр для клиента «ИП Тест»"))
    assert "———\nНе переданы короба 3 и 5\n———" in preview  # ровно то, что уйдёт клиенту
    assert not any("Не переданы короба" in t for t in owner if t is not preview)  # не в сводке
    script_owner(env, {"intent": "go", "ticket_ids": [1], "all": False})
    env.say(OWNER_CHAT, "кати 1", user=OWNER_ID, name="Владелец")
    env.pipe.tick()
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == ["Не переданы короба 3 и 5"]
    env.say(OWNER_CHAT, "кати 1 ещё раз", user=OWNER_ID, name="Владелец")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == ["Не переданы короба 3 и 5"]  # второй раз не уходит


def test_generic_go_with_two_previews_sends_nothing_reply_picks_exact_one(env: Any) -> None:
    script(env)
    info_ticket(env, "ответ первому", "71", user=5)
    info_ticket(env, "ответ второму", "72", user=6)
    finish_reports(env)
    assert len(env.store.rows("SELECT * FROM tickets WHERE stage='await_owner'")) == 2
    script_owner(env, {"intent": "go", "ticket_ids": [], "all": False})
    env.say(OWNER_CHAT, "кати", user=OWNER_ID, name="Владелец")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []  # любое «кати» ничего не подтверждает
    assert "Не понял" in env.tg.to(OWNER_CHAT)[-1]
    script_owner(env, {"intent": "go", "ticket_ids": [], "all": True})
    env.say(OWNER_CHAT, "всё кати", user=OWNER_ID, name="Владелец")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []  # даже «всё кати» не подтверждает ответы клиентам
    second_preview = env.store.outbox_by_key("preview:2")["tg_message_id"]
    script_owner(env, {"intent": "go", "ticket_ids": [], "all": False})
    env.say(OWNER_CHAT, "кати", user=OWNER_ID, name="Владелец", reply_to=second_preview)
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == ["ответ второму"]
    assert env.store.ticket(1)["stage"] == "await_owner"


def test_no_send_before_preview_is_delivered_or_after_it_changed(env: Any) -> None:
    script(env)
    info_ticket(env, "точный текст", "81")
    env.clock.advance(130)
    env.pipe.tick()
    env.clock.advance(100)
    env.pipe.tick()  # сводка и предпросмотр поставлены в очередь, но не отправлены (нет flush)
    script_owner(env, {"intent": "go", "ticket_ids": [1], "all": False})
    env.say(OWNER_CHAT, "кати 1", user=OWNER_ID, name="Владелец")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []  # до доставки предпросмотра клиенту не уходит
    env.flush()
    data = env.store.data(1)
    env.store.patch_data(1, client_answer={**data["client_answer"], "text": "подменённый текст"})
    env.say(OWNER_CHAT, "кати 1", user=OWNER_ID, name="Владелец", msg_id="again")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []
    assert any("изменилось после предпросмотра" in t for t in env.tg.to(OWNER_CHAT))


def test_file_export_is_previewed_as_document_and_sent_only_after_confirmation(env: Any) -> None:
    script(env)
    info_ticket(env, "Выгрузка во вложении", "91", file="qr;box\n1;A\n2;B\n")
    finish_reports(env)
    assert [d[0] for d in env.tg.documents] == [OWNER_CHAT]
    path = Path(env.tg.documents[0][1])
    assert path.read_text(encoding="utf-8") == "qr;box\n1;A\n2;B\n" and path.name == "export-1-0.csv"
    assert any(t.startswith("Предпросмотр") and "Выгрузка во вложении" in t for t in env.tg.to(OWNER_CHAT))
    preview_file = env.store.outbox_by_key("preview_file0:1")["tg_message_id"]
    script_owner(env, {"intent": "go", "ticket_ids": [], "all": False})
    env.say(OWNER_CHAT, "кати", user=OWNER_ID, name="Владелец", reply_to=preview_file)
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == ["Выгрузка во вложении"]
    assert [d[0] for d in env.tg.documents] == [OWNER_CHAT, CLIENT_CHAT]
    assert env.tg.documents[1][1] == str(path)


def test_file_changed_after_preview_is_not_sent(env: Any) -> None:
    script(env)
    info_ticket(env, "Выгрузка", "92", file="a;b\n")
    finish_reports(env)
    Path(env.store.data(1)["client_answer"]["files"][0]).write_text("подмена", encoding="utf-8")
    script_owner(env, {"intent": "go", "ticket_ids": [1], "all": False})
    env.say(OWNER_CHAT, "кати 1", user=OWNER_ID, name="Владелец")
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == [] and [d[0] for d in env.tg.documents] == [OWNER_CHAT]


def script_owner(env: Any, parsed: dict[str, Any]) -> None:
    intent = str(parsed.get("intent", "other"))
    ids = list(parsed.get("ticket_ids") or [])
    if parsed.get("all"):
        ids = [int(t["id"]) for t in env.store.open_tickets()]
    actions = ([{"kind": intent, "ticket_ids": ids, "note": "поручение владельца"}]
               if intent in ("go", "reject", "postpone", "mockup_yes", "mockup_no") else [])
    env.llm.on("routine", "Владелец склада написал",
               {"scope": "wms", "reply": "Понял.", "actions": actions, "listed_ticket_ids": []})


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


def test_message_that_keeps_failing_is_reported_not_looped(env: Any) -> None:
    def boom(prompt: str, kw: Any) -> Any:
        raise KeyError("unexpected")

    env.llm.on("filter", "Новое сообщение из клиентского чата", boom)
    env.say(CLIENT_CHAT, "не работает передача")
    for _ in range(4):
        env.pipe.tick()
    env.flush()
    assert env.store.messages_with_status("error")
    assert sum("обработать не получилось" in t for t in env.tg.to(OWNER_CHAT)) == 1
    assert env.tg.to(CLIENT_CHAT) == []


def test_default_bug_goes_straight_to_analysis_without_urgency_question(env: Any) -> None:
    """Владелец: клиента не дёргаем вопросом о срочности, её оценивает аналитик."""
    env.cfg.limits.ask_client_urgency = False
    script(env)
    env.say(CLIENT_CHAT, "не работает передача поставки", msg_id="500")
    run_until_report(env)
    env.clock.advance(60)
    env.pipe.tick()
    env.flush()
    assert env.tg.to(CLIENT_CHAT) == []
    assert not env.store.tickets_in("await_urgency")
    assert env.store.ticket(1)["stage"] == "await_owner"
    assert any(c["role"] == "analyst" for c in env.llm.calls)


def test_client_is_asked_at_most_once_per_ticket_and_at_most_two_questions(env: Any) -> None:
    """Даже если аналитик снова просит данные после ответа клиента, второго опроса нет."""
    env.cfg.limits.ask_client_urgency = False
    need = dict(ANALYSIS_BUG, need_data={"why": "x", "points": ["первое", "второе", "третье", "четвёртое"]})
    script(env, need)
    env.say(CLIENT_CHAT, "не получается передать поставку", msg_id="9")
    run_until_report(env)
    env.flush()
    asks = [t for t in env.tg.to(CLIENT_CHAT) if t.startswith("Чтобы разобраться")]
    assert len(asks) == 1
    assert "2. второе" in asks[0] and "третье" not in asks[0]
    env.say(CLIENT_CHAT, "вот ответ", user=5)
    env.pipe.tick()  # аналитик опять вернул need_data
    env.clock.advance(60)
    env.pipe.tick()
    env.flush()
    assert len([t for t in env.tg.to(CLIENT_CHAT) if t.startswith("Чтобы разобраться")]) == 1
    assert env.store.ticket(1)["stage"] == "await_owner"


def test_analyst_rules_require_own_investigation_before_asking() -> None:
    from support_agent import prompts

    rules = prompts.analyst_rules(prod_db=True)
    assert "клиент делает минимум" in rules
    assert "1–2 коротких точечных вопроса" in rules
    assert "Никогда не спрашивай то, что клиент уже написал" in rules
