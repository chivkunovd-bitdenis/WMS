"""WMS-661: instruction order and real tool effects, not real LLM cognition.

Semantic reuse/new is scripted; the fake obeys the explicit installed draft-first
instruction if present. No production Store, network, paid provider or live DB.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from support_agent import agent_tools
from support_agent.agent_coordinator import AgentCoordinator
from support_agent.agent_tools import AgentTools
from support_agent.config import config_from_dict
from support_agent.llm import LlmResult
from support_agent.readonly_mcp import MAX_READ, TOOLS, Reader, call_tool

BACKLOG = "docs/KANONICHESKIY_BACKLOG.md"
DOCUMENT = "docs/requirements/WMS-9001.md"
SCAN_TITLE = "Показывать причину непризнанного скана при упаковке FBS"
SCAN_DESCRIPTION = "На экране упаковки FBS после нераспознанного сканирования оператор видит конкретную причину."
SCAN_REQUEST = "При сборке FBS штрихкод не принимается — надо сразу объяснять оператору, почему этот скан не распознан"
EXTRA = "Причина должна оставаться видимой после следующего скана."
CREATE = r"(?:task_record|созда\w*|создай|зарегистр\w*|регистрац\w*|завед\w*|заведи)"
SEARCH = r"(?:поиск\w*|поищи|ищи|найди|найти|проверь|проверить|проверяй)"
CREATE_FIRST = re.compile(
    rf"(?:сначала|первым делом|вначале|первым шагом|начни с)\s+"
    rf"(?:(?:вызови|вызвать|создай|создать|заведи|зарегистрируй)\s+)?"
    rf"(?:task_record|черновик|новую задачу)|"
    rf"(?:создай|заведи|вызови)\s+(?:черновик|task_record)[^.;]*"
    rf"(?:а после|затем|потом)[^.;]*{SEARCH}", re.I,
)


def normalize_instruction(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[`*#]", "", text)).strip().lower()


def assert_instruction_contract(system: str) -> None:
    """Validate an explicit normative relation, not model cognition or keywords.

    Bounded document check accepts before/after and first-then formulations.
    Candidate meaning is still the fixture's verdict. This is never a product
    runtime gate: only TESTWRITER's inspection of the loaded document.
    """
    paragraphs = [normalize_instruction(p) for p in re.split(r"\n\s*\n", system) if p.strip()]
    normative = []
    for paragraph in paragraphs:
        current_tasks = re.search(r"(?:текущ|существующ)\w*.{0,80}задач", paragraph)
        canonical_backlog = re.search(r"каноническ\w*.{0,60}бэклог", paragraph)
        # A mention that tools are available does not direct search before creation.
        before = re.search(
            rf"(?:до|перед)\s+[^.;]{{0,180}}{CREATE}[^.;]{{0,240}}"
            rf"(?:обязатель\w*|выполни|выполнить|проведи|проверь|ищи|найди)[^.;]{{0,120}}{SEARCH}", paragraph)
        first_then = re.search(
            rf"сначала[^.;]{{0,220}}{SEARCH}[^;]{{0,700}}(?:затем|после этого)[^.;]{{0,180}}{CREATE}", paragraph)
        only_after = re.search(
            rf"{CREATE}[^.;]{{0,160}}(?:только|лишь) после[^.;]{{0,240}}{SEARCH}", paragraph)
        optional = re.search(r"необязател|не обязател|по желанию|можно не (?:искать|проверять)", paragraph)
        if current_tasks and canonical_backlog and (before or first_then or only_after) and not optional:
            normative.append(paragraph)
    assert normative, "loaded instructions lack mandatory current-task AND canonical-backlog search BEFORE creation"
    assert any(re.search(r"(?:включая|в том числе|также|и для|относится|даже)[^.]*чернов", p)
               and "task_record" in p and "confirm_author=false" in p for p in normative), (
        "mandatory precreation search must explicitly include unconfirmed task_record drafts")
    for paragraph in paragraphs:
        # An affirmative create-first directive contradicts the positive contract.
        first = CREATE_FIRST.search(paragraph)
        if first:
            prior = paragraph[:first.start()]
            assert re.search(r"после[^.;]*поиск", prior), "loaded instructions still direct draft creation first"
    reuse = any(re.search(r"если[^.;]*(?:найден|установлен|существует|есть)[^.;]*(?:дубл|совпад|соответств|задач)", p)
                and re.search(r"(?:переиспольз|используй существующ|свяж|обнови существующ|ticket_id)", p)
                for p in paragraphs)
    new = any(re.search(r"если[^.;]*(?:не найден|не установ|нет соответств|нет совпад|нет дубл)[^.;]*", p)
              and re.search(r"(?:создай|создать|зарегистр|заведи|новая задача разрешена)", p)
              for p in paragraphs)
    assert reuse, "loaded instructions must reuse an established canonical match"
    assert new, "loaded instructions must allow new registration only after search found no match"


COMPLIANT_INSTRUCTION = """
Перед регистрацией любой новой задачи обязательно выполни поиск по текущим задачам
и каноническому бэклогу по смыслу, затронутому процессу и объекту. Прочитай содержание
подходящих кандидатов. Это правило относится также к черновику task_record(confirm_author=false).

