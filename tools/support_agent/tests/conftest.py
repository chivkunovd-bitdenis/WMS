"""Подделки Telegram, Trello, WMS, моделей и оболочки. Реальных вызовов в тестах нет."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from support_agent.config import Config, config_from_dict
from support_agent.llm import ExecResult, LlmResult
from support_agent.pipeline import InlinePool, Pipeline
from support_agent.store import Store
from support_agent.telegram import Inbound, TelegramError
from support_agent.trello import TrelloError

CLIENT_CHAT = -100111
PARTNER_CHAT = -100222
OWNER_CHAT = -100999
OWNER_ID = 42


def make_config(tmp_path: Any, **over: Any) -> Config:
    data: dict[str, Any] = {
        "state_dir": str(tmp_path / "state"),
        "repo": str(tmp_path / "repo"),
        "telegram": {
            "bot_token": "123456:SECRET-BOT-TOKEN",
            "owner_user_id": OWNER_ID,
            "owner_chat_id": OWNER_CHAT,
            "chats": {
                str(CLIENT_CHAT): {"role": "client", "seller": "ИП Тест"},
                str(PARTNER_CHAT): {"role": "partner"},
            },
        },
        "trello": {
            "api_key": "TRELLO-KEY-VALUE", "token": "TRELLO-TOKEN-VALUE", "board_id": "board",
            "client_list_id": "L_CLIENT", "partner_list_id": "L_TASKS",
            "in_progress_list_id": "L_PROGRESS", "completed_list_id": "L_DONE",
            "client_label_id": "LABEL_CLIENT",
        },
        "wms": {"base_url": "https://wms.test/api", "agent_key": "K" * 40, "poll_interval_sec": 60},
        "limits": {"quiet_sec": 120, "batch_wait_sec": 45, "urgency_wait_sec": 900,
                   "ask_client_urgency": True,
                   "data_wait_sec": 7200, "ci_timeout_sec": 600, "deploy_timeout_sec": 600},
        "hotfix": {"backend_bin": "/venv/bin", "deployed_sha_cmd": "echo sha",
                   "public_base_url": "https://wms.test"},
        "mockups": {"publish_cmd": "publish {dir} {name}", "base_url": "https://mock.test"},
    }
    data.update(over)
    return config_from_dict(data)


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, str | None]] = []
        self.documents: list[tuple[int, str, str, str | None]] = []
        self.updates: list[dict[str, Any]] = []
        self.files: dict[str, bytes] = {}
        self.fail: list[TelegramError] = []
        self.ids = itertools.count(1000)

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        batch = [u for u in self.updates if u["update_id"] >= offset]
        return batch

    def send_message(self, chat_id: int, text: str, reply_to: str | None = None) -> str:
        if self.fail:
            raise self.fail.pop(0)
        self.sent.append((chat_id, text, reply_to))
        return str(next(self.ids))

    def send_document(self, chat_id: int, path: str, caption: str = "", reply_to: str | None = None) -> str:
        if self.fail:
            raise self.fail.pop(0)
        self.documents.append((chat_id, path, caption, reply_to))
        return str(next(self.ids))

    def download_file(self, file_id: str) -> bytes:
        if file_id not in self.files:
            raise TelegramError("rejected", "no_file")
        return self.files[file_id]

    def to(self, chat_id: int) -> list[str]:
        return [t for c, t, _ in self.sent if c == chat_id]


class FakeLlm:
    """Сценарий ответов по роли и подстроке запроса; хранит журнал вызовов."""

    def __init__(self) -> None:
        self.rules: list[tuple[str, str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.down = False

    def on(self, role: str, contains: str, reply: Any) -> None:
        self.rules.insert(0, (role, contains, reply))

    def _reply(self, role: str, prompt: str, kw: dict[str, Any]) -> Any:
        self.calls.append({"role": role, "prompt": prompt, **kw})
        if self.down:
            from support_agent.llm import LlmUnavailable

            raise LlmUnavailable("no_cli_available")
        for r, contains, reply in self.rules:
            if r == role and contains in prompt:
                return reply(prompt, kw) if callable(reply) else reply
        raise AssertionError(f"no fake rule for role={role} prompt={prompt[:120]!r}")

    def ask(self, role: str, prompt: str, **kw: Any) -> LlmResult:
        reply = self._reply(role, prompt, kw)
        text = reply if isinstance(reply, str) else __import__("json").dumps(reply, ensure_ascii=False)
        return LlmResult(text, kw.get("_cli", "claude"), "fake-model", "sess")

    def ask_json(self, role: str, prompt: str, **kw: Any) -> tuple[dict[str, Any], LlmResult]:
        result = self.ask(role, prompt, **kw)
        from support_agent.llm import extract_json

        return extract_json(result.text), result

    def roles(self) -> list[str]:
        return [c["role"] for c in self.calls]


class FakeTrello:
    def __init__(self) -> None:
        self.cards: dict[str, dict[str, Any]] = {}
        self.comments_by: dict[str, list[str]] = {}
        self.creates = 0
        self.moves: list[tuple[str, str]] = []
        self.lose_response_once = False
        self.reject = False
        self.hide_after_lose = False
        self.ids = itertools.count(1)

    def create_card(self, *, list_id: str, name: str, desc: str, label_id: str = "") -> dict[str, Any]:
        if self.reject:
            raise TrelloError("http_400", rejected=True)
        self.creates += 1
        cid = f"c{next(self.ids)}"
        self.cards[cid] = {"id": cid, "idList": list_id, "name": name, "desc": desc,
                           "label": label_id, "shortUrl": f"https://trello.test/{cid}"}
        if self.lose_response_once:
            self.lose_response_once = False
            raise TrelloError("transport_ReadTimeout")
        return self.cards[cid]

    def find_by_marker(self, marker: str) -> dict[str, Any] | None:
        if self.hide_after_lose:
            return None
        for card in self.cards.values():
            if marker in card["desc"].splitlines():
                return card
        return None

    def get_card(self, card_id: str) -> dict[str, Any]:
        return self.cards[card_id]

    def comments(self, card_id: str) -> list[str]:
        return self.comments_by.get(card_id, [])

    def add_comment(self, card_id: str, text: str) -> None:
        self.comments_by.setdefault(card_id, []).append(text)

    def move_card(self, card_id: str, list_id: str) -> None:
        self.moves.append((card_id, list_id))
        self.cards[card_id]["idList"] = list_id


class FakeWms:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}

    def new_requests(self, cursor: dict[str, str] | None, limit: int = 50) -> list[dict[str, Any]]:
        out = []
        for row in self.rows:
            if cursor is None or (row["created_at"], row["id"]) > (cursor["created_at"], cursor["id"]):
                out.append(row)
        return out[:limit]

    def request(self, request_id: str) -> dict[str, Any]:
        if request_id in self.by_id:
            return self.by_id[request_id]
        for row in self.rows:
            if row["id"] == request_id:
                return row
        from support_agent.wms import WmsError

        raise WmsError("http_404")


class FakeTranscriber:
    def __init__(self) -> None:
        self.fail = 0
        self.text = "не открывается поставка"

    def transcribe(self, audio: bytes) -> str:
        from support_agent.transcribe import TranscribeError

        if self.fail > 0:
            self.fail -= 1
            raise TranscribeError("whisper_failed")
        return self.text


class Clock:
    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, sec: float) -> None:
        self.now += sec


@pytest.fixture
def env(tmp_path: Any) -> SimpleNamespace:
    cfg = make_config(tmp_path)
    store = Store(cfg.db_path)
    tg, llm, trello, wms, tr = FakeTelegram(), FakeLlm(), FakeTrello(), FakeWms(), FakeTranscriber()
    clock = Clock()
    pipe = Pipeline(cfg, store, tg, llm, trello, wms, tr, pool=InlinePool(), clock=clock)  # type: ignore[arg-type]
    mid = itertools.count(1)

    def say(chat: int, text: str, *, user: int = 5, name: str = "Анна", reply_to: str | None = None,
            role: str | None = None, voice: bool = False, msg_id: str | None = None) -> int | None:
        role = role or {CLIENT_CHAT: "client", PARTNER_CHAT: "partner", OWNER_CHAT: "owner"}[chat]
        result = pipe.ingest(Inbound(
            source="telegram", chat_id=chat, msg_id=msg_id or str(next(mid)), role=role,
            author_id=str(user), author_name=name, ts=clock.now, kind="voice" if voice else "text",
            text="" if voice else text, file_id="f1" if voice else None, reply_to=reply_to,
        ))
        pipe.route_messages()  # в службе то же делает tick()
        return result

    def flush() -> None:
        from support_agent.telegram import flush_outbox

        flush_outbox(store, tg, cfg)  # type: ignore[arg-type]

    return SimpleNamespace(cfg=cfg, store=store, tg=tg, llm=llm, trello=trello, wms=wms,
                           tr=tr, clock=clock, pipe=pipe, say=say, flush=flush)


def ok(rc: int = 0, out: str = "", err: str = "") -> ExecResult:
    return ExecResult(rc, out, err)


def normalize_git(argv: list[str]) -> list[str]:
    """Убирает жёсткую обвязку git (env и -c ...), чтобы тесты сверяли суть команды."""
    if argv[:2] == ["/usr/bin/env", "GIT_CONFIG_NOSYSTEM=1"] and argv[2] == "git":
        rest = argv[3:]
        out = ["git"]
        i = 0
        while i < len(rest):
            if rest[i] == "-c" and i + 1 < len(rest):
                if rest[i + 1].startswith(("core.", "diff.external", "user.")):
                    i += 2
                    continue
            out.append(rest[i])
            i += 1
        return out
    return argv


class FakeShell:
    """Подделка git/gh/ruff/pytest: ответы по подстроке команды, журнал вызовов."""

    def __init__(self) -> None:
        self.rules: list[tuple[str, Callable[[list[str]], ExecResult] | ExecResult]] = []
        self.calls: list[list[str]] = []
        self.raw_calls: list[list[str]] = []
        self.cwd: str | None = None

    def on(self, contains: str, reply: Callable[[list[str]], ExecResult] | ExecResult) -> None:
        self.rules.insert(0, (contains, reply))

    def __call__(self, argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        self.raw_calls.append(list(argv))
        self.cwd = cwd
        argv = normalize_git(argv)
        self.calls.append(argv)
        line = " ".join(argv)
        for contains, reply in self.rules:
            if contains in line:
                return reply(argv) if callable(reply) else reply
        return ok()

    def ran(self, contains: str) -> int:
        return sum(1 for c in self.calls if contains in " ".join(c))
