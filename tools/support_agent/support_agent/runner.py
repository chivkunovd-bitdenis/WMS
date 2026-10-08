"""Главный цикл: Telegram long polling, опрос формы, стадии, отправка. Работает как служба (R32)."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from .agent_coordinator import AgentCoordinator
from .config import Config
from .hotfix import HotfixRunner
from .llm import LlmRouter
from .mockups import MockupRunner
from .night import NightRunner
from .pipeline import Pipeline, ThreadPool
from .prod_sql import ProdSqlSettings
from .redact import scrub
from .seller_directory import SellerDirectory
from .store import Store
from .telegram import (
    Bots,
    TelegramClient,
    TelegramError,
    as_bots,
    flush_outbox,
    normalize_update,
    recover_after_restart,
)
from .transcribe import Transcriber
from .trello import TrelloClient
from .wms import WmsClient

log = logging.getLogger(__name__)
DAY = 24 * 3600


class RedactFilter(logging.Filter):
    """Фильтр ОБРАБОТЧИКА (а не logger'а): применяется ко всем записям, в том числе дочерних
    logger'ов (httpx и др.), и к тексту исключения (R37)."""

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(self.cfg, record.getMessage())
        record.args = ()
        if record.exc_info:
            text = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = scrub(self.cfg, text)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = scrub(self.cfg, record.exc_text)
        if record.stack_info:
            record.stack_info = scrub(self.cfg, record.stack_info)
        return True


def install_logging(cfg: Config) -> None:
    """Маскировка на каждом обработчике корня + журналирование URL у httpx/httpcore выключено."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    flt = RedactFilter(cfg)
    for handler in logging.getLogger().handlers:
        handler.addFilter(flt)


class Agent:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        tg: Any,
        pipeline: Pipeline,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cfg, self.store, self.pipe, self.clock = cfg, store, pipeline, clock
        self.bots = as_bots(tg, cfg.telegram.owner_chat_id)
        self.tg = self.bots.intake
        self.lock = threading.RLock()
        self.drained: set[str] = set()
        self.stop = False
        self.catchup: dict[str, float] | None = None
        self.last_form_poll = 0.0

    # ---- запуск ----------------------------------------------------------------------
    def startup(self) -> None:
        if self.cfg.agent.intake_only or self.cfg.agent.visible_moderator:
            if self.cfg.agent.visible_moderator:
                if self.cfg.agent.enabled and self.pipe.agent is not None:
                    dispatcher = self.pipe.agent.dispatcher
                    dispatcher.prepare_visible_realtime()
                    dispatcher.recover_visible_realtime()
                    dispatcher.recover_visible_card_projections()
                    dispatcher.tick()
                    self._settle_visible_realtime_outbox()
                    self._settle_visible_case_cards()
                self._recover_visible_native_sends()
            self.store.kv_set("heartbeat", self.clock())
            return
        recover_after_restart(self.store, self.cfg)
        if self.pipe.agent is not None:
            self.pipe.agent.recover_after_restart()
        now = self.clock()
        last = self.store.kv_get("heartbeat")
        if last is not None and now - float(last) > self.cfg.limits.downtime_notice_sec:
            self.catchup = {"from": float(last), "to": now, "chats": 0, "forms": 0}
        self.store.kv_set("heartbeat", now)

    def _recover_visible_native_sends(self) -> None:
        """Resolve only interrupted explicit native sends, never the legacy outbox."""
        from .case_journal import CaseJournal
        from .media import archive_root
        from .telegram import reconcile_unconfirmed_native_delivery

        journal = CaseJournal(self.store, archive_root(self.cfg))
        interrupted = self.store.rows(
            "SELECT * FROM outbox WHERE key LIKE 'native-send:%' "
            "AND status IN ('sending', 'unknown') ORDER BY id"
        )
        for item in interrupted:
            if item['status'] == 'sending':
                self.store.execute(
                    "UPDATE outbox SET status='unknown' WHERE id=? AND status='sending'",
                    (item['id'],),
                )
            resolved = self.store.outbox_by_key(item['key'])
            if resolved is not None and resolved['status'] == 'unknown':
                reconcile_unconfirmed_native_delivery(
                    journal, self.store, self.bots.owner, self.cfg.telegram.owner_chat_id, resolved,
                )

    def _fmt(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=UTC).strftime("%d.%m %H:%M UTC")

    def _finish_catchup(self) -> None:
        c = self.catchup
        if c is None:
            return
        text = (
            f"Агент снова работает. Он был недоступен с {self._fmt(c['from'])} до {self._fmt(c['to'])}. "
            f"Подобрано при возвращении: сообщений из чатов {int(c['chats'])}, записей формы "
            f"{int(c['forms'])}."
        )
        if c["to"] - c["from"] > DAY:
            text += (
                " Простой был дольше суток: Telegram хранит необработанные сообщения не дольше "
                "24 часов, поэтому часть сообщений в чатах за это время могла потеряться. "
                "Просмотрите чаты."
            )
        self.pipe.say_owner(f"downtime:{int(c['from'])}", text, purpose="downtime")
        self.catchup = None

    # ---- опрос ботов -----------------------------------------------------------------
    def _offset_key(self, bot: str) -> str:
        return f"tg_offset:{bot}"

    def poll_bot(self, bot: str, timeout: int = 10) -> int:
        """Один независимый long polling одного бота; у каждого бота свой offset в хранилище."""
        if (self.cfg.agent.visible_moderator and self.cfg.agent.enabled
                and self.pipe.agent is not None
                and not isinstance(self.store.kv_get("agent_realtime_cutover_v1"), dict)):
            self.pipe.agent.dispatcher.prepare_visible_realtime()
        client = self.bots.named()[bot]
        key = self._offset_key(bot)
        offset = int(self.store.kv_get(key, self.store.kv_get("tg_offset", 0) if bot == "intake" else 0))
        updates = client.get_updates(offset, timeout)
        count = 0
        for update in updates:
            inb = normalize_update(update, self.cfg, bot)
            realtime = bool(self.cfg.agent.visible_moderator and self.cfg.agent.enabled
                            and self.pipe.agent is not None)
            poll_marker_key = f"agent_realtime_poll_v1:{bot}:{int(update['update_id'])}"
            poll_marker: dict[str, Any] | None = None
            if inb is not None and realtime:
                cutover = self.store.kv_get("agent_realtime_cutover_v1", {})
                cutover_at = float(cutover.get("at", 0)) if isinstance(cutover, dict) else 0
                event_ts = max(float(inb.ts or 0), float(inb.edit_ts or 0))
                if event_ts and event_ts >= cutover_at:
                    poll_marker = self.store.kv_get(poll_marker_key)
                    if not poll_marker:
                        poll_marker = {
                            "realtime_version": 1, "update_id": int(update["update_id"]),
                            "source": inb.source, "chat_id": int(inb.chat_id),
                            "message_id": str(inb.msg_id), "received_at": self.clock(),
                            "state": "receiving",
                        }
                        # This proof precedes Store.add_message: redelivery can recover
                        # a crash in the add-row / source-marker / offset window.
                        self.store.kv_set(poll_marker_key, poll_marker)
            message_id = self.pipe.ingest(inb) if inb is not None else None
            if inb is not None and message_id is not None:
                count += 1
            if inb is not None and realtime:
                if message_id is None:
                    existing = self.store.row(
                        "SELECT * FROM messages WHERE source=? AND chat_id=? AND msg_id=?",
                        (inb.source, inb.chat_id, inb.msg_id),
                    )
                    if existing is not None:
                        revision = int(existing["revision"])
                        marker_key = f"agent_realtime_received_v1:{existing['id']}:{revision}"
                        event = self.store.kv_get(f"agent_event:in:{existing['id']}:{revision}", {})
                        if (poll_marker or self.store.kv_get(marker_key)
                                or event.get("realtime_version") == 1):
                            message_id = int(existing["id"])
                if message_id is not None:
                    message = self.store.row("SELECT * FROM messages WHERE id=?", (message_id,))
                    if message is not None:
                        revision = int(message["revision"])
                        receipt_key = f"agent_realtime_received_v1:{message_id}:{revision}"
                        event = self.store.kv_get(f"agent_event:in:{message_id}:{revision}", {})
                        if (poll_marker or self.store.kv_get(receipt_key)
                                or event.get("realtime_version") == 1):
                            self.store.kv_set(receipt_key, {
                                "update_id": int(update["update_id"]), "received_at": self.clock(),
                                "realtime_version": 1,
                            })
                            if poll_marker is not None:
                                poll_marker.update(state="accepted", source_id=int(message_id),
                                                   revision=revision)
                                self.store.kv_set(poll_marker_key, poll_marker)
                            if message["status"] == "transcribing":
                                self.pipe.agent.dispatcher._update_case_card(
                                    message, f"in:{message_id}:{revision}",
                                    f"topic-{message_id}", False, waiting_for_transcript=True,
                                )
                            elif (message["status"] == "new"
                                  or event.get("realtime_version") == 1):
                                self.pipe.agent.dispatcher.accept(message)
                                self.pipe.agent.dispatcher.tick()
            offset = max(offset, int(update["update_id"]) + 1)
        if updates:
            self.store.kv_set(key, offset)  # после сохранения сообщений (R35)
        with self.lock:
            if self.catchup is not None:
                self.catchup["chats"] += count
                if updates:
                    self.drained.discard(bot)
                else:
                    self.drained.add(bot)
                    if self.drained >= set(self.bots.named()):
                        self._finish_catchup()
        return count

    def poll_telegram(self, timeout: int = 10) -> int:
        total = 0
        for bot in self.bots.named():
            total += self.poll_bot(bot, timeout)
        return total

    def _poll_forever(self, bot: str) -> None:
        while not self.stop:
            try:
                self.poll_bot(bot, 25)
            except TelegramError as exc:
                log.warning("telegram poll (%s) failed: %s", bot, exc.code)
                time.sleep(5)
            except Exception:
                log.exception("poll %s failed", bot)
                time.sleep(5)

    # ---- один оборот цикла -----------------------------------------------------------
    def loop_once(self, tg_timeout: int = 10, poll: bool = True) -> None:
        now = self.clock()
        if poll:
            try:
                self.poll_telegram(tg_timeout)
            except TelegramError as exc:
                log.warning("telegram poll failed: %s", exc.code)
                time.sleep(min(5, tg_timeout))
        if self.cfg.agent.intake_only or self.cfg.agent.visible_moderator:
            if self.cfg.agent.visible_moderator:
                from .case_journal import CaseJournal
                from .media import archive_pending, archive_root

                if self.cfg.agent.enabled and self.pipe.agent is not None:
                    dispatcher = self.pipe.agent.dispatcher
                    for message in self.store.rows(
                            "SELECT * FROM messages WHERE status IN ('new','transcribing') "
                            "ORDER BY id"):
                        revision = int(message["revision"])
                        marker = self.store.kv_get(
                            f"agent_realtime_received_v1:{message['id']}:{revision}")
                        if not marker:
                            continue
                        if message["status"] == "transcribing":
                            dispatcher._update_case_card(
                                message, f"in:{message['id']}:{revision}",
                                f"topic-{message['id']}", False, waiting_for_transcript=True,
                            )
                        else:
                            dispatcher.accept(message)
                    dispatcher.tick()
                    dispatcher.recover_visible_card_projections()
                    self._flush_visible_realtime_outbox()
                self.pipe.transcribe_pending()
                self.pipe.pool.submit("media-archive", lambda: archive_pending(self.pipe))
                if now - float(self.store.kv_get("native_archive_at", 0)) >= 15:
                    def archive_chats() -> None:
                        journal = CaseJournal(self.store, archive_root(self.cfg))
                        for row in self.store.rows("SELECT DISTINCT chat_id FROM messages"):
                            journal.sync_chat(int(row["chat_id"]))
                        self.store.kv_set("native_archive_at", self.clock())
                    self.pipe.pool.submit("conversation-archive", archive_chats)
            self.store.kv_set("heartbeat", self.clock())
            return
        if now - self.last_form_poll >= self.cfg.wms.poll_interval_sec:
            self.last_form_poll = now
            before = self.store.row("SELECT COUNT(*) AS n FROM tickets WHERE kind='form'")
            self.pipe.poll_forms()
            after = self.store.row("SELECT COUNT(*) AS n FROM tickets WHERE kind='form'")
            if self.catchup is not None and before and after:
                self.catchup["forms"] += after["n"] - before["n"]
        self.pipe.tick()
        flush_outbox(self.store, self.bots, self.cfg)
        self.store.kv_set("heartbeat", self.clock())

    def _flush_visible_realtime_outbox(self) -> None:
        """Flush only sends authorized by a completed current-version analysis."""
        from .case_journal import CaseJournal
        from .media import archive_root

        marker_rows = self.store.rows(
            "SELECT key,value FROM kv WHERE key LIKE 'agent_realtime_outbox:%' ORDER BY key"
        )
        marked: dict[str, dict[str, Any]] = {}
        for row in marker_rows:
            try:
                value = json.loads(row["value"])
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                marked[str(row["key"])[len("agent_realtime_outbox:"):]] = value
        pending = self.store.outbox_pending()
        allowed = {int(item["id"]) for item in pending if str(item["key"]) in marked}
        if allowed:
            flush_outbox(self.store, self.bots, self.cfg, only_ids=allowed,
                         allow_scoped_client_replies=True)
        journal = CaseJournal(self.store, archive_root(self.cfg))
        for outbox_key, metadata in marked.items():
            item = self.store.outbox_by_key(outbox_key)
            if item is None or item["status"] not in {"sent", "unknown", "failed"}:
                continue
            if metadata.get("reported"):
                continue
            topic_id = str(metadata.get("topic_id") or "")
            card = self.store.kv_get(f"case_card:{topic_id}", {})
            if not card:
                continue
            kind = str(metadata.get("kind") or "answer")
            if item["status"] == "sent":
                if kind == "owner_response":
                    event_text = f"Ответ владельцу отправлен: {item['text']}"
                    statuses = {"working": True}
                elif kind == "question":
                    event_text = f"Уточнение отправлено клиенту: {item['text']}"
                    statuses = {"question_sent": True}
                else:
                    event_text = f"Ответ отправлен клиенту: {item['text']}"
                    statuses = {"answer_sent": True}
                if item["tg_message_id"]:
                    self.store.kv_set(
                        f"case_reply_topic:{item['chat_id']}:{item['tg_message_id']}",
                        topic_id,
                    )
            elif item["status"] == "unknown":
                event_text = ("Доставка ответа клиенту не подтверждена; повторную отправку "
                              "не выполняю до проверки чата.")
                statuses = {"owner_needed": True}
            else:
                event_text = "Telegram отклонил отправку клиентского сообщения; проверьте обращение."
                statuses = {"owner_needed": True}
            event_key = f"realtime-delivery:{item['id']}"
            updated = journal.update_card(
                self.bots.owner, self.cfg.telegram.owner_chat_id, topic_id,
                int(card.get("chat_id") or item["chat_id"]), statuses=statuses,
                event=event_text[:1400], event_key=event_key, event_timestamp=self.clock(),
            )
            current = self.store.kv_get(f"case_card:{topic_id}", updated)
            body = journal.render(current)
            delivered = bool(current.get("message_id") and current.get("last_text") == body)
            terminal = (not current.get("message_id")
                        and current.get("delivery") in {"unknown", "rejected"})
            metadata["reported"] = delivered or terminal
            self.store.kv_set(f"agent_realtime_outbox:{outbox_key}", metadata)

    def _settle_visible_realtime_outbox(self) -> None:
        """Mark interrupted current-version sends unknown without touching legacy rows."""
        for row in self.store.rows(
                "SELECT key,value FROM kv WHERE key LIKE 'agent_realtime_outbox:%'"):
            key = str(row["key"])[len("agent_realtime_outbox:"):]
            item = self.store.outbox_by_key(key)
            if item is not None and item["status"] == "sending":
                self.store.finish_outbox(int(item["id"]), "unknown")

    def _settle_visible_case_cards(self) -> None:
        """Do not retry a card creation whose Telegram response was lost on shutdown."""
        for row in self.store.rows("SELECT key,value FROM kv WHERE key LIKE 'case_card:%'"):
            card = json.loads(row["value"])
            if card.get("delivery") != "sending" or card.get("message_id"):
                continue
            card["delivery"] = "unknown"
            card["delivery_error"] = "process_interrupted_during_telegram_send"
            self.store.kv_set(str(row["key"]), card)

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        visible = self.cfg.agent.visible_moderator
        background_polling = not self.bots.single or visible
        if not visible:
            self.startup()
        elif (self.cfg.agent.enabled and self.pipe.agent is not None):
            self.pipe.agent.dispatcher.prepare_visible_realtime()
        threads = []
        if background_polling:
            for bot in self.bots.named():
                thread = threading.Thread(target=self._poll_forever, args=(bot,), daemon=True,
                                          name=f"poll-{bot}")
                thread.start()
                threads.append(thread)
        if visible:
            # Start intake before startup reconciliation can wait on a Telegram edit.
            self.startup()
        log.info("support agent started (%s)", "one bot" if self.bots.single else "intake and owner bots")
        while not self.stop:
            try:
                self.loop_once(poll=not background_polling)
                if threads:
                    time.sleep(2)
            except Exception:
                log.exception("loop failed")
                time.sleep(5)
        log.info("support agent stopped")


def build_agent(cfg: Config) -> Agent:
    install_logging(cfg)
    http = httpx.Client()
    store = Store(cfg.db_path)
    intake = TelegramClient(cfg.telegram.intake_token, http)
    owner = intake if cfg.telegram.single_bot else TelegramClient(cfg.telegram.owner_token, http)
    tg = Bots(intake, owner, cfg.telegram.owner_chat_id)
    llm = LlmRouter(cfg, store)
    trello = TrelloClient(cfg.trello, http, redact=lambda t: scrub(cfg, t))
    pipe = Pipeline(
        cfg, store, tg, llm, trello, WmsClient(cfg.wms, http),
        Transcriber(cfg.transcribe, cfg.openai, http), pool=ThreadPool(cfg.limits.max_parallel),
    )
    hotfix = HotfixRunner(pipe, http=http)
    pipe.hotfix = hotfix
    pipe.night = NightRunner(pipe, hotfix)
    if cfg.prod_db.enabled:
        c = cfg.prod_db
        directory = SellerDirectory(ProdSqlSettings(
            c.ssh_host, c.ssh_user, os.path.expanduser(c.ssh_key_path),
            os.path.expanduser(c.known_hosts) if c.known_hosts else "", c.row_limit, c.timeout_sec,
            c.max_bytes, c.ssh_bin))
        pipe.directory = directory
        llm.role_ensurer = directory.ensure_scope
        llm.role_alert = pipe.on_role_failure
    pipe.mockups = MockupRunner(pipe, hotfix)
    from .media import message_image_paths
    pipe.message_image_paths = lambda message: message_image_paths(pipe, message)
    if cfg.agent.enabled and not cfg.agent.intake_only:
        from .agent_tools import AgentTools
        pipe.agent = AgentCoordinator(pipe, AgentTools(pipe))
    return Agent(cfg, store, tg, pipe)