Если найден соответствующий канонический дубль, свяжи новый источник с существующей задачей,
переиспользуй её ticket_id, требования и карточку, обнови существенные сведения без второго комплекта.

Если не найден соответствующий запрос после поиска и чтения кандидатов, создай новую самостоятельную
задачу обычным путём; сохраняй существующие правила подтверждения автора и согласования владельца.
"""
PARAPHRASED_COMPLIANT_INSTRUCTION = """
Сначала обязательно проведи поиск по текущим задачам и каноническому бэклогу по смыслу,
процессу и объекту, прочитай описания кандидатов, затем вызывай task_record для регистрации.
Порядок действует даже для черновика task_record(confirm_author=false).

Если установлен соответствующий дубль, переиспользуй ticket_id и свяжи сообщение с существующей
канонической задачей без создания второго документа или карточки.

Если не установлено соответствие после поиска и чтения, зарегистрируй новую самостоятельную задачу
с обычным подтверждением автора, без общего запрета новых тем.
"""


class MemoryStore:
    """SQL-compatible synthetic store; SQLite exists exclusively in RAM."""

    def __init__(self, journal: list[tuple[str, Any]]) -> None:
        self.journal = journal
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE messages(id INTEGER PRIMARY KEY, chat_id INTEGER, source TEXT, msg_id TEXT,
                role TEXT, author_id TEXT, author_name TEXT, ts REAL, kind TEXT, text TEXT,
                reply_to TEXT, ticket_id INTEGER, revision INTEGER);
            CREATE TABLE tickets(id INTEGER PRIMARY KEY, chat_id INTEGER, kind TEXT, stage TEXT,
                author_id TEXT, data TEXT, source TEXT, seller TEXT, category TEXT);
            CREATE TABLE outbox(id INTEGER PRIMARY KEY, key TEXT, chat_id INTEGER, reply_to TEXT,
                text TEXT, status TEXT, tg_message_id TEXT, ticket_id INTEGER, purpose TEXT,
                created_at REAL, sent_at REAL);
        """)
        self.kv: dict[str, Any] = {}

    def row(self, sql: str, args: tuple[Any, ...] = ()) -> Any:
        return self.db.execute(sql, args).fetchone()

    def rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[Any]:
        return self.db.execute(sql, args).fetchall()

    def transaction(self) -> Any:
        return nullcontext()

    def kv_get(self, key: str, default: Any = None) -> Any:
        return self.kv.get(key, default)

    def kv_set(self, key: str, value: Any) -> None:
        self.kv[key] = value

    def kv_once(self, key: str) -> bool:
        if key in self.kv:
            return False
        self.kv[key] = True
        return True

    def ticket(self, tid: int) -> Any:
        return self.row("SELECT * FROM tickets WHERE id=?", (tid,))

    def data(self, tid: int) -> dict[str, Any]:
        return json.loads(self.ticket(tid)["data"])

    def open_tickets(self) -> list[Any]:
        return self.rows("SELECT * FROM tickets WHERE stage NOT IN ('done','closed','rejected','failed')")

    def patch_data(self, tid: int, **patch: Any) -> dict[str, Any]:
        data = {**self.data(tid), **patch}
        self.db.execute("UPDATE tickets SET data=? WHERE id=?", (json.dumps(data), tid))
        return data

    def set_stage(self, tid: int, stage: str, **patch: Any) -> None:
        self.db.execute("UPDATE tickets SET stage=? WHERE id=?", (stage, tid))
        if patch:
            self.patch_data(tid, **patch)

    def add_ticket(self, **fields: Any) -> int:
        self.journal.append(("create_ticket", dict(fields)))
        data = json.dumps(fields.pop("data", {}))
        cols = list(fields)
        cursor = self.db.execute(
            f"INSERT INTO tickets ({','.join(cols)},data) VALUES ({','.join('?' for _ in cols)},?)",
            (*fields.values(), data),
        )
        return int(cursor.lastrowid)

    def seed_ticket(self, tid: int, title: str, description: str, canonical: bool = True) -> None:
        agent = {"title": title, "description": description, "source_message_ids": [101],
                 "anchor": 101, "topic_key": "old-scan-reason", "version": "old-version",
                 "owner_approval": {"version": "old-version"}}
        data: dict[str, Any] = {"agent": agent}
        if canonical:
            agent.update(wms_number=9001, document_path=DOCUMENT, document_version="old-version",
                         document_sha="fake-old-sha", document_branch="fake-existing-branch")
            data.update(card_id="fake-card-31", card_url="https://trello.test/fake-card-31")
        self.db.execute("INSERT INTO tickets VALUES (?,900,'agent_task','agent_discussion','42',?,'telegram','client','task')",
                        (tid, json.dumps(data)))

    def queue_message(self, **fields: Any) -> bool:
        self.journal.append(("queue_message", fields))
        return True


