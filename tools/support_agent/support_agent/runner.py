"""Главный цикл: Telegram long polling, опрос формы, стадии, отправка. Работает как служба (R32)."""

from __future__ import annotations

import logging
import re
import signal
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from .config import Config
from .hotfix import HotfixRunner
from .llm import LlmRouter
from .mockups import MockupRunner
from .pipeline import Pipeline, ThreadPool
from .store import Store
from .telegram import (
    TelegramClient,
    TelegramError,
    flush_outbox,
    normalize_update,
    recover_after_restart,
)
from .transcribe import Transcriber
from .trello import TrelloClient
from .wms import WmsClient

log = logging.getLogger(__name__)
DAY = 24 * 3600


SECRET_PATTERNS = [
    (re.compile(r"bot\d+:[\w-]{10,}"), "bot***"),
    (re.compile(r"(?i)\b(key|token|api_key|access_token)=[^&\s\"']+"), r"\1=***"),
    (re.compile(r"(?i)bearer\s+[\w.\-]+"), "Bearer ***"),
    (re.compile(r"\bsk-[\w\-]{12,}"), "sk-***"),
]


def scrub(cfg: Config, text: str) -> str:
    """Известные значения секретов и типовые формы токенов (URL Telegram, ключи Trello, Bearer)."""
    text = cfg.redact(text)
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


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
        tg: TelegramClient,
        pipeline: Pipeline,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cfg, self.store, self.tg, self.pipe, self.clock = cfg, store, tg, pipeline, clock
        self.stop = False
        self.catchup: dict[str, float] | None = None
        self.last_form_poll = 0.0

    # ---- запуск ----------------------------------------------------------------------
    def startup(self) -> None:
        recover_after_restart(self.store, self.cfg)
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

    # ---- один оборот цикла -----------------------------------------------------------
    def poll_telegram(self, timeout: int = 10) -> int:
        offset = int(self.store.kv_get("tg_offset", 0))
        updates = self.tg.get_updates(offset, timeout)
        count = 0
        for update in updates:
            inb = normalize_update(update, self.cfg)
            if inb is not None and self.pipe.ingest(inb) is not None:
                count += 1
            offset = max(offset, int(update["update_id"]) + 1)
        if updates:
            self.store.kv_set("tg_offset", offset)  # после сохранения сообщений (R35)
        if self.catchup is not None:
            self.catchup["chats"] += count
            if not updates:
                self._finish_catchup()
        return count

    def loop_once(self, tg_timeout: int = 10) -> None:
        now = self.clock()
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
        flush_outbox(self.store, self.tg, self.cfg)
        self.store.kv_set("heartbeat", self.clock())

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop", True))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop", True))
        self.startup()
        log.info("support agent started")
        while not self.stop:
            try:
                self.loop_once()
            except Exception:
                log.exception("loop failed")
                time.sleep(5)
        log.info("support agent stopped")


def build_agent(cfg: Config) -> Agent:
    install_logging(cfg)
    http = httpx.Client()
    store = Store(cfg.db_path)
    tg = TelegramClient(cfg.telegram.bot_token, http)
    llm = LlmRouter(cfg, store)
    pipe = Pipeline(
        cfg, store, tg, llm, TrelloClient(cfg.trello, http), WmsClient(cfg.wms, http),
        Transcriber(cfg.transcribe, cfg.openai, http), pool=ThreadPool(cfg.limits.max_parallel),
    )
    hotfix = HotfixRunner(pipe, http=http)
    pipe.hotfix = hotfix
    pipe.mockups = MockupRunner(pipe, hotfix)
    return Agent(cfg, store, tg, pipe)
