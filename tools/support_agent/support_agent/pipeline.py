"""Конвейер обращений: приём -> фильтр -> ворох -> классификация -> разбор -> сводка -> «кати».

Каждое обращение — строка tickets со стадией (stage). Стадии регистрируются в словаре
Pipeline.stages: новая стадия (разработка, вечерний отчёт, релиз — R38) добавляется новым
обработчиком, без правки приёма, фильтра и согласования.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from . import prompts
from .config import Config
from .llm import LlmError, LlmRouter, LlmUnavailable, extract_json
from .store import Store
from .telegram import Inbound, TelegramClient, TelegramError
from .transcribe import TranscribeError, Transcriber
from .trello import TrelloClient, TrelloError, ensure_card
from .wms import WmsClient, WmsError

log = logging.getLogger(__name__)

CLOSED = ("done", "closed", "rejected", "failed")
DECISION_INTENTS = ("go", "reject", "postpone", "mockup_yes", "mockup_no")
FORBIDDEN_IN_SUMMARY = re.compile(r"```|\b[\w/.-]+\.(py|tsx?|js|sql)\b|/app/|\b\d{9,}\b")


class InlinePool:
    """Синхронный исполнитель для тестов."""

    def submit(self, key: str, fn: Callable[[], None]) -> None:
        fn()

    def idle(self) -> bool:
        return True


class ThreadPool:
    """Параллельные обращения с пределом числа одновременных сессий (R34)."""

    def __init__(self, workers: int) -> None:
        self.executor = ThreadPoolExecutor(max_workers=max(1, workers))
        self.busy: set[str] = set()

    def submit(self, key: str, fn: Callable[[], None]) -> None:
        if key in self.busy:
            return
        self.busy.add(key)

        def run() -> None:
            try:
                fn()
            except Exception:
                log.exception("job %s failed", key)
            finally:
                self.busy.discard(key)

        self.executor.submit(run)

    def idle(self) -> bool:
        return not self.busy


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%d.%m %H:%M")


class Pipeline:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        tg: TelegramClient,
        llm: LlmRouter,
        trello: TrelloClient,
        wms: WmsClient,
        transcriber: Transcriber,
        pool: InlinePool | ThreadPool | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.cfg, self.store, self.tg, self.llm = cfg, store, tg, llm
        self.trello, self.wms, self.transcriber = trello, wms, transcriber
        self.pool = pool or ThreadPool(cfg.limits.max_parallel)
        self.clock = clock
        self.hotfix: Any = None  # HotfixRunner, подключается в runner (избегаем цикла импортов)
        self.mockups: Any = None
        self.stages: dict[str, Callable[[int], None]] = {
            "collecting": self.stage_collecting,
            "form_new": self.stage_form_new,
            "await_urgency": self.stage_await_urgency,
            "analysis": self.stage_analysis,
            "await_client_data": self.stage_await_client_data,
            "task_draft": self.stage_task_draft,
            "task_create": self.stage_task_create,
            "hotfix": self.stage_hotfix,
            "mockup": self.stage_mockup,
        }

    # ===== утилиты ====================================================================
    def say_owner(self, key: str, text: str, ticket_id: int | None = None, purpose: str = "notice") -> None:
        self.store.queue_message(
            key=key, chat_id=self.cfg.telegram.owner_chat_id, text=text, ticket_id=ticket_id,
            purpose=purpose, repeat_ok=True,
        )

    def say_client(
        self, key: str, chat_id: int, text: str, reply_to: str | None, ticket_id: int
    ) -> None:
        self.store.queue_message(
            key=key, chat_id=chat_id, text=text, reply_to=reply_to, ticket_id=ticket_id,
            purpose="client", repeat_ok=False,
        )

    def seller_of(self, tid: int) -> str:
        t = self.store.ticket(tid)
        if t["seller"]:
            return str(t["seller"])
        return "—"

    def title_of(self, tid: int) -> str:
        return str(self.store.data(tid).get("title") or "обращение без названия")

    def ticket_context(self, tid: int) -> str:
        """Всё, что известно об обращении, для аналитика (данные клиента — в обёртке)."""
        t, d = self.store.ticket(tid), self.store.data(tid)
        lines = [
            f"Обращение №{tid}. Источник: "
            f"{'форма «?» в WMS' if t['kind'] == 'form' else 'Telegram-чат клиента'}. "
            f"Клиент (селлер): {t['seller'] or '—'}."
        ]
        body: list[str] = []
        form = d.get("form")
        if form:
            body.append(
                f"Тип в форме: {'ошибка' if form['type'] == 'bug' else 'улучшение'}\n"
                f"Описание: {form.get('description') or ''}\nЭкран: {form.get('screen') or ''}\n"
                f"Проблема: {form.get('problem') or ''}\nПредложение: {form.get('proposal') or ''}\n"
                f"Путь экрана: {form.get('page_url') or '—'}"
            )
        else:
            first = self.store.ticket_messages(tid)
            if first:
                since = first[0]["ts"] - self.cfg.limits.context_window_min * 60
                context = [
                    m for m in self.store.recent_chat_messages(t["chat_id"], since)
                    if m["ticket_id"] != tid and m["ts"] < first[0]["ts"] and m["status"] == "dropped"
                ]
                if context:
                    body.append("Предшествующий разговор в чате:")
                    body += [f"[{_fmt_ts(m['ts'])}] {m['author_name']}: {m['text']}" for m in context]
            body.append("Сообщения по обращению:")
            body += [
                f"[{_fmt_ts(m['ts'])}] {m['author_name']}: {m['text']}"
                for m in self.store.ticket_messages(tid)
            ]
        text = prompts.wrap("\n".join(body))
        extra = []
        if d.get("urgency_client") is not None:
            extra.append(f"Ответ клиента о срочности: {prompts.wrap(str(d['urgency_client']))}")
        elif d.get("urgency_asked_ts"):
            extra.append("Клиент на вопрос о срочности не ответил.")
        if d.get("data_requests"):
            for req in d["data_requests"]:
                answer = req.get("answer")
                extra.append(
                    f"Мы просили у клиента: {req['points']}. "
                    + (f"Ответ: {prompts.wrap(str(answer))}" if answer else "Ответа нет.")
                )
        return "\n".join(lines + [text] + extra)

    def _chat_link(self, chat_id: int, msg_id: str) -> str:
        raw = str(chat_id)
        return f"https://t.me/c/{raw[4:] if raw.startswith('-100') else raw.lstrip('-')}/{msg_id}"

    # ===== приём ======================================================================
    def ingest(self, inb: Inbound) -> int | None:
        """Единый вид (R1): сохраняем; повтор того же сообщения игнорируется (R35)."""
        return self.store.add_message(
            source=inb.source, chat_id=inb.chat_id, msg_id=inb.msg_id, role=inb.role,
            author_id=inb.author_id, author_name=inb.author_name, ts=inb.ts, kind=inb.kind,
            text=inb.text, file_id=inb.file_id, reply_to=inb.reply_to,
        )

    def transcribe_pending(self) -> None:
        """R3: расшифровка с повторами; сбой не теряет сообщение."""
        for m in self.store.messages_with_status("transcribing"):
            if self.clock() < float(self.store.kv_get(f"voice_retry:{m['id']}", 0)):
                continue
            self.pool.submit(f"voice:{m['id']}", lambda m=m: self._transcribe_one(m))  # type: ignore[misc]

    def _transcribe_one(self, m: Any) -> None:
        try:
            audio = self.tg.download_file(m["file_id"])
            text = self.transcriber.transcribe(audio)
        except (TranscribeError, TelegramError) as exc:
            attempts = m["attempts"] + 1
            self.store.set_message(m["id"], attempts=attempts)
            if attempts >= self.cfg.transcribe.max_attempts:
                self.store.set_message(m["id"], status="transcribe_failed")
                seller = self._seller_for_chat(m["chat_id"], m["role"])
                self.say_owner(
                    f"voice_fail:{m['id']}",
                    f"Голосовое от {seller} не расшифровано. Клиенту ничего не отправлено.",
                )
                log.warning("voice %s not transcribed: %s", m["id"], exc)
            else:
                self.store.kv_set(f"voice_retry:{m['id']}", self.clock() + 30 * attempts)
            return
        self.store.set_message(m["id"], text=f"(расшифровка голосового) {text}", status="new")

    def _seller_for_chat(self, chat_id: int, role: str) -> str:
        chat = self.cfg.telegram.chats.get(chat_id)
        if role == "owner":
            return "владельца"
        return chat.seller if chat and chat.seller else "партнёрского чата"

    # ===== маршрутизация сообщений =====================================================
    def route_messages(self) -> None:
        chats = {m["chat_id"] for m in self.store.messages_with_status("new")}
        for chat_id in chats:
            self.pool.submit(f"chat:{chat_id}", lambda c=chat_id: self.process_chat(c))  # type: ignore[misc]

    def process_chat(self, chat_id: int) -> None:
        for m in [x for x in self.store.messages_with_status("new", 500) if x["chat_id"] == chat_id]:
            try:
                if m["role"] == "owner":
                    self.handle_owner_message(m)
                elif m["role"] == "partner":
                    self.handle_partner_message(m)
                else:
                    self.handle_client_message(m)
            except LlmUnavailable as exc:
                self._llm_down(str(exc))
                return  # сообщение остаётся 'new': обработается, когда модель вернётся
            except LlmError:
                self.store.set_message(m["id"], status="attached" if m["ticket_id"] else "dropped")
            except Exception as exc:
                log.exception("message %s failed", m["id"])
                attempts = m["attempts"] + 1
                self.store.set_message(m["id"], attempts=attempts)
                if attempts >= 3:
                    self.store.set_message(m["id"], status="error")
                    self.say_owner(
                        f"msg_error:{m['id']}",
                        f"Сообщение из чата ({self._seller_for_chat(m['chat_id'], m['role'])}) "
                        f"обработать не получилось ({type(exc).__name__}). Посмотрите его вручную.",
                    )

    # ----- клиентский чат ------------------------------------------------------------
    def handle_client_message(self, m: Any) -> None:
        # Ответ на наш вопрос (reply) — сразу к своему обращению, без фильтра.
        if m["reply_to"]:
            tid = self.store.ticket_for_tg_message(m["chat_id"], m["reply_to"])
            if tid is not None and self.store.ticket(tid)["stage"] not in CLOSED:
                self.attach(m, tid)
                return
        open_tickets = self.store.open_chat_tickets(m["chat_id"])
        listing = [{"id": str(t["id"]), "title": self.title_of(t["id"])} for t in open_tickets]
        waiting = [t["id"] for t in open_tickets if t["stage"] in ("await_urgency", "await_client_data")]
        try:
            verdict, _ = self.llm.ask_json(
                "filter", prompts.filter_prompt(m["text"], listing, waiting),
                system=prompts.FILTER_SYSTEM,
            )
        except LlmError:
            verdict = {"relevant": "unsure"}  # при сомнении не отбрасываем (R8)
        relevant = verdict.get("relevant")
        if relevant is False or str(relevant).lower() == "false":
            self.store.set_message(m["id"], status="dropped")
            return
        target = verdict.get("ticket_id")
        if isinstance(target, int) and target in [t["id"] for t in open_tickets]:
            self.attach(m, target)
            return
        chat = self.cfg.telegram.chats[m["chat_id"]]
        tid = self.store.add_ticket(
            kind="chat", source="telegram", chat_id=m["chat_id"], seller=chat.seller,
            stage="collecting", author_id=m["author_id"], now=self.clock(),
            data={"first_msg_id": m["msg_id"], "title": m["text"][:60]},
        )
        self.attach(m, tid)

    def attach(self, m: Any, tid: int) -> None:
        self.store.set_message(m["id"], status="attached", ticket_id=tid)
        t = self.store.ticket(tid)
        if t["stage"] == "collecting":
            self.store.touch(tid, self.clock())

    # ===== стадии =====================================================================
    def tick(self) -> None:
        """Раз в цикл: запускает всё, что готово. Параллельность — через пул (R34)."""
        self.transcribe_pending()
        self.route_messages()
        now = self.clock()
        for t in self.store.tickets_in(*self.stages):
            if self._ready(t, now):
                tid = t["id"]
                self.pool.submit(f"ticket:{tid}", lambda tid=tid: self.process_ticket(tid))  # type: ignore[misc]
        self.pool.submit("reports", self.send_reports)
        if now - float(self.store.kv_get("form_links_ts", 0)) >= 60:
            self.store.kv_set("form_links_ts", now)
            self.pool.submit("form_links", self.sync_form_cards)

    def _ready(self, t: Any, now: float) -> bool:
        d = self.store.data(t["id"])
        stage = t["stage"]
        if stage == "collecting":
            return now - t["last_activity"] >= self.cfg.limits.quiet_sec
        if stage in ("await_urgency", "await_client_data"):
            return self._answered(t["id"], d) or now >= float(d.get("deadline", 0))
        return True

    def _answered(self, tid: int, d: dict[str, Any]) -> bool:
        since = int(d.get("asked_after_msg", 0))
        return any(m["id"] > since for m in self.store.ticket_messages(tid))

    def _progress_key(self, tid: int) -> tuple[str, str]:
        t = self.store.ticket(tid)
        return t["stage"], str(self.store.data(tid).get("hotfix", {}).get("step", ""))

    def process_ticket(self, tid: int) -> None:
        """Идёт по стадиям, пока обращение готово двигаться дальше (без ожидания следующего цикла)."""
        for _ in range(12):
            before = self._progress_key(tid)
            handler = self.stages.get(before[0])
            if handler is None:
                return
            try:
                handler(tid)
            except LlmUnavailable as exc:
                self._llm_down(str(exc))
                return
            except LlmError:
                self._bump_error(tid, "модель не вернула понятный ответ")
                return
            except Exception as exc:
                log.exception("ticket %s stage %s failed", tid, before[0])
                self._bump_error(tid, type(exc).__name__)
                return
            after = self._progress_key(tid)
            if after == before or not self._ready(self.store.ticket(tid), self.clock()):
                return

    def _bump_error(self, tid: int, why: str) -> None:
        errors = int(self.store.data(tid).get("errors", 0)) + 1
        self.store.patch_data(tid, errors=errors)
        if errors >= 3:
            self.store.set_stage(tid, "failed")
            self.say_owner(
                f"ticket_failed:{tid}",
                f"Обращение №{tid} ({self.seller_of(tid)}): автоматически разобрать не получилось "
                f"({why}). Посмотрите вручную.",
                tid,
            )

    def _llm_down(self, reason: str) -> None:
        if self.store.kv_get("llm_unavailable_notified", False):
            return
        self.store.kv_set("llm_unavailable_notified", True)
        if reason == "claude_only_unavailable":
            text = (
                "Для правки интерфейса нужен Opus, а он сейчас недоступен (лимит или вход). "
                "Передать задачу Astra? Пока она ждёт в очереди."
            )
        else:
            text = (
                "Обе модели (Claude и Codex) сейчас недоступны: лимит или вход. Обращения ждут "
                "в очереди и обработаются сами, когда доступ вернётся."
            )
        self.say_owner(f"llm_down:{int(self.clock())}", text)

    # ----- ворох -> классификация ----------------------------------------------------
    def stage_collecting(self, tid: int) -> None:
        text = "\n".join(m["text"] for m in self.store.ticket_messages(tid))
        res, _ = self.llm.ask_json("filter", prompts.classify_prompt(text, None),
                                   system=prompts.FILTER_SYSTEM, ticket_id=tid)
        self._after_classify(tid, res)

    def stage_form_new(self, tid: int) -> None:
        d = self.store.data(tid)
        form = d["form"]
        text = "\n".join(str(form.get(k) or "") for k in ("description", "screen", "problem", "proposal"))
        res, _ = self.llm.ask_json("filter", prompts.classify_prompt(text, form["type"]),
                                   system=prompts.FILTER_SYSTEM, ticket_id=tid)
        if res.get("category") in ("bug", "improvement") and res["category"] != (
            "bug" if form["type"] == "bug" else "improvement"
        ):
            self.store.patch_data(tid, type_mismatch=True)
        self._after_classify(tid, res)

    def _after_classify(self, tid: int, res: dict[str, Any]) -> None:
        category = str(res.get("category", "other"))
        title = str(res.get("title") or self.title_of(tid))[:120]
        t = self.store.ticket(tid)
        self.store.patch_data(tid, title=title)
        self.store.set_ticket(tid, category=category)
        if category == "chatter" and t["kind"] == "chat":
            self.store.set_stage(tid, "closed")  # болтовня: ни ответа, ни сводки (R8)
            return
        if category not in ("bug", "improvement", "info") or res.get("confidence") == "low":
            self.store.set_stage(tid, "report_ready", verdict="other", ready_at=self.clock(),
                                 report={"body": self._other_body(tid)})
            return
        if category == "bug" and t["kind"] == "chat":
            self._ask_urgency(tid)
            return
        self.store.set_stage(tid, "analysis")

    def _other_body(self, tid: int) -> str:
        msgs = self.store.ticket_messages(tid)
        form = self.store.data(tid).get("form")
        raw = " / ".join(m["text"] for m in msgs)[:400] if msgs else str(form)[:400]
        return (
            "Не удалось уверенно понять, о чём обращение (не баг, не улучшение, не запрос "
            f"данных, либо не уверен). Что написали: {raw}\nХотфикс и карточка не создавались."
        )

    def _ask_urgency(self, tid: int) -> None:
        first = self.store.ticket_messages(tid)
        t = self.store.ticket(tid)
        self.say_client(
            f"t{tid}:urgency", t["chat_id"],
            "Подскажите, пожалуйста: это прямо сейчас мешает работе или можно исправить позже?",
            first[0]["msg_id"] if first else None, tid,
        )
        now = self.clock()
        self.store.set_stage(
            tid, "await_urgency", asked_ts=now, deadline=now + self.cfg.limits.urgency_wait_sec,
            asked_after_msg=max((m["id"] for m in first), default=0),
        )

    def stage_await_urgency(self, tid: int) -> None:
        d = self.store.data(tid)
        since = int(d.get("asked_after_msg", 0))
        answers = [m["text"] for m in self.store.ticket_messages(tid) if m["id"] > since]
        self.store.set_stage(tid, "analysis", urgency_client="\n".join(answers) if answers else None,
                             urgency_asked_ts=d.get("asked_ts"))

    # ----- разбор --------------------------------------------------------------------
    def stage_analysis(self, tid: int) -> None:
        d = self.store.data(tid)
        context = prompts.analysis_context(self.ticket_context(tid), self.cfg.llm.analyst_data_hint)
        analysis, result = self.llm.ask_json(
            "analyst", prompts.analysis_ask(d.get("resume_note")), ticket_id=tid,
            session_key="analyst", mode="readonly", cwd=self._analysis_cwd(), context=context,
        )
        self.store.patch_data(tid, analyst_cli=result.cli, analysis=analysis, resume_note=None)
        t = self.store.ticket(tid)
        need = analysis.get("need_data")
        if (
            need and need.get("points") and t["kind"] == "chat"
            and len(d.get("data_requests", [])) < 2
        ):
            self._ask_data(tid, need)
            return
        self._finalize(tid, analysis, result.cli)

    def _analysis_cwd(self) -> str | None:
        """Читаем проект из свежего origin/etalon, а не из чужого рабочего checkout."""
        if self.hotfix is not None:
            try:
                return str(self.hotfix.analysis_dir())
            except Exception:
                log.warning("analysis worktree unavailable, using repo", exc_info=True)
        return self.cfg.repo or None

    def _ask_data(self, tid: int, need: dict[str, Any]) -> None:
        d = self.store.data(tid)
        requests = list(d.get("data_requests", []))
        points = [str(p) for p in need["points"]]
        requests.append({"points": points, "answer": None})
        text = "Чтобы разобраться, пришлите, пожалуйста:\n" + "\n".join(
            f"{i}. {p}" for i, p in enumerate(points, 1)
        )
        msgs = self.store.ticket_messages(tid)
        self.say_client(f"t{tid}:data:{len(requests)}", self.store.ticket(tid)["chat_id"], text,
                        msgs[-1]["msg_id"] if msgs else None, tid)
        now = self.clock()
        self.store.set_stage(
            tid, "await_client_data", data_requests=requests, asked_ts=now,
            deadline=now + self.cfg.limits.data_wait_sec,
            asked_after_msg=max((m["id"] for m in msgs), default=0),
        )

    def stage_await_client_data(self, tid: int) -> None:
        d = self.store.data(tid)
        since = int(d.get("asked_after_msg", 0))
        answers = [m["text"] for m in self.store.ticket_messages(tid) if m["id"] > since]
        requests = list(d.get("data_requests", []))
        requests[-1]["answer"] = "\n".join(answers) if answers else None
        note = (
            "Клиент ответил: " + prompts.wrap("\n".join(answers)) if answers
            else "Клиент на просьбу не ответил. Оцени без этих данных и больше не проси."
        )
        self.store.set_stage(tid, "analysis", data_requests=requests, resume_note=note)

    def _finalize(self, tid: int, analysis: dict[str, Any], analyst_cli: str) -> None:
        t = self.store.ticket(tid)
        category = str(analysis.get("category") or t["category"] or "other")
        if category not in ("bug", "improvement", "info"):
            self.store.set_ticket(tid, category="other")
            self.store.set_stage(tid, "report_ready", verdict="other", ready_at=self.clock(),
                                 report={"body": self._other_body(tid)})
            return
        self.store.set_ticket(tid, category=category)
        hotfix = analysis.get("hotfix") or {}
        # R15: миграция или не один изолированный процесс — не «безопасный короткий».
        safe = bool(hotfix.get("safe")) and not hotfix.get("needs_migration") and bool(
            hotfix.get("single_process", False)
        )
        urgent = bool(analysis.get("urgent"))
        cross: dict[str, Any] | None = None
        if category == "bug" and safe:
            cross = self._crosscheck(tid, analysis, analyst_cli)
        card_note = ""
        if category == "improvement" or (category == "bug" and not urgent):
            card_note = self._card_for(tid, analysis)
        verdict = {"info": "info", "improvement": "trello"}.get(
            category, "hotfix" if safe else "bug_no_hotfix"
        )
        body = self._compose(tid, analysis, verdict, cross, card_note)
        self.store.set_stage(
            tid, "report_ready", verdict=verdict, ready_at=self.clock(), hotfix_ok=safe and category == "bug",
            urgent=urgent, cross=cross, report={"body": body},
            affected=hotfix.get("affected") or [],
        )

    def _crosscheck(self, tid: int, analysis: dict[str, Any], analyst_cli: str) -> dict[str, Any]:
        """R16: проверяет модель другого семейства; нет модели — честная пометка."""
        try:
            res, result = self.llm.ask_json(
                "review", prompts.crosscheck_prompt(self.ticket_context(tid), str(analysis)),
                ticket_id=tid, mode="readonly", cwd=self._analysis_cwd(), exclude_cli=analyst_cli,
            )
        except (LlmUnavailable, LlmError) as exc:
            return {"verdict": "not_done", "reason": str(exc)}
        return {"verdict": res.get("verdict", "uncertain"), "risks": res.get("risks") or [],
                "affected": res.get("affected") or [], "by": result.model}

    def _card_for(self, tid: int, analysis: dict[str, Any]) -> str:
        t, d = self.store.ticket(tid), self.store.data(tid)
        if t["kind"] == "form":
            return ""  # карточку формы создаёт WMS-624; агент только комментирует (R5)
        if not self.cfg.trello.api_key:
            return " Карточка в Trello не создана: Trello не настроен."
        card = analysis.get("improvement_card") or {}
        msgs = self.store.ticket_messages(tid)
        link = self._chat_link(t["chat_id"], msgs[0]["msg_id"]) if msgs else "—"
        body = (
            f"Клиент: {t['seller']}\nДата: {_fmt_ts(t['created_at'])} UTC\n"
            f"Источник: клиентский Telegram-чат, {link}\n\n"
            f"Суть: {card.get('description') or analysis.get('why', '')}\n\n"
            f"Что предлагается: {analysis.get('proposed_solution', '')}\n"
            f"Почему: {analysis.get('why_this_solution', '')}"
        )
        res = ensure_card(
            self.store, self.trello, key=f"ticket:{tid}", ticket_id=tid,
            list_id=self.cfg.trello.client_list_id,
            name=f"Клиент: {t['seller']} — {card.get('title') or d.get('title')}",
            body=body, label_id=self.cfg.trello.client_label_id,
        )
        if res.status == "linked":
            self.store.patch_data(tid, card_id=res.card_id, card_url=res.url)
            return f" Карточка в Trello создана: {res.url}"
        if res.status == "unknown":
            return " Карточка в Trello: исход создания неизвестен, повторно не создаю."
        return " Карточку в Trello создать не удалось (отказ Trello)."

    def _compose(
        self, tid: int, analysis: dict[str, Any], verdict: str, cross: dict[str, Any] | None,
        card_note: str,
    ) -> str:
        note = {
            "info": "Это запрос данных, а не поломка. Готовый ответ клиенту ниже в материалах.",
            "trello": "Вердикт: это улучшение, ушло в Trello.",
        }.get(verdict, "")
        try:
            result = self.llm.ask("routine", prompts.summary_prompt(str(analysis), note), ticket_id=tid)
            body = result.text.strip()
            if FORBIDDEN_IN_SUMMARY.search(body):
                body = self.llm.ask("routine", prompts.rewrite_summary_prompt(body),
                                    ticket_id=tid).text.strip()
                body = FORBIDDEN_IN_SUMMARY.sub("", body)
        except (LlmUnavailable, LlmError):
            body = "\n".join(
                [f"Что не работает: {'; '.join(analysis.get('problem_steps') or [])}",
                 f"Почему: {analysis.get('why', '')}",
                 f"Решение: {analysis.get('proposed_solution', '')}"]
            )
        lines = [body]
        d = self.store.data(tid)
        if verdict == "info" and analysis.get("info_answer"):
            lines.append(f"Ответ клиенту (после вашего «кати»): {analysis['info_answer']}")
        if cross is not None:
            if cross["verdict"] == "safe":
                lines.append("Проверка второй моделью: безопасно.")
            elif cross["verdict"] == "not_done":
                lines.append(
                    f"Перекрёстная проверка не проведена: {cross.get('reason', 'модель недоступна')}."
                )
            else:
                affected = ", ".join(cross.get("affected") or cross.get("risks") or []) or "—"
                lines.append(f"Проверка второй моделью: неопределённость высокая, затронуты: {affected}.")
        t = self.store.ticket(tid)
        if t["kind"] == "chat":
            if d.get("urgency_client") is None and d.get("urgency_asked_ts"):
                lines.append("Клиент на вопрос о срочности не ответил.")
            elif d.get("urgency_client") is not None:
                client_urgent = bool(re.search(r"срочн|сейчас|не могу|мешает|горит|встал",
                                               str(d["urgency_client"]), re.IGNORECASE))
                if client_urgent != bool(analysis.get("urgent")):
                    lines.append(
                        "Оценка срочности у нас и у клиента расходится: "
                        f"{analysis.get('urgency_reason', '')}"
                    )
        else:
            if d.get("type_mismatch"):
                lines.append("Тип в форме не совпал с сутью обращения (в форме указан другой).")
            missing = analysis.get("missing_for_owner") or []
            if analysis.get("need_data") and not missing:
                missing = analysis["need_data"].get("points") or []
            if missing:
                lines.append("Данных не хватает: " + "; ".join(str(x) for x in missing))
        return "\n".join(x for x in lines if x) + card_note

    # ----- сводки владельцу (R19, R20) -----------------------------------------------
    FOOTERS = {
        "hotfix": (
            "Ответьте на это сообщение: «кати» — сделаю быстрое исправление, «нет» — не делать, "
            "«позже» — отложить."
        ),
        "bug_no_hotfix": "Коротким хотфиксом это не закрыть. Решение за вами: «нет» или «позже».",
        "info": "Ответьте «кати» — отправлю этот ответ клиенту; «нет» — не отправлять.",
        "trello": "",
        "other": "Ответьте «нет» или «позже»; хотфикса и карточки по этому обращению нет.",
    }

    def send_reports(self) -> None:
        now = self.clock()
        ready = [
            t for t in self.store.tickets_in("report_ready")
            if now - float(self.store.data(t["id"]).get("ready_at", 0)) >= self.cfg.limits.batch_wait_sec
        ]
        if not ready:
            return
        hotfixes = [t for t in ready if self.store.data(t["id"]).get("hotfix_ok")]
        if len(hotfixes) >= 2:
            try:
                items = "\n".join(
                    f"Обращение {t['id']}: "
                    f"{self.store.data(t['id']).get('analysis', {}).get('proposed_solution', '')}; "
                    f"заденет: {self.store.data(t['id']).get('affected')}" for t in hotfixes
                )
                recon = self.llm.ask("analyst", prompts.reconcile_prompt(items),
                                     mode="readonly", cwd=self._analysis_cwd()).text.strip()
            except (LlmUnavailable, LlmError):
                recon = "Сверка хотфиксов между собой не проведена: модель недоступна."
            ids = ", ".join(str(t["id"]) for t in hotfixes)
            self.say_owner(f"reconcile:{ids}",
                           f"Порция: {len(ready)} обращений, из них хотфиксов {len(hotfixes)}. "
                           f"Сверка хотфиксов между собой ({ids}):\n{recon}", purpose="batch")
        for t in ready:
            d = self.store.data(t["id"])
            text = (
                f"Обращение №{t['id']} · Клиент: {self._client_label(t)}\n\n{d['report']['body']}"
            )
            footer = self.FOOTERS.get(d.get("verdict", "other"), "")
            if footer:
                text += f"\n\n{footer}"
            self.say_owner(f"report:{t['id']}", text, t["id"], "summary")
            final = "done" if d.get("verdict") in ("trello",) else "await_owner"
            self.store.set_stage(t["id"], final, reported_at=now)

    def _client_label(self, t: Any) -> str:
        d = self.store.data(t["id"])
        return str(d.get("form", {}).get("client_name") or t["seller"] or "—")

    # ===== команды владельца (R21) =====================================================
    def handle_owner_message(self, m: Any) -> None:
        awaiting_rows = self.store.tickets_in("await_owner", "postponed", "await_mockup")
        awaiting = [{"id": str(t["id"]), "title": self.title_of(t["id"]),
                     "kind": self.store.data(t["id"]).get("verdict", "")} for t in awaiting_rows]
        target = (
            self.store.ticket_for_tg_message(m["chat_id"], m["reply_to"]) if m["reply_to"] else None
        )
        parsed, _ = self.llm.ask_json(
            "filter", prompts.owner_command_prompt(m["text"], awaiting, target),
            system="Ты разбираешь короткие ответы владельца склада.",
        )
        self.store.set_message(m["id"], status="handled")
        intent = str(parsed.get("intent", "other"))
        if intent == "other":
            return
        valid = {t["id"] for t in awaiting_rows}
        ids = [int(i) for i in parsed.get("ticket_ids") or [] if isinstance(i, int) and i in valid]
        if target is not None and target in valid and not ids:
            ids = [target]
        if parsed.get("all"):
            ids = [t["id"] for t in awaiting_rows if self._fits(t, intent)]
        if not ids and len(awaiting_rows) == 1:
            ids = [awaiting_rows[0]["id"]]
        if intent == "unclear" or (intent in DECISION_INTENTS and not ids):
            options = "; ".join(f"№{a['id']} — {a['title']}" for a in awaiting) or "ничего нет"
            self.say_owner(f"clarify:{m['id']}",
                           f"Не понял, что именно и по какому обращению сделать. Ждут решения: "
                           f"{options}. Ответьте на нужную сводку словами «кати», «нет» или «позже».")
            return
        for tid in ids:
            self._apply_decision(tid, intent)

    def _fits(self, t: Any, intent: str) -> bool:
        if intent in ("mockup_yes", "mockup_no"):
            return bool(t["stage"] == "await_mockup")
        return bool(t["stage"] in ("await_owner", "postponed"))

    def _apply_decision(self, tid: int, intent: str) -> None:
        t, d = self.store.ticket(tid), self.store.data(tid)
        if intent in ("mockup_yes", "mockup_no"):
            if t["stage"] != "await_mockup":
                return
            self.store.set_stage(tid, "mockup" if intent == "mockup_yes" else "done")
            return
        if t["stage"] not in ("await_owner", "postponed"):
            return
        if intent == "reject":
            self.store.set_stage(tid, "rejected")
        elif intent == "postpone":
            self.store.set_stage(tid, "postponed")
        elif intent == "go":
            verdict = d.get("verdict")
            if verdict == "hotfix" and d.get("hotfix_ok"):
                self.store.set_stage(tid, "hotfix", hotfix={"step": "start"})
                self.say_owner(f"go:{tid}", f"Принято: по обращению №{tid} делаю хотфикс. "
                                            "Отчитаюсь, когда выложу.", tid)
            elif verdict == "bug_no_hotfix":
                self.say_owner(
                    f"nogo:{tid}",
                    f"По обращению №{tid} вердикт «нельзя коротким хотфиксом» "
                    f"({(d.get('analysis') or {}).get('hotfix', {}).get('reason', 'см. сводку')}). "
                    "В облегчённом режиме не делаю. Как поступить?", tid,
                )
            elif verdict == "info":
                answer = (d.get("analysis") or {}).get("info_answer")
                if answer and t["chat_id"]:
                    first = self.store.ticket_messages(tid)
                    self.say_client(f"t{tid}:info", t["chat_id"], str(answer),
                                    first[0]["msg_id"] if first else None, tid)
                self.store.set_stage(tid, "done")
            else:
                self.say_owner(f"noop:{tid}", f"По обращению №{tid} действий не требуется.", tid)

    # ===== хотфикс и макеты (R23-R27, R31) =============================================
    def stage_hotfix(self, tid: int) -> None:
        self.hotfix.step(tid)

    def stage_mockup(self, tid: int) -> None:
        self.mockups.run(tid)

    # ===== партнёрский чат (R28-R30) ===================================================
    def handle_partner_message(self, m: Any) -> None:
        self.store.set_message(m["id"], status="handled")
        waiting = [
            t for t in self.store.tickets_in("task_await_confirm")
            if t["chat_id"] == m["chat_id"] and t["author_id"] == m["author_id"]
        ]
        if waiting:
            tid = waiting[-1]["id"]
            d = self.store.data(tid)
            res, _ = self.llm.ask_json(
                "filter", prompts.partner_reply_prompt(self._task_text(d), m["text"])
            )
            intent = res.get("intent")
            if intent == "confirm":
                self.store.set_stage(tid, "task_create")
                return
            if intent == "edit":
                edits = list(d.get("edits", [])) + [str(res.get("edit") or m["text"])]
                self.store.set_stage(tid, "task_draft", edits=edits, version=int(d.get("version", 1)) + 1)
                return
        if not re.search(r"trello|трелло", m["text"], re.IGNORECASE):
            return
        res, _ = self.llm.ask_json("filter", prompts.partner_trigger_prompt(m["text"]))
        if res.get("is_task_request") is True:
            chat = self.cfg.telegram.chats[m["chat_id"]]
            self.store.add_ticket(
                kind="partner_task", source="telegram", chat_id=m["chat_id"], seller=chat.seller,
                stage="task_draft", author_id=m["author_id"], category="task", now=self.clock(),
                data={"raw": str(res.get("task") or m["text"]), "msg_id": m["msg_id"],
                      "author_name": m["author_name"], "version": 1, "edits": []},
            )

    def _task_text(self, d: dict[str, Any]) -> str:
        draft = d.get("draft") or {}
        return (f"{draft.get('title', '')}\nСуть: {draft.get('essence', '')}\n"
                f"Что должно получиться: {draft.get('expected', '')}\n"
                f"Что понял неочевидного: {'; '.join(draft.get('notes') or [])}")

    def stage_task_draft(self, tid: int) -> None:
        d = self.store.data(tid)
        draft, _ = self.llm.ask_json(
            "routine", prompts.partner_draft_prompt(d["raw"], list(d.get("edits", []))), ticket_id=tid
        )
        version = int(d.get("version", 1))
        t = self.store.ticket(tid)
        self.store.patch_data(tid, draft=draft)
        text = (
            f"Правильно ли я понял задачу?\n\n«{draft.get('title', '')}»\n"
            f"Суть: {draft.get('essence', '')}\nЧто должно получиться: {draft.get('expected', '')}\n"
            + ("Что понял неочевидного:\n" + "\n".join(f"- {n}" for n in draft.get("notes") or [])
               if draft.get("notes") else "")
            + "\n\nЕсли всё верно, ответьте «да». Если нет — напишите, что поправить."
        )
        self.say_client(f"t{tid}:draft:{version}", t["chat_id"], text, d.get("msg_id"), tid)
        self.store.set_stage(tid, "task_await_confirm")

    def stage_task_create(self, tid: int) -> None:
        d, t = self.store.data(tid), self.store.ticket(tid)
        draft = d.get("draft") or {}
        desc = (
            f"{self._task_text(d)}\n\nИсточник: партнёрский чат, {d.get('author_name', '')}, "
            f"{_fmt_ts(t['created_at'])} UTC"
        )
        res = ensure_card(
            self.store, self.trello, key=f"task:{tid}", ticket_id=tid,
            list_id=self.cfg.trello.partner_list_id, name=str(draft.get("title") or d["raw"][:80]),
            body=desc,  # метка «Клиент» не ставится
        )
        if res.status == "linked":
            question = ""
            stage = "done"
            if draft.get("is_ui"):
                question = (
                    "\n\nЗадача связана с интерфейсом. Нужен ли макет? "
                    "Ответьте «да» или «нет» на это сообщение."
                )
                stage = "await_mockup"
            self.store.set_stage(tid, stage, card_id=res.card_id, card_url=res.url,
                                 approved_description=desc)
            self.say_owner(
                f"task_in:{tid}",
                f"Задача внесена в Trello: {draft.get('title', '')}\n{res.url}{question}",
                tid, "task_notice",
            )
        elif res.status == "unknown":
            self.store.set_stage(tid, "failed")
            if self.store.kv_once(f"card_unknown:{tid}"):
                self.say_owner(f"card_unknown:{tid}",
                               f"Задачу «{draft.get('title', '')}» в Trello внести не удалось подтвердить: "
                               "ответ Trello потерян. Повторно не создаю, чтобы не было дубля. "
                               "Проверьте доску.", tid)
        else:
            self.store.set_stage(tid, "failed")
            self.say_owner(
                f"card_rej:{tid}",
                f"Trello отклонил создание карточки по задаче «{draft.get('title', '')}».", tid,
            )

    # ===== форма «?» (R4-R7) ===========================================================
    def poll_forms(self) -> None:
        """Опрос бэка; курсор хранится после сохранения записи (повтор не создаёт дубля)."""
        if not self.cfg.wms.agent_key:
            return
        cursor = self.store.kv_get("form_cursor")
        try:
            rows = self.wms.new_requests(cursor)
        except WmsError as exc:
            log.warning("form poll failed: %s", exc)
            return
        for row in rows:
            self.ingest_form(row)
            cursor = {"created_at": row["created_at"], "id": row["id"]}
            self.store.kv_set("form_cursor", cursor)

    def ingest_form(self, row: dict[str, Any]) -> int | None:
        text = " ".join(str(row.get(k) or "") for k in ("description", "screen", "problem", "proposal"))
        with self.store.lock:
            self.store.execute("BEGIN")
            try:
                mid = self.store.add_message(
                    source="form", chat_id=0, msg_id=row["id"], role="client", author_id="form",
                    author_name=row["client_name"], ts=self.clock(), kind="text", text=text,
                    file_id=None, reply_to=None,
                )
                tid = None
                if mid is not None:
                    tid = self.store.add_ticket(
                        kind="form", source="form", chat_id=None, seller=row["client_name"],
                        stage="form_new", category=None, now=self.clock(),
                        data={"form": row, "title": (row.get("title") or "")[:80],
                              "card_id": row.get("trello_card_id")},
                    )
                    self.store.set_message(mid, status="attached", ticket_id=tid)
                self.store.execute("COMMIT")
            except Exception:
                self.store.execute("ROLLBACK")
                raise
        return tid

    def sync_form_cards(self) -> None:
        """R5: карточку формы создаёт WMS-624; агент ждёт связь и добавляет один комментарий."""
        for t in self.store.rows("SELECT * FROM tickets WHERE kind='form' AND stage NOT IN "
                                 "('failed','closed','rejected')"):
            d = self.store.data(t["id"])
            if not d.get("report") and not d.get("analysis"):
                continue
            if d.get("commented"):
                continue
            if not d.get("card_id"):
                try:
                    fresh = self.wms.request(d["form"]["id"])
                except WmsError:
                    continue
                if not fresh.get("trello_card_id"):
                    continue
                d = self.store.patch_data(t["id"], card_id=fresh["trello_card_id"])
            self._comment_form_card(t["id"], d)

    def _comment_form_card(self, tid: int, d: dict[str, Any]) -> None:
        marker = f"WMS-AGENT-COMMENT: t{tid}"
        try:
            card = self.trello.get_card(d["card_id"])
            if f"WMS-REQUEST-ID: {d['form']['id']}" not in str(card.get("desc", "")).splitlines():
                return  # чужая или не та карточка: ничего не пишем
            if any(marker in c for c in self.trello.comments(d["card_id"])):
                self.store.patch_data(tid, commented=True)
                return
            a = d.get("analysis") or {}
            text = (
                f"Разбор агента-диспетчера.\nКатегория: {self.store.ticket(tid)['category']}. "
                f"Срочность: {'срочно' if d.get('urgent') else 'не срочно'}.\n"
                f"Что не работает: {'; '.join(a.get('problem_steps') or []) or '—'}\n"
                f"Решение: {a.get('proposed_solution', '—')}\n\n{marker}"
            )
            self.trello.add_comment(d["card_id"], text)
            self.store.patch_data(tid, commented=True)
        except TrelloError as exc:
            log.warning("form card comment failed: %s", exc.code)

    # ===== очистка ответа модели (используется тестами/отладкой) =======================
    @staticmethod
    def parse(text: str) -> dict[str, Any]:
        return extract_json(text)
