"""Локальное хранилище состояния (SQLite). Переживает перезапуск агента и мака (R33)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL, chat_id INTEGER NOT NULL, msg_id TEXT NOT NULL,
  role TEXT NOT NULL, author_id TEXT, author_name TEXT, ts REAL NOT NULL,
  kind TEXT NOT NULL DEFAULT 'text', text TEXT NOT NULL DEFAULT '', file_id TEXT,
  status TEXT NOT NULL, ticket_id INTEGER, reply_to TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  UNIQUE (source, chat_id, msg_id)
);
CREATE INDEX IF NOT EXISTS ix_messages_status ON messages (status);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, source TEXT NOT NULL, chat_id INTEGER, seller TEXT NOT NULL DEFAULT '',
  stage TEXT NOT NULL, category TEXT, author_id TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, last_activity REAL NOT NULL,
  data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL UNIQUE, chat_id INTEGER NOT NULL, reply_to TEXT, text TEXT NOT NULL,
  status TEXT NOT NULL, tg_message_id TEXT, ticket_id INTEGER, purpose TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0, repeat_ok INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, sent_at REAL, file_path TEXT
);
CREATE TABLE IF NOT EXISTS cards (
  key TEXT PRIMARY KEY, ticket_id INTEGER, marker TEXT NOT NULL, status TEXT NOT NULL,
  card_id TEXT, url TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, cli TEXT NOT NULL, model TEXT NOT NULL,
  effort TEXT, role TEXT NOT NULL, ticket_id INTEGER, ok INTEGER NOT NULL, error TEXT
);
CREATE TABLE IF NOT EXISTS chat_bindings (
  chat_id INTEGER PRIMARY KEY, seller_id TEXT NOT NULL, seller_name TEXT NOT NULL,
  tenant_id TEXT NOT NULL, tenant_name TEXT NOT NULL, bound_at REAL NOT NULL, bound_by TEXT NOT NULL,
  chat_title TEXT NOT NULL DEFAULT '', level TEXT NOT NULL DEFAULT 'seller'
);
CREATE TABLE IF NOT EXISTS binding_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, candidates TEXT NOT NULL,
  requested_by TEXT NOT NULL, created_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  chat_title TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS wms_numbers (
  number INTEGER PRIMARY KEY, ticket_id INTEGER, ts REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.scrubber: Callable[[str], str] = lambda text: text  # маскировка секретов в исходящем
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA busy_timeout=5000")
            self.db.executescript(SCHEMA)
            for ddl in ("ALTER TABLE chat_bindings ADD COLUMN level TEXT NOT NULL DEFAULT 'seller'",
                        "ALTER TABLE chat_bindings ADD COLUMN chat_title TEXT NOT NULL DEFAULT ''",
                        "ALTER TABLE binding_proposals ADD COLUMN chat_title TEXT NOT NULL DEFAULT ''"):
                try:  # база прежней версии: уровень привязки и название чата
                    self.db.execute(ddl)
                except sqlite3.OperationalError:
                    pass
            try:  # база старой версии без файлов в очереди отправки
                self.db.execute("ALTER TABLE outbox ADD COLUMN file_path TEXT")
            except sqlite3.OperationalError:
                pass

    # -- low level -----------------------------------------------------------------
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.db.execute(sql, params)

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return list(self.db.execute(sql, params).fetchall())

    def row(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.db.execute(sql, params).fetchone()

    # -- kv ------------------------------------------------------------------------
    def kv_get(self, key: str, default: Any = None) -> Any:
        row = self.row("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def kv_set(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def kv_once(self, key: str) -> bool:
        """True только при первом вызове с этим ключом (дедупликация одноразовых уведомлений)."""
        cur = self.execute("INSERT OR IGNORE INTO kv(key,value) VALUES(?, 'true')", (key,))
        return cur.rowcount == 1

    # -- messages ------------------------------------------------------------------
    def add_message(
        self,
        *,
        source: str,
        chat_id: int,
        msg_id: str,
        role: str,
        author_id: str,
        author_name: str,
        ts: float,
        kind: str,
        text: str,
        file_id: str | None,
        reply_to: str | None,
    ) -> int | None:
        """None, если такое сообщение уже сохранено (повторная доставка, R35)."""
        status = "transcribing" if kind == "voice" else "new"
        cur = self.execute(
            "INSERT OR IGNORE INTO messages(source,chat_id,msg_id,role,author_id,author_name,ts,"
            "kind,text,file_id,status,reply_to) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (source, chat_id, msg_id, role, author_id, author_name, ts, kind, text, file_id,
             status, reply_to),
        )
        return cur.lastrowid if cur.rowcount == 1 else None

    def messages_with_status(self, status: str, limit: int = 100) -> list[sqlite3.Row]:
        return self.rows(
            "SELECT * FROM messages WHERE status=? ORDER BY ts, id LIMIT ?", (status, limit)
        )

    def set_message(self, message_id: int, **values: Any) -> None:
        keys = ", ".join(f"{k}=?" for k in values)
        self.execute(f"UPDATE messages SET {keys} WHERE id=?", (*values.values(), message_id))

    def ticket_messages(self, ticket_id: int) -> list[sqlite3.Row]:
        return self.rows("SELECT * FROM messages WHERE ticket_id=? ORDER BY ts, id", (ticket_id,))

    def recent_chat_messages(self, chat_id: int, since_ts: float) -> list[sqlite3.Row]:
        return self.rows(
            "SELECT * FROM messages WHERE chat_id=? AND ts>=? AND role!='owner' ORDER BY ts, id",
            (chat_id, since_ts),
        )

    # -- tickets -------------------------------------------------------------------
    def add_ticket(
        self,
        *,
        kind: str,
        source: str,
        chat_id: int | None,
        seller: str,
        stage: str,
        author_id: str = "",
        category: str | None = None,
        data: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> int:
        now = now if now is not None else time.time()
        cur = self.execute(
            "INSERT INTO tickets(kind,source,chat_id,seller,stage,category,author_id,created_at,"
            "updated_at,last_activity,data) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (kind, source, chat_id, seller, stage, category, author_id, now, now, now,
             json.dumps(data or {}, ensure_ascii=False)),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def ticket(self, ticket_id: int) -> sqlite3.Row:
        row = self.row("SELECT * FROM tickets WHERE id=?", (ticket_id,))
        assert row is not None, f"ticket {ticket_id} not found"
        return row

    def tickets_in(self, *stages: str) -> list[sqlite3.Row]:
        marks = ",".join("?" for _ in stages)
        return self.rows(f"SELECT * FROM tickets WHERE stage IN ({marks}) ORDER BY id", stages)

    def open_chat_tickets(self, chat_id: int) -> list[sqlite3.Row]:
        closed = ("done", "closed", "rejected", "failed")
        marks = ",".join("?" for _ in closed)
        return self.rows(
            f"SELECT * FROM tickets WHERE chat_id=? AND kind='chat' AND stage NOT IN ({marks}) "
            "ORDER BY id",
            (chat_id, *closed),
        )

    def data(self, ticket_id: int) -> dict[str, Any]:
        result = json.loads(self.ticket(ticket_id)["data"])
        assert isinstance(result, dict)
        return result

    def set_stage(self, ticket_id: int, stage: str, **data_patch: Any) -> None:
        with self.lock:
            data = self.data(ticket_id)
            data.update(data_patch)
            self.db.execute(
                "UPDATE tickets SET stage=?, data=?, updated_at=? WHERE id=?",
                (stage, json.dumps(data, ensure_ascii=False), time.time(), ticket_id),
            )

    def patch_data(self, ticket_id: int, **data_patch: Any) -> dict[str, Any]:
        with self.lock:
            data = self.data(ticket_id)
            data.update(data_patch)
            self.db.execute(
                "UPDATE tickets SET data=?, updated_at=? WHERE id=?",
                (json.dumps(data, ensure_ascii=False), time.time(), ticket_id),
            )
            return data

    def set_ticket(self, ticket_id: int, **values: Any) -> None:
        keys = ", ".join(f"{k}=?" for k in values)
        self.execute(f"UPDATE tickets SET {keys} WHERE id=?", (*values.values(), ticket_id))

    def touch(self, ticket_id: int, now: float | None = None) -> None:
        self.set_ticket(ticket_id, last_activity=now if now is not None else time.time())

    # -- outbox --------------------------------------------------------------------
    def queue_message(
        self,
        *,
        key: str,
        chat_id: int,
        text: str,
        reply_to: str | None = None,
        ticket_id: int | None = None,
        purpose: str = "",
        repeat_ok: bool = False,
        file_path: str | None = None,
    ) -> bool:
        """Записывает НАМЕРЕНИЕ отправить. Тот же key второй раз не создаёт сообщения."""
        text = self.scrubber(text)
        cur = self.execute(
            "INSERT OR IGNORE INTO outbox(key,chat_id,reply_to,text,status,ticket_id,purpose,"
            "repeat_ok,created_at,file_path) VALUES(?,?,?,?, 'pending', ?,?,?,?,?)",
            (key, chat_id, reply_to, text, ticket_id, purpose, int(repeat_ok), time.time(), file_path),
        )
        return cur.rowcount == 1

    def outbox_by_key(self, key: str) -> sqlite3.Row | None:
        return self.row("SELECT * FROM outbox WHERE key=?", (key,))

    def outbox_pending(self) -> list[sqlite3.Row]:
        return self.rows("SELECT * FROM outbox WHERE status='pending' ORDER BY id")

    def claim_outbox(self, outbox_id: int) -> bool:
        """pending -> sending ДО обращения к Telegram: убитый процесс оставит след."""
        cur = self.execute(
            "UPDATE outbox SET status='sending', attempts=attempts+1 WHERE id=? AND status='pending'",
            (outbox_id,),
        )
        return cur.rowcount == 1

    def finish_outbox(self, outbox_id: int, status: str, tg_message_id: str | None = None) -> None:
        self.execute(
            "UPDATE outbox SET status=?, tg_message_id=COALESCE(?, tg_message_id), sent_at=? "
            "WHERE id=?",
            (status, tg_message_id, time.time(), outbox_id),
        )

    def settle_interrupted_sends(self) -> list[sqlite3.Row]:
        """После перезапуска: 'sending' без итога — исход неизвестен. Клиенту не повторяем (R35)."""
        stuck = self.rows("SELECT * FROM outbox WHERE status='sending'")
        for item in stuck:
            if item["repeat_ok"]:
                self.execute("UPDATE outbox SET status='pending' WHERE id=?", (item["id"],))
            else:
                self.execute("UPDATE outbox SET status='unknown' WHERE id=?", (item["id"],))
        return [row for row in stuck if not row["repeat_ok"]]

    def ticket_for_tg_message(self, chat_id: int, tg_message_id: str) -> int | None:
        row = self.row(
            "SELECT ticket_id FROM outbox WHERE chat_id=? AND tg_message_id=? "
            "AND ticket_id IS NOT NULL",
            (chat_id, tg_message_id),
        )
        return int(row["ticket_id"]) if row else None

    def outbox_for_tg_message(self, chat_id: int, tg_message_id: str) -> sqlite3.Row | None:
        return self.row(
            "SELECT * FROM outbox WHERE chat_id=? AND tg_message_id=? AND ticket_id IS NOT NULL",
            (chat_id, tg_message_id),
        )

    def outbox_purpose_for_tg_message(self, chat_id: int, tg_message_id: str) -> str | None:
        row = self.row(
            "SELECT purpose FROM outbox WHERE chat_id=? AND tg_message_id=?",
            (chat_id, tg_message_id),
        )
        return str(row["purpose"]) if row else None

    # -- привязка чата к селлеру (R39, R40) -------------------------------------------
    def binding(self, chat_id: int) -> sqlite3.Row | None:
        return self.row("SELECT * FROM chat_bindings WHERE chat_id=?", (chat_id,))

    def bindings(self) -> list[sqlite3.Row]:
        return self.rows("SELECT * FROM chat_bindings ORDER BY chat_id")

    def set_binding(self, chat_id: int, seller: dict[str, str], bound_by: str, chat_title: str = "") -> None:
        """Один чат — один селлер: прежняя привязка заменяется."""
        self.execute(
            "INSERT INTO chat_bindings(chat_id,seller_id,seller_name,tenant_id,tenant_name,bound_at,"
            "bound_by,chat_title,level) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET "
            "seller_id=excluded.seller_id,seller_name=excluded.seller_name,tenant_id=excluded.tenant_id,"
            "tenant_name=excluded.tenant_name,bound_at=excluded.bound_at,bound_by=excluded.bound_by,"
            "chat_title=excluded.chat_title,level=excluded.level",
            (chat_id, seller.get("seller_id", ""), seller.get("seller_name", ""), seller["tenant_id"],
             seller["tenant_name"], time.time(), bound_by, chat_title, seller.get("level", "seller")),
        )

    def add_proposal(self, chat_id: int, candidates: list[dict[str, str]], requested_by: str,
                     chat_title: str = "") -> int:
        self.execute("UPDATE binding_proposals SET status='replaced' WHERE chat_id=? AND status='open'",
                     (chat_id,))
        cur = self.execute(
            "INSERT INTO binding_proposals(chat_id,candidates,requested_by,created_at,chat_title) "
            "VALUES(?,?,?,?,?)",
            (chat_id, json.dumps(candidates, ensure_ascii=False), requested_by, time.time(), chat_title),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def proposal(self, proposal_id: int) -> sqlite3.Row | None:
        return self.row("SELECT * FROM binding_proposals WHERE id=?", (proposal_id,))

    def close_proposal(self, proposal_id: int, status: str) -> None:
        self.execute("UPDATE binding_proposals SET status=? WHERE id=?", (status, proposal_id))

    def outbox_by_tg(self, chat_id: int, tg_message_id: str) -> sqlite3.Row | None:
        return self.row("SELECT * FROM outbox WHERE chat_id=? AND tg_message_id=?", (chat_id, tg_message_id))

    # -- cards ---------------------------------------------------------------------
    def card(self, key: str) -> sqlite3.Row | None:
        return self.row("SELECT * FROM cards WHERE key=?", (key,))

    def set_card(
        self,
        key: str,
        *,
        ticket_id: int | None,
        marker: str,
        status: str,
        card_id: str | None = None,
        url: str | None = None,
    ) -> None:
        self.execute(
            "INSERT INTO cards(key,ticket_id,marker,status,card_id,url,created_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET status=excluded.status,"
            "card_id=COALESCE(excluded.card_id, cards.card_id), url=COALESCE(excluded.url, cards.url)",
            (key, ticket_id, marker, status, card_id, url, time.time()),
        )

    # -- журнал вызовов моделей ----------------------------------------------------
    def log_llm(
        self,
        *,
        cli: str,
        model: str,
        effort: str | None,
        role: str,
        ticket_id: int | None,
        ok: bool,
        error: str | None = None,
    ) -> None:
        self.execute(
            "INSERT INTO llm_calls(ts,cli,model,effort,role,ticket_id,ok,error) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (time.time(), cli, model, effort, role, ticket_id, int(ok), (error or "")[:300]),
        )

    # -- номера задач --------------------------------------------------------------
    def reserve_number(self, number: int, ticket_id: int | None) -> bool:
        cur = self.execute(
            "INSERT OR IGNORE INTO wms_numbers(number,ticket_id,ts) VALUES(?,?,?)",
            (number, ticket_id, time.time()),
        )
        return cur.rowcount == 1

    def max_reserved_number(self) -> int:
        row = self.row("SELECT MAX(number) AS n FROM wms_numbers")
        return int(row["n"]) if row and row["n"] is not None else 0
