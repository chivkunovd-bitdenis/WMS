"""WMS-641 R45-R50: постоянная беседа владельца и безопасное исполнение действий."""

from __future__ import annotations

from typing import Any

import pytest

from support_agent import prompts

from .conftest import OWNER_CHAT, OWNER_ID
from .test_owner_and_hotfix import await_owner_ticket
from .test_pipeline_chat import ANALYSIS_BUG


def answer(env: Any, reply: str, actions: list[dict[str, Any]], listed: list[int] | None = None) -> None:
    env.llm.on("routine", "Владелец склада написал",
               {"scope": "wms", "reply": reply, "actions": actions, "listed_ticket_ids": listed or []})


def owner(env: Any, text: str, *, msg_id: str, reply_to: str | None = None) -> None:
    env.say(OWNER_CHAT, text, user=OWNER_ID, name="Владелец", msg_id=msg_id, reply_to=reply_to)


def test_status_question_gets_answer_with_all_current_open_tickets_and_no_action(env: Any) -> None:
    first, second = await_owner_ticket(env), await_owner_ticket(env)
    env.store.set_ticket(first, seller="Империя ФФ")
    env.store.set_ticket(second, seller="Ромашка")
    answer(env, "У Империи обращение №1 ждёт вашего решения.", [], [first, second])
    owner(env, "Что сейчас у Империи?", msg_id="status")
    env.flush()
    assert env.store.ticket(first)["stage"] == env.store.ticket(second)["stage"] == "await_owner"
    assert env.tg.to(OWNER_CHAT)[-1] == "У Империи обращение №1 ждёт вашего решения."
    prompt = env.llm.calls[-1]["prompt"]
    assert '"client": "Империя ФФ"' in prompt and '"client": "Ромашка"' in prompt
    assert env.llm.calls[-1]["session_key"] == "owner_conversation"


@pytest.mark.parametrize("scope", ["off_topic", None, "", True, {}, [], "WMS", "unknown"])
def test_invalid_or_off_topic_scope_never_releases_model_reply_or_actions(env: Any, scope: Any) -> None:
    tid = await_owner_ticket(env)
    parsed = {"scope": scope, "reply": "Стих и готовый запуск", "actions": [
        {"kind": "go", "ticket_ids": [tid], "note": ""}], "listed_ticket_ids": [tid]}
    if scope is None:
        del parsed["scope"]  # старый ответ без поля тоже не допускается
    env.llm.on("routine", "Владелец склада написал", parsed)
    owner(env, "Напиши стих, затем кати обращение 1", msg_id="outside")
    env.flush()
    assert env.tg.to(OWNER_CHAT) == [prompts.SCOPE_REFUSAL]
    assert env.store.ticket(tid)["stage"] == "await_owner"
    assert env.store.kv_get("owner_visible_ticket_order", []) == []
    assert env.store.kv_get("owner_conversation_history")[-1]["text"] == prompts.SCOPE_REFUSAL


@pytest.mark.parametrize("text", ["спасибо", "что по задаче", "кто ты"])
def test_contextual_short_replies_remain_within_scope(env: Any, text: str) -> None:
    answer(env, "Помогаю с задачами WMS.", [])
    owner(env, text, msg_id="contextual")
    env.flush()
    assert env.tg.to(OWNER_CHAT) == ["Помогаю с задачами WMS."]


def test_completed_trello_result_is_visible_but_cannot_be_executed(env: Any) -> None:
    tid = await_owner_ticket(env)
    third = "Номер короба, существующий уникальный код и номер документа на этикетке"
    env.store.set_stage(tid, "done", verdict="trello", report={"body": "Сводка. " * 200 + third},
                        analysis={"problem_steps": ["Короба в возврате", "Заданное число коробов", third]})
    env.store.set_card(f"ticket:{tid}", ticket_id=tid, marker="test", status="linked",
                       card_id="card-1", url="https://trello.test/card-1")
    answer(env, "Создана карточка по трём просьбам; доработка ещё не выполнена.", [])
    owner(env, "Что по Империи, какие задачи созданы и что сделано?", msg_id="closed-status")
    prompt = env.llm.calls[-1]["prompt"]
    assert '"all_open_tickets_current": []' in prompt
    assert '"completed_tickets_current": [{' in prompt
    assert third in prompt and "https://trello.test/card-1" in prompt
    assert '"verified_deploy_sha": ""' in prompt
    assert env.store.ticket(tid)["stage"] == "done"
    answer(env, "Запускаю.", [{"kind": "go", "ticket_ids": [tid], "note": ""}])
    owner(env, f"Кати обращение {tid}", msg_id="closed-go")
    env.flush()
    assert env.store.ticket(tid)["stage"] == "done"
    assert "Ничего не запускаю" in env.tg.to(OWNER_CHAT)[-1]