class ScriptedSemanticLlm:
    """Supplies semantic verdict, but cannot conceal installed draft-first order."""

    def __init__(self, env: Any, *, reuse: bool, request: str) -> None:
        self.env, self.reuse, self.request = env, reuse, request
        self.calls: list[dict[str, Any]] = []
        self.result: dict[str, Any] = {}

    def agent_turn(self, prompt: str, **kwargs: Any) -> LlmResult:
        self.calls.append(kwargs)
        env = self.env
        assert kwargs["include_project_tools"] is True, "project reader unavailable in actual topic turn"
        handler = kwargs["tool_handler"]

        def dispatch(name: str, args: dict[str, Any]) -> Any:
            env.journal.append((name, dict(args)))
            return handler(name, args)

        def project(name: str, args: dict[str, Any]) -> str:
            assert name in {tool["name"] for tool in TOOLS}
            env.journal.append((name, dict(args)))
            text, failed = call_tool(env.reader, name, args)
            assert not failed, text
            return text

        new_args = {"chat_id": 900, "source_message_ids": [106], "title": "Новая формулировка",
                    "description": self.request, "topic_key": "new-distinct-source-topic",
                    "is_frontend": False, "confirm_author": False}
        # A compliant trace requires an affirmative ordering contract. The only
        # exception is a deliberately incorrect trace for a known create-first
        # directive, retained to reproduce the installed defect's effects.
        draft = None
        try:
            assert_instruction_contract(kwargs["system"])
        except AssertionError:
            if not CREATE_FIRST.search(normalize_instruction(kwargs["system"])):
                raise
            draft = dispatch("task_record", dict(new_args))
        current = dispatch("read_context", {"chat_id": 900})
        assert isinstance(current.get("tasks"), list)
        project("search", {"path": BACKLOG, "pattern": "скан|упаков|постав|9001"})
        chunks, offset = [], 0
        while True:
            chunk = project("read_file", {"path": BACKLOG, "offset": offset, "max_bytes": MAX_READ})
            chunks.append(chunk)
            if "файл продолжается" not in chunk:
                break
            offset += MAX_READ
        assert "WMS-9001" in "".join(chunks), "backlog candidate was never read"
        description = project("read_file", {"path": DOCUMENT})
        selected = dispatch("read_context", {"chat_id": 900, "ticket_id": 31})
        payload = json.dumps(selected, ensure_ascii=False)
        assert env.candidate_title in payload, "read_context(ticket_id=31) omitted selected candidate"
        assert env.candidate_description in payload, "candidate content was not exposed"
        assert env.candidate_description in description
        if self.reuse:
            self.result = dispatch("task_record", {
                **new_args, "ticket_id": 31, "source_message_ids": [101, 106],
                "title": env.candidate_title, "description": env.candidate_description + " " + EXTRA,
            })
        else:
            self.result = draft or dispatch("task_record", new_args)
            self.result = dispatch("task_record", {**new_args, "ticket_id": self.result["ticket_id"],
                                                   "confirm_author": True})
        return LlmResult(json.dumps({"summary": "synthetic decision", "task_ids": ["WMS-9001"]}),
                         "fake", "fixture", "fixture-session")


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: Any) -> Any:
    environments: list[Any] = []

    def make(*, reuse: bool = True, hidden: bool = False, large: bool = False,
             shared_object: bool = False) -> Any:
        journal: list[tuple[str, Any]] = []
        store = MemoryStore(journal)
        cfg = config_from_dict({"repo": str(tmp_path), "state_dir": str(tmp_path / "unused-state"),
                                "telegram": {"owner_user_id": 42, "owner_chat_id": 900},
                                "agent": {"enabled": True}})
        title = "Печатать QR поставки WB" if shared_object else SCAN_TITLE
        description = "Печать QR поставки WB из документа поставки." if shared_object else SCAN_DESCRIPTION
        store.seed_ticket(31, title, description)
        if hidden:
            for tid in range(32, 72):
                store.seed_ticket(tid, f"Независимая задача {tid}", f"Другой процесс {tid}", False)
        request = SCAN_REQUEST + ". " + EXTRA if reuse else "Добавить выгрузку отчёта расчётов за выбранный месяц"
        if shared_object:
            request = "Показывать срок сдачи поставки WB в документе поставки"
        source = {"id": 106, "chat_id": 900, "source": "telegram", "msg_id": "new-message-106",
                  "role": "owner", "author_id": "42", "author_name": "Synthetic Owner",
                  "ts": 200, "kind": "text", "text": request, "reply_to": None,
                  "ticket_id": None, "revision": 0}
        for sid in (101, 106):
            values = {**source, "id": sid, "msg_id": str(sid)}
            store.db.execute(f"INSERT INTO messages ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                             tuple(values.values()))
        (tmp_path / "docs/requirements").mkdir(parents=True, exist_ok=True)
        padding = "Старая независимая запись без нужного объекта.\n" * 4000 if large else ""
        (tmp_path / BACKLOG).write_text(padding + f"\n## WMS-9001 · {title}\nTicket: 31\nТребования: {DOCUMENT}\n", encoding="utf-8")
        (tmp_path / DOCUMENT).write_text(f"# {title}\n{description}\n", encoding="utf-8")
        env = SimpleNamespace(store=store, cfg=cfg, journal=journal, reader=Reader(str(tmp_path)),
                              candidate_title=title, candidate_description=description,
                              documents={31: DOCUMENT}, cards={31: "fake-card-31"})

        def persist(pipe: Any, tid: int) -> dict[str, Any]:
            if tid not in env.documents:
                journal.append(("create_document", tid))
                env.documents[tid] = f"docs/requirements/WMS-{9000 + tid}.md"
            data = store.data(tid)["agent"]
            number = data.get("wms_number", 9000 + tid)
            store.patch_data(tid, agent={**data, "wms_number": number, "document_version": data["version"],
                                         "document_sha": "fixture-sha"})
            return {"number": number, "branch": "fixture-branch", "sha": "fixture-sha"}

        def sync(self: Any, args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
            tid = args["ticket_id"]
            if tid not in env.cards:
                journal.append(("create_card", tid))
                env.cards[tid] = f"fake-card-{tid}"
            return {"status": "linked", "card_id": env.cards[tid], "url": "https://trello.test/fixture"}

        monkeypatch.setattr(agent_tools, "persist_task", persist)
        monkeypatch.setattr(AgentTools, "_tool_trello_sync", sync)
        llm = ScriptedSemanticLlm(env, reuse=reuse, request=request)
        pipe = SimpleNamespace(cfg=cfg, store=store, llm=llm, clock=lambda: 200,
                               _owner_snapshot=lambda: [], _seller_for_chat=lambda *_: "client",
                               say_owner=lambda *args: None)
        tools = AgentTools(pipe)
        agent = AgentCoordinator(pipe, tools)
        tools.semantic_verifier = SimpleNamespace(check=lambda *_: {"authorized": True, "reason": "fixture"})
        topic = {"id": "topic-106", "chat_id": 900, "generation": 0, "summary": ""}
        store.kv_set("agent_topic:topic-106", topic)
        env.agent, env.llm, env.source = agent, llm, source
        env.run = lambda: agent.run_topic_turn(topic, {"id": 106, "kind": "input"}, source)
        environments.append(env)
        return env

    yield make
    for env in environments:
        env.agent.jobs.shutdown(wait=True)
        env.agent.dispatcher.router.shutdown(wait=True)
        env.agent.dispatcher.workers.shutdown(wait=True)
        env.store.db.close()


def assert_search_before_record(env: Any) -> None:
    journal = env.journal
    record = next(i for i, (name, _) in enumerate(journal) if name == "task_record")
    context = [i for i, (name, _) in enumerate(journal) if name == "read_context"]
    backlog = [i for i, (name, args) in enumerate(journal) if name == "read_file" and args["path"] == BACKLOG]
    docs = [i for i, (name, args) in enumerate(journal) if name == "read_file" and args["path"] == DOCUMENT]
    searches = [i for i, (name, _) in enumerate(journal) if name == "search"]
    assert context and searches and backlog and docs
    assert max(context + searches + backlog + docs) < record, (
        "current-task/backlog search and candidate reads must precede even unconfirmed task_record", journal)


def assert_reused(env: Any) -> None:
    assert_search_before_record(env)
    assert not [entry for entry in env.journal if entry[0].startswith("create_")], env.journal
    assert env.llm.result["ticket_id"] == 31
    agent = env.store.data(31)["agent"]
    assert agent["wms_number"] == 9001 and agent["document_path"] == DOCUMENT
    assert env.store.data(31)["card_id"] == "fake-card-31"
    assert {101, 106} <= set(agent["source_message_ids"])
    assert EXTRA in agent["description"]
    assert "owner_approval" not in agent, "new version must not inherit old approval"
    assert env.documents == {31: DOCUMENT} and env.cards == {31: "fake-card-31"}


def test_c1_synonymous_new_source_reuses_canonical_task_before_draft(scenario: Any) -> None:
    env = scenario()
    env.run()
    assert_reused(env)


def test_c2_backlog_only_candidate_is_read_outside_recent_tasks(scenario: Any) -> None:
    env = scenario(hidden=True)
    assert 31 not in [int(t["id"]) for t in env.store.open_tickets()[-30:]]
    env.run()
    assert_reused(env)


def test_c3_independent_new_request_creates_one_confirmed_bundle_after_search(scenario: Any) -> None:
    env = scenario(reuse=False)
    env.run()
    assert_search_before_record(env)
    assert [name for name, _ in env.journal if name.startswith("create_")] == [
        "create_ticket", "create_document", "create_card"]
    tid = env.llm.result["ticket_id"]
    assert tid != 31 and env.llm.result["author_confirmed"] is True
    assert env.documents[tid] != DOCUMENT and env.cards[tid] != "fake-card-31"
    assert len(env.store.open_tickets()) == 2
    assert env.store.data(31)["agent"]["description"] == SCAN_DESCRIPTION


def test_c4_shared_supply_object_different_action_can_be_new(scenario: Any) -> None:
    env = scenario(reuse=False, shared_object=True)
    env.run()
    assert_search_before_record(env)
    tid = env.llm.result["ticket_id"]
    assert tid != 31 and "срок сдачи" in env.store.data(tid)["agent"]["description"]
    assert env.store.data(31)["agent"]["description"] == env.candidate_description
    assert len(env.documents) == len(env.cards) == 2


def test_c5_large_backlog_candidate_after_first_window_is_reused(scenario: Any) -> None:
    env = scenario(large=True, hidden=True)
    backlog = env.reader.root / BACKLOG
    assert backlog.stat().st_size > 250_000
    assert "WMS-9001" not in env.reader.read_file(BACKLOG)
    env.run()
    assert_reused(env)
    offsets = [args.get("offset", 0) for name, args in env.journal
               if name == "read_file" and args["path"] == BACKLOG]
    assert len(offsets) > 1 and max(offsets) > MAX_READ


def test_c6_actual_topic_instructions_require_search_before_even_draft(scenario: Any) -> None:
    env = scenario()
    env.run()
    call = env.llm.calls[0]
    system = call["system"]
    assert_instruction_contract(system)
    assert "read_context" in {tool["name"] for tool in call["tools"]}
    assert call["include_project_tools"] is True
    assert {"search", "read_file"} <= {tool["name"] for tool in TOOLS}
    assert len(env.llm.calls) == 1, "topic must not call an extra semantic provider"


@pytest.mark.parametrize("options", [{}, {"reuse": False}, {"reuse": False, "shared_object": True},
                                     {"large": True, "hidden": True}, {"hidden": True}])
def test_contract_positive_control_accepts_compliant_fixture(scenario: Any, monkeypatch: Any,
                                                             options: dict[str, Any]) -> None:
    """Validate test harness using explicit synthetic fixes, not product edits."""
    env = scenario(**options)
    env.agent.system = COMPLIANT_INSTRUCTION
    assert_instruction_contract(env.agent.system)
    original = env.agent.tools._tool_read_context

    def expose_selected(args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
        result = original(args, event, owner)
        if args.get("ticket_id") == 31:
            ticket = dict(env.store.ticket(31))
            ticket["data"] = env.store.data(31)
            result["selected_task"] = ticket
        return result

    monkeypatch.setattr(env.agent.tools, "_tool_read_context", expose_selected)
    env.run()
    assert_search_before_record(env)
    if options.get("reuse", True):
        assert_reused(env)
    else:
        assert env.llm.result["ticket_id"] != 31
        assert [name for name, _ in env.journal if name.startswith("create_")] == [
            "create_ticket", "create_document", "create_card"]


def test_c5_negative_control_incomplete_large_source_is_not_absence(scenario: Any, monkeypatch: Any) -> None:
    env = scenario(large=True)
    env.agent.system = COMPLIANT_INSTRUCTION
    original = env.reader.read_file

    def incomplete(path: str, offset: int = 0, max_bytes: int = MAX_READ) -> str:
        if path == BACKLOG:
            # Simulate a tool claiming completion after only its first window.
            return original(path, offset=0, max_bytes=MAX_READ).split("\n… файл продолжается")[0]
        return original(path, offset, max_bytes)

    monkeypatch.setattr(env.reader, "read_file", incomplete)
    with pytest.raises(AssertionError, match="backlog candidate was never read"):
        env.run()


INSTRUCTION_MUTATIONS = {
    "word_mentions_only": "Поиск по текущим задачам и каноническому бэклогу доступен. "
                          "Смысл, процесс, объект и черновик известны. Для новой темы создай новую задачу.",
    "duty_removed": "Используй task_record(confirm_author=false) для нового черновика. Поиск доступен.",
    "search_after_creation": "Создай черновик task_record(confirm_author=false), а после этого выполни поиск "
                             "по текущим задачам и каноническому бэклогу.",
    "equivalent_draft_first": "Первым делом создай черновик task_record(confirm_author=false). "
                              "Поиск по текущим задачам и каноническому бэклогу доступен.",
    "optional_search": "Перед регистрацией новой задачи по желанию выполни поиск по текущим задачам "
                       "и каноническому бэклогу. Это относится также к черновику task_record(confirm_author=false).",
}
CONTRACT_CASES = [test_c1_synonymous_new_source_reuses_canonical_task_before_draft,
                  test_c2_backlog_only_candidate_is_read_outside_recent_tasks,
                  test_c3_independent_new_request_creates_one_confirmed_bundle_after_search,
                  test_c4_shared_supply_object_different_action_can_be_new,
                  test_c5_large_backlog_candidate_after_first_window_is_reused,
                  test_c6_actual_topic_instructions_require_search_before_even_draft]


@pytest.mark.parametrize("case", CONTRACT_CASES, ids=lambda case: case.__name__.split("_")[1])
@pytest.mark.parametrize("mutation", [*INSTRUCTION_MUTATIONS, "installed_paraphrase"])
def test_c6_every_contract_case_rejects_missing_or_reversed_search_duty(
    scenario: Any, monkeypatch: Any, case: Any, mutation: str,
) -> None:
    """Each C1–C6 must fail, even with candidate-tool defect synthetically fixed."""
    def altered_scenario(**options: Any) -> Any:
        env = scenario(**options)
        if mutation == "installed_paraphrase":
            env.agent.system = env.agent.system.replace("сначала вызови", "первым делом вызови")
        else:
            remainder = COMPLIANT_INSTRUCTION.split("\n\n", 1)[1]
            env.agent.system = INSTRUCTION_MUTATIONS[mutation] + "\n\n" + remainder
        original = env.agent.tools._tool_read_context

        def expose_selected(args: dict[str, Any], event: Any, owner: bool) -> dict[str, Any]:
            result = original(args, event, owner)
            if args.get("ticket_id") == 31:
                ticket = dict(env.store.ticket(31))
                ticket["data"] = env.store.data(31)
                result["selected_task"] = ticket
            return result

        monkeypatch.setattr(env.agent.tools, "_tool_read_context", expose_selected)
        return env

    with pytest.raises(AssertionError, match="mandatory|must precede|creation first"):
        case(altered_scenario)


@pytest.mark.parametrize("instruction", [
    COMPLIANT_INSTRUCTION,
    COMPLIANT_INSTRUCTION.replace("Перед регистрацией", "До регистрации"),
    PARAPHRASED_COMPLIANT_INSTRUCTION,
    COMPLIANT_INSTRUCTION.replace(
        "Перед регистрацией любой новой задачи обязательно выполни поиск по текущим задачам\nи каноническому бэклогу",
        "Регистрировать новую задачу через task_record разрешено только после поиска по текущим задачам\nи каноническому бэклогу",
    ),
])
def test_c6_positive_paraphrase_uses_same_loaded_instruction_validator(scenario: Any, instruction: str) -> None:
    def paraphrased(**options: Any) -> Any:
        env = scenario(**options)
        env.agent.system = instruction
        return env

    # Invoke the exact C6 case, not a weaker validation unique to the control.
    test_c6_actual_topic_instructions_require_search_before_even_draft(paraphrased)


@pytest.mark.parametrize("instruction, expected", [
    (COMPLIANT_INSTRUCTION + "\n\nПервым делом создай черновик task_record(confirm_author=false), а после выполни поиск.",
     "creation first"),
    (COMPLIANT_INSTRUCTION.replace("Это правило относится также к черновику task_record(confirm_author=false).", ""),
     "explicitly include"),
    (COMPLIANT_INSTRUCTION.split("\n\nЕсли найден", 1)[0] + "\n\nЕсли не найден дубль после поиска, создай новую задачу.",
     "must reuse"),
    (COMPLIANT_INSTRUCTION.split("\n\nЕсли не найден", 1)[0], "allow new registration"),
])
def test_c6_normative_contract_rejects_conflict_or_missing_branch(instruction: str, expected: str) -> None:
    with pytest.raises(AssertionError, match=expected):
        assert_instruction_contract(instruction)
