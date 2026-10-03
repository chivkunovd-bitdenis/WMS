"""Главный цикл: Telegram long polling, опрос формы, стадии, отправка. Работает как служба (R32)."""

from __future__ import annotations

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

from .config import Config
from .agent_coordinator import AgentCoordinator
from .hotfix import HotfixRunner
from .llm import LlmRouter
from .mockups import MockupRunner
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
        recover_after_restart(self.store, self.cfg)
        if self.pipe.agent is not None:
            self.pipe.agent.recover_after_restart()
        now = self.clock()
        last = self.store.kv_get("heartbeat")
        if last is not None and now - float(last) > self.cfg.limits.downtime_notice_sec:
            self.catchup = {"from": float(last), "to": now, "chats": 0, "forms": 0}
        self.store.kv_set("heartbeat", now)

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
        client = self.bots.named()[bot]
        key = self._offset_key(bot)
        offset = int(self.store.kv_get(key, self.store.kv_get("tg_offset", 0) if bot == "intake" else 0))
        updates = client.get_updates(offset, timeout)
        count = 0
        for update in updates:
            inb = normalize_update(update, self.cfg, bot)
            if inb is not None and self.pipe.ingest(inb) is not None:
                count += 1
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

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        self.startup()
        log.info("support agent started (%s)", "one bot" if self.bots.single else "intake and owner bots")
        threads = []
        if not self.bots.single:  # два бота опрашиваются независимо, каждый в своём потоке
            for bot in self.bots.named():
                thread = threading.Thread(target=self._poll_forever, args=(bot,), daemon=True,
                                          name=f"poll-{bot}")
                thread.start()
                threads.append(thread)
        while not self.stop:
            try:
                self.loop_once(poll=self.bots.single)
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
    if cfg.agent.enabled:
        from .agent_tools import AgentTools
        pipe.agent = AgentCoordinator(pipe, AgentTools(pipe))
    return Agent(cfg, store, tg, pipe)