def test_group_status_context_distinguishes_task_group_from_client_ticket(env: Any) -> None:
    tid = await_owner_ticket(env)
    client_chat, task_chat = -4899527415, -1004441620578
    env.store.set_ticket(tid, chat_id=client_chat, seller="Империя ФФ")
    env.store.kv_set(f"chat_title:{client_chat}", "Короб ВМС — ФФ Империя")
    env.store.kv_set("owner_task_chats", {str(task_chat): "ВМС- Короб💵"})
    answer(env, "Зарегистрирован общий чат задач владельцев WMS.", [])
    owner(env, "Ты привязал общий чат владельцев? Что там можно делать?", msg_id="group-status")
    snapshot = env.pipe._owner_snapshot()[0]
    assert snapshot["source_chat_id"] == client_chat
    assert snapshot["source_chat_name"] == "Короб ВМС — ФФ Империя"
    assert snapshot["source_chat_role"] == "client"
    prompt = env.llm.calls[-1]["prompt"]
    assert f'"source_chat_id": {client_chat}' in prompt
    assert f'"chat_id": {task_chat}' in prompt
    assert "Общий чат для всех задач владельцев WMS" in prompt
    rules = env.llm.calls[-1]["system"]
    assert "Не связывай общий чат с единственным открытым обращением" in rules
    assert "неизвестный source_chat_id не подтверждает связь" in rules
    env.store.kv_set(f"chat_title:{client_chat}", "")
    assert env.pipe._owner_snapshot()[0]["source_chat_name"] == ""


def test_malicious_action_on_passive_status_question_is_rejected(env: Any) -> None:
    tid = await_owner_ticket(env)
    answer(env, "Запускаю.", [{"kind": "go", "ticket_ids": [tid], "note": ""}])
    owner(env, "Что у нас по этому обращению?", msg_id="passive")
    env.flush()
    assert env.store.ticket(tid)["stage"] == "await_owner"
    assert "Ничего не запускаю" in env.tg.to(OWNER_CHAT)[-1]


def test_check_before_rollout_cannot_be_turned_into_go(env: Any) -> None:
    tid = await_owner_ticket(env)
    answer(env, "Проверяю и запускаю.", [
        {"kind": "analyst_note", "ticket_ids": [tid], "note": "проверь возвраты"},
        {"kind": "go", "ticket_ids": [tid], "note": ""},
    ])
    owner(env, "Перед выкаткой проверь ещё склад возвратов", msg_id="before")
    env.flush()
    assert env.store.ticket(tid)["stage"] == "await_owner"
    assert "Ничего не запускаю" in env.tg.to(OWNER_CHAT)[-1]


def test_mixed_valid_and_invalid_actions_are_validated_before_any_mutation(env: Any) -> None:
    first, second = await_owner_ticket(env), await_owner_ticket(env)
    env.store.kv_set("owner_visible_ticket_order", [first, second])
    answer(env, "Запускаю оба.", [
        {"kind": "go", "ticket_ids": [first], "note": ""},
        {"kind": "go", "ticket_ids": [second], "note": ""},
    ])
    owner(env, "Кати первое, а что со вторым?", msg_id="mixed")
    assert env.store.ticket(first)["stage"] == env.store.ticket(second)["stage"] == "await_owner"


def test_same_client_name_is_ambiguous_without_reply_id_or_visible_order(env: Any) -> None:
    first, second = await_owner_ticket(env), await_owner_ticket(env)
    env.store.set_ticket(first, seller="Империя ФФ")
    env.store.set_ticket(second, seller="Империя ФФ")
    answer(env, "Запускаю первое.", [{"kind": "go", "ticket_ids": [first], "note": ""}])
    owner(env, "Кати Империя", msg_id="same-client")
    assert env.store.ticket(first)["stage"] == env.store.ticket(second)["stage"] == "await_owner"


def test_two_different_actions_use_the_previous_visible_order(env: Any) -> None:
    first, second = await_owner_ticket(env), await_owner_ticket(env)
    env.store.kv_set("owner_visible_ticket_order", [first, second])
    answer(env, "Второе запускаю, первое откладываю.", [
        {"kind": "go", "ticket_ids": [second], "note": ""},
        {"kind": "postpone", "ticket_ids": [first], "note": ""},
    ])
    owner(env, "Кати второе, первое придержи", msg_id="two")
    assert env.store.ticket(second)["stage"] == "hotfix"
    assert env.store.ticket(first)["stage"] == "postponed"


