"""Главный цикл: Telegram long polling, опрос формы, стадии, отправка. Работает как служба (R32)."""

from __future__ import annotations

import logging
import signal
import time
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


class RedactFilter(logging.Filter):
    """Секреты не попадают в логи (R37)."""

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.cfg.redact(record.getMessage())
        record.args = ()
        return True


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
    logging.getLogger().addFilter(RedactFilter(cfg))
    http = httpx.Client()
    store = Store(cfg.db_path)
    tg = TelegramClient(cfg.telegram.bot_token, http)
    llm = LlmRouter(cfg, store)
    pipe = Pipeline(
        cfg, store, tg, llm, TrelloClient(cfg.trello, http), WmsClient(cfg.wms, http),
        Transcriber(cfg.transcribe), pool=ThreadPool(cfg.limits.max_parallel),
    )
    hotfix = HotfixRunner(pipe, http=http)
    pipe.hotfix = hotfix
    pipe.mockups = MockupRunner(pipe, hotfix)
    return Agent(cfg, store, tg, pipe)
