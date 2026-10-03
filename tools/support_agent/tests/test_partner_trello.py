"""R28-R31, R35: партнёрский чат, подтверждение автором, одна карточка при любых сбоях."""

from __future__ import annotations

from typing import Any

from support_agent.pipeline import InlinePool, Pipeline
from support_agent.trello import ensure_card

from .conftest import OWNER_CHAT, PARTNER_CHAT, FakeLlm, FakeTelegram, FakeTranscriber, FakeWms

AUTHOR, OTHER = 11, 22


def script_partner(env: Any, is_ui: bool = False) -> None:
    llm = env.llm
    llm.on("filter", "Сообщение из партнёрского чата", {"is_task_request": True, "task": "сделать отчёт"})
    llm.on("routine", "Составь короткое структурное описание", {
        "title": "Отчёт по остаткам", "essence": "нужен отчёт", "expected": "кнопка выгрузки",
        "notes": ["срок не указан"], "is_ui": is_ui})
    llm.on("filter", "Описание задачи отправлено автору", {"intent": "confirm", "edit": ""})


def ask_task(env: Any, text: str = "Trello: внеси задачу, нужен отчёт по остаткам") -> None:
    env.say(PARTNER_CHAT, text, user=AUTHOR, name="Партнёр", msg_id="p1")
    env.pipe.tick()


def test_only_explicit_trello_requests_make_tasks(env: Any) -> None:
    script_partner(env)
    env.say(PARTNER_CHAT, "обсуждаем отгрузку", user=AUTHOR)  # без слова Trello: модель не вызывается
    assert env.llm.calls == [] and not env.store.rows("SELECT * FROM tickets")
    env.llm.on("filter", "Сообщение из партнёрского чата", {"is_task_request": False, "task": ""})
    env.say(PARTNER_CHAT, "в Trello видел карточку, ок", user=AUTHOR)
    assert not env.store.rows("SELECT * FROM tickets")
    env.flush()
    assert env.tg.sent == []


def test_draft_goes_to_author_and_only_author_can_confirm(env: Any) -> None:
    script_partner(env)
    env.llm.on("filter", "Сообщение из партнёрского чата", {"is_task_request": True, "task": "отчёт"})
    ask_task(env)
    env.flush()
    chat, text, reply = env.tg.sent[0]
    assert chat == PARTNER_CHAT and reply == "p1" and "Правильно ли я понял" in text
    assert "Отчёт по остаткам" in text and "срок не указан" in text
    assert env.store.ticket(1)["stage"] == "task_await_confirm"
    env.say(PARTNER_CHAT, "да", user=OTHER)  # чужое «да» не считается
    env.pipe.tick()
    assert env.store.ticket(1)["stage"] == "task_await_confirm" and env.trello.creates == 0
    env.say(PARTNER_CHAT, "да, правильно", user=AUTHOR)
    env.pipe.tick()
    assert env.store.ticket(1)["stage"] == "done" and env.trello.creates == 1


def test_edit_makes_new_version_then_confirm_creates_single_card(env: Any) -> None:
    script_partner(env)
    ask_task(env)
    env.llm.on("filter", "Описание задачи отправлено автору", {"intent": "edit", "edit": "добавить фильтр"})
    env.say(PARTNER_CHAT, "добавьте фильтр по складу", user=AUTHOR)
    env.pipe.tick()
    env.flush()
    drafts = [t for c, t, _ in env.tg.sent if "Правильно ли я понял" in t]
    assert len(drafts) == 2
    assert "добавить фильтр" in [c["prompt"] for c in env.llm.calls if "структурное описание" in c["prompt"]][-1]
    env.llm.on("filter", "Описание задачи отправлено автору", {"intent": "confirm", "edit": ""})
    env.say(PARTNER_CHAT, "да", user=AUTHOR)
    env.pipe.tick()
    assert env.trello.creates == 1
    card = next(iter(env.trello.cards.values()))
    assert card["idList"] == "L_TASKS" and card["label"] == ""  # без метки «Клиент»
    assert "WMS-AGENT-ID: task:1" in card["desc"].splitlines() and "Отчёт по остаткам" in card["desc"]
    env.flush()
    notes = [t for t in env.tg.to(OWNER_CHAT) if t.startswith("Задача внесена в Trello")]
    assert len(notes) == 1 and "https://trello.test/" in notes[0]
    assert "макет" not in notes[0]  # задача про бэк: вопроса о макете нет


def test_silence_creates_no_card_and_no_repeat_messages(env: Any) -> None:
    script_partner(env)
    ask_task(env)
    for _ in range(5):
        env.clock.advance(3600)
        env.pipe.tick()
    env.flush()
    assert env.trello.creates == 0 and len(env.tg.to(PARTNER_CHAT)) == 1


def test_ui_task_asks_owner_about_mockup(env: Any) -> None:
    script_partner(env, is_ui=True)
    ask_task(env)
    env.say(PARTNER_CHAT, "да", user=AUTHOR)
    env.pipe.tick()
    env.flush()
    assert any("Нужен ли макет?" in t for t in env.tg.to(OWNER_CHAT))
    assert env.store.ticket(1)["stage"] == "await_mockup"
    assert "card_id" in env.store.data(1) and "approved_description" in env.store.data(1)


def test_lost_trello_response_still_exactly_one_card(env: Any) -> None:
    script_partner(env)
    ask_task(env)
    env.trello.lose_response_once = True  # карточка создана, ответ потерян
    env.say(PARTNER_CHAT, "да", user=AUTHOR)
    env.pipe.tick()
    assert env.trello.creates == 1 and env.store.ticket(1)["stage"] == "done"
    # перезапуск и повторная обработка той же стадии
    env.store.set_stage(1, "task_create")
    env.pipe.process_ticket(1)
    assert env.trello.creates == 1


def test_unknown_outcome_never_recreates_and_owner_is_told_once(env: Any) -> None:
    script_partner(env)
    ask_task(env)
    env.trello.lose_response_once = True
    env.trello.hide_after_lose = True  # прочитать доску не удаётся: исход так и не выяснен
    env.say(PARTNER_CHAT, "да", user=AUTHOR)
    env.pipe.tick()
    assert env.trello.creates == 1 and env.store.ticket(1)["stage"] == "failed"
    env.store.set_stage(1, "task_create")
    env.pipe.process_ticket(1)
    env.pipe.process_ticket(1)
    env.flush()
    assert env.trello.creates == 1
    assert len([t for t in env.tg.to(OWNER_CHAT) if "не удалось подтвердить" in t]) == 1


def test_ensure_card_rejection_is_known_and_retriable(env: Any) -> None:
    env.trello.reject = True
    res = ensure_card(env.store, env.trello, key="k1", ticket_id=None, list_id="L", name="n", body="b")
    assert res.status == "rejected" and env.store.card("k1") is None
    env.trello.reject = False
    assert ensure_card(env.store, env.trello, key="k1", ticket_id=None, list_id="L", name="n",
                       body="b").status == "linked"


def test_restart_does_not_repeat_card_or_messages(env: Any) -> None:
    script_partner(env)
    ask_task(env)
    env.say(PARTNER_CHAT, "да", user=AUTHOR)
    env.pipe.tick()
    env.flush()
    sent = len(env.tg.sent)
    pipe2 = Pipeline(env.cfg, env.store, FakeTelegram(), FakeLlm(), env.trello, FakeWms(),
                     FakeTranscriber(), pool=InlinePool(), clock=env.clock)  # type: ignore[arg-type]
    pipe2.tick()
    env.flush()
    assert env.trello.creates == 1 and len(env.tg.sent) == sent