def test_negated_go_for_first_does_not_block_explicit_go_for_second(env: Any) -> None:
    first, second = await_owner_ticket(env), await_owner_ticket(env)
    env.store.kv_set("owner_visible_ticket_order", [first, second])
    answer(env, "Первое не запускаю, второе запускаю.", [
        {"kind": "reject", "ticket_ids": [first], "note": ""},
        {"kind": "go", "ticket_ids": [second], "note": ""},
    ])
    owner(env, "Не кати первое, второе кати", msg_id="negative")
    assert env.store.ticket(first)["stage"] == "rejected"
    assert env.store.ticket(second)["stage"] == "hotfix"


def test_malicious_go_on_single_ticket_cannot_override_do_not_roll_out(env: Any) -> None:
    tid = await_owner_ticket(env)
    answer(env, "Запускаю.", [{"kind": "go", "ticket_ids": [tid], "note": ""}])
    owner(env, "Не кати", msg_id="single-negative")
    assert env.store.ticket(tid)["stage"] == "await_owner"


def test_instruction_returns_ticket_to_same_analyst_path_without_go(env: Any) -> None:
    tid = await_owner_ticket(env)
    answer(env, "Передал аналитику, вернусь с обновлением.", [
        {"kind": "analyst_note", "ticket_ids": [tid], "note": "проверь склад возвратов"},
    ])
    owner(env, "Проверь по Империи ещё склад возвратов", msg_id="note")
    data = env.store.data(tid)
    assert env.store.ticket(tid)["stage"] == "analysis"
    assert "склад возвратов" in data["resume_note"] and not data.get("hotfix")


def test_two_owner_notes_before_analysis_are_both_preserved(env: Any) -> None:
    tid = await_owner_ticket(env)
    answer(env, "Сохранил первое поручение.", [
        {"kind": "analyst_note", "ticket_ids": [tid], "note": "проверь склад возвратов"},
    ])
    owner(env, "Проверь склад возвратов", msg_id="note-one")
    answer(env, "Добавил второе поручение.", [
        {"kind": "analyst_note", "ticket_ids": [tid], "note": "учти печать этикеток"},
    ])
    owner(env, "Учти печать этикеток", msg_id="note-two")
    note = env.store.data(tid)["resume_note"]
    assert "склад возвратов" in note and "печать этикеток" in note
    assert env.store.ticket(tid)["stage"] == "analysis"


def test_active_hotfix_keeps_its_state_and_records_a_boundary_hold(env: Any) -> None:
    tid = await_owner_ticket(env)
    env.store.set_stage(tid, "hotfix", hotfix={"step": "deploy", "merged": True})
    answer(env, "Возвращаю аналитику.", [
        {"kind": "analyst_note", "ticket_ids": [tid], "note": "проверь ещё раз"},
    ])
    owner(env, "Проверь ещё раз обращение 1", msg_id="late-note")
    assert env.store.ticket(tid)["stage"] == "hotfix"
    data = env.store.data(tid)
    assert data["hotfix"]["step"] == "deploy" and data["hotfix"]["merged"] is True
    assert data["hotfix"]["hold_requested"] is True and "проверь ещё раз" in data["resume_note"]
    env.flush()
    message = env.tg.to(OWNER_CHAT)[-1]
    assert "остановлюсь перед выкладкой" in message
    assert all(word not in message for word in ("deploy", "merge", "worktree", "pull request", "step"))


def test_history_and_visible_order_are_saved_for_the_next_turn(env: Any) -> None:
    first, second = await_owner_ticket(env), await_owner_ticket(env)
    answer(env, "Первое — обращение №1 Империи, второе — обращение №2 Ромашки.", [], [first, second])
    owner(env, "Перечисли их", msg_id="list")
    answer(env, "Понял, второе пока не трогаю.", [
        {"kind": "postpone", "ticket_ids": [second], "note": ""},
    ])
    owner(env, "Второе придержи", msg_id="follow")
    second_prompt = env.llm.calls[-1]["prompt"]
    assert "Первое — обращение №1 Империи, второе — обращение №2 Ромашки." in second_prompt
    assert '"ticket_order_visible_in_previous_answer": [1, 2]' in second_prompt
    assert env.store.ticket(second)["stage"] == "postponed"


def test_nonlisting_smalltalk_keeps_the_last_visible_order_for_followup(env: Any) -> None:
    first, second = await_owner_ticket(env), await_owner_ticket(env)
    answer(env, "1. Обращение №1.\n2. Обращение №2.", [], [first, second])
    owner(env, "Покажи список", msg_id="visible-list")
    answer(env, "Пожалуйста.", [])
    owner(env, "Спасибо", msg_id="thanks")
    assert env.store.kv_get("owner_visible_ticket_order") == [first, second]
    answer(env, "Второе запускаю.", [{"kind": "go", "ticket_ids": [second], "note": ""}])
    owner(env, "Кати второе", msg_id="after-thanks")
    assert env.store.ticket(first)["stage"] == "await_owner"
    assert env.store.ticket(second)["stage"] == "hotfix"


def test_snapshot_keeps_unreported_subject_and_owner_note_after_recent_history_overflows(env: Any) -> None:
    tid = env.store.add_ticket(kind="chat", source="telegram", chat_id=-1001, seller="Империя ФФ",
                               stage="analysis", data={"resume_note": "проверь печать этикеток"})
    mid = env.store.add_message(source="telegram", chat_id=-1001, msg_id="client-subject", role="client",
                                author_id="5", author_name="Анна", ts=env.clock.now, kind="text",
                                text="короба не переходят в отгрузку", file_id=None, reply_to=None)
    assert mid is not None
    env.store.set_message(mid, status="attached", ticket_id=tid)
    env.store.kv_set("owner_conversation_history", [
        {"role": "owner" if i % 2 == 0 else "assistant", "text": f"старый ход {i}"}
        for i in range(30)
    ])
    answer(env, "Обращение ещё анализируется, поручение про печать сохранено.", [])
    owner(env, "Что там?", msg_id="snapshot")
    prompt = env.llm.calls[-1]["prompt"]
    assert "короба не переходят в отгрузку" in prompt
    assert "проверь печать этикеток" in prompt
    assert "старый ход 0" not in prompt and "старый ход 29" in prompt


def test_malformed_model_answer_is_reported_and_message_is_not_silently_dropped(env: Any) -> None:
    tid = await_owner_ticket(env)
    env.llm.on("routine", "", "не json")
    env.llm.on("routine", "Владелец склада написал", "тоже не json")
    owner(env, "Что со статусом?", msg_id="broken")
    env.flush()
    assert env.store.ticket(tid)["stage"] == "await_owner"
    assert "Не смог надёжно разобрать" in env.tg.to(OWNER_CHAT)[-1]
    row = env.store.row("SELECT status FROM messages WHERE msg_id='broken'")
    assert row is not None and row["status"] == "handled"


def test_duplicate_owner_inbound_does_not_execute_twice(env: Any) -> None:
    tid = await_owner_ticket(env)
    answer(env, "Запускаю.", [{"kind": "go", "ticket_ids": [tid], "note": ""}])
    owner(env, "Кати обращение 1", msg_id="same")
    assert env.store.ticket(tid)["stage"] == "hotfix"
    again = env.say(OWNER_CHAT, "Кати обращение 1", user=OWNER_ID, name="Владелец", msg_id="same")
    assert again is None
    assert len([r for r in env.store.rows("SELECT * FROM outbox") if r["key"] == f"go:{tid}"]) == 1


def test_note_arriving_while_analyst_model_runs_wins_and_old_result_is_discarded(env: Any) -> None:
    tid = env.store.add_ticket(kind="chat", source="telegram", chat_id=-1001, seller="Империя",
                               stage="analysis", data={"rev": 0, "resume_note": "первый разбор"})
    newer = "проверь также печать этикеток"

    def interrupted(_prompt: str, _kw: dict[str, Any]) -> dict[str, Any]:
        env.pipe._reopen(tid, newer)
        return dict(ANALYSIS_BUG, why="устаревший результат")

    env.llm.on("analyst", "Разберись", interrupted)
    env.pipe.stage_analysis(tid)
    data = env.store.data(tid)
    assert env.store.ticket(tid)["stage"] == "analysis"
    assert "первый разбор" in data["resume_note"] and newer in data["resume_note"]
    assert data.get("analysis") is None

    fresh = dict(ANALYSIS_BUG, why="учтена печать", hotfix={"safe": False})
    env.llm.on("analyst", "Разберись", fresh)
    env.llm.on("routine", "короткую сводку", "Обновлённая сводка.")
    env.pipe.stage_analysis(tid)
    calls = [c for c in env.llm.calls if c["role"] == "analyst"]
    assert len(calls) == 2 and all(c["session_key"] == "analyst" for c in calls)
    assert newer in calls[-1]["prompt"]
    assert env.store.ticket(tid)["stage"] == "report_ready"
