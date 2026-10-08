"""Telegram Bot API (long polling: у мака нет публичного адреса) и надёжная отправка (R35)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .case_journal import CaseJournal
from .config import Config
from .store import Store

log = logging.getLogger(__name__)
API = "https://api.telegram.org"
MAX_SEND_ATTEMPTS = 5
MAX_TEXT = 4096


class TelegramError(Exception):
    """outcome: 'rejected' — точно не доставлено; 'not_sent' — запрос не ушёл; 'unknown'."""

    def __init__(self, outcome: str, code: str = "") -> None:
        super().__init__(f"telegram_{outcome}:{code}")
        self.outcome = outcome
        self.code = code


class TelegramClient:
    def __init__(self, token: str, http: httpx.Client) -> None:
        self.token = token
        self.http = http

    def _call(
        self, method: str, payload: dict[str, Any], timeout: float = 30,
        files: dict[str, Any] | None = None,
    ) -> Any:
        try:
            url = f"{API}/bot{self.token}/{method}"
            if files is not None:
                response = self.http.post(url, data=payload, files=files, timeout=timeout)
            else:
                response = self.http.post(url, json=payload, timeout=timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise TelegramError("not_sent", "connect") from None
        except httpx.HTTPError as exc:  # токен в URL: текст исключения не пробрасываем
            raise TelegramError("unknown", type(exc).__name__) from None
        try:
            body = response.json()
        except ValueError:
            raise TelegramError("unknown", f"http_{response.status_code}") from None
        if response.status_code == 429:
            raise TelegramError("not_sent", "rate_limited")
        if response.status_code >= 500:
            raise TelegramError("unknown", f"http_{response.status_code}")
        if not body.get("ok"):
            if "message to delete not found" in str(body.get("description", "")).lower():
                raise TelegramError("rejected", "message_not_found")
            if "message is not modified" in str(body.get("description", "")).lower():
                raise TelegramError("rejected", "message_not_modified")
            raise TelegramError("rejected", f"http_{response.status_code}")
        return body["result"]

    def get_me(self) -> dict[str, Any]:
        result = self._call("getMe", {}, timeout=20)
        assert isinstance(result, dict)
        return result

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        result = self._call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": ["message", "edited_message"]},
            timeout=timeout + 15,
        )
        assert isinstance(result, list)
        return result

    def send_message(self, chat_id: int, text: str, reply_to: str | None = None) -> str:
        if len(text.encode("utf-16-le")) // 2 > MAX_TEXT:
            raise TelegramError("rejected", "too_long")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_to:
            payload["reply_to_message_id"] = int(reply_to)
            payload["allow_sending_without_reply"] = True
        return str(self._call("sendMessage", payload)["message_id"])

    def edit_message(self, chat_id: int, message_id: str, text: str) -> None:
        if len(text.encode("utf-16-le")) // 2 > MAX_TEXT:
            raise TelegramError("rejected", "too_long")
        try:
            self._call("editMessageText", {"chat_id": chat_id,
                       "message_id": int(message_id), "text": text})
        except TelegramError as exc:
            # Telegram rejects an identical edit. Treat only that exact error as success.
            if exc.code != "message_not_modified":
                raise

    def delete_message(self, chat_id: int, message_id: str) -> None:
        try:
            self._call("deleteMessage", {"chat_id": chat_id, "message_id": int(message_id)})
        except TelegramError as exc:
            if exc.code != "message_not_found":
                raise

    def send_document(
        self, chat_id: int, path: str, caption: str = "", reply_to: str | None = None
    ) -> str:
        payload: dict[str, Any] = {"chat_id": str(chat_id)}
        if caption:
            payload["caption"] = caption.encode("utf-16-le")[:2000].decode("utf-16-le", errors="ignore")
        if reply_to:
            payload["reply_to_message_id"] = reply_to
            payload["allow_sending_without_reply"] = "true"
        file = Path(path)
        result = self._call("sendDocument", payload, timeout=120,
                            files={"document": (file.name, file.read_bytes())})
        return str(result["message_id"])

    def download_file(self, file_id: str) -> bytes:
        info = self._call("getFile", {"file_id": file_id})
        try:
            response = self.http.get(f"{API}/file/bot{self.token}/{info['file_path']}", timeout=60)
        except httpx.HTTPError as exc:
            raise TelegramError("unknown", type(exc).__name__) from None
        if response.status_code != 200:
            raise TelegramError("rejected", f"http_{response.status_code}")
        return response.content


@dataclass
class Inbound:
    """Единый вид входящего сообщения из любого источника (R1)."""

    source: str  # telegram | form
    chat_id: int
    msg_id: str
    role: str  # client | partner | owner
    author_id: str
    author_name: str
    ts: float
    kind: str  # text | voice
    text: str
    file_id: str | None = None
    reply_to: str | None = None
    chat_title: str = ""
    caption: str = ""
    edited: bool = False
    edit_ts: float | None = None


# Команда владельца о привязке чата (WMS-641 R39). Чаты владельца чаще всего с ФУЛФИЛМЕНТАМИ (тенантами,
# внутри много селлеров), реже напрямую с селлером. Распознаётся мягко, ПОСЛЕ упоминания бота:
#   «@бот это фулфилмент <название>», «@бот это ФФ <название>», «@бот привяжи к ФФ/фулфилменту <название>»,
#   «@бот привяжи к ИП/селлеру <название>», «@бот это ИП/селлер <название>»,
#   «@бот привяжи к <название>» (= селлер).
# Без упоминания бота (текстом) команда игнорируется; голосом упоминания нет, там разбор без него.
MENTION_RE = re.compile(r"@\w+")
_TENANT_WORD = r"(?:фулфилмент\w*|ффо?)(?=\W|$)"
_SELLER_WORD = r"(?:ип|и\.\s?п\.|ip|индивидуальн\w+\s+предпринимател\w+|селлер\w*|продав\w+)(?=\W|$)"
_SEP = r"[\s:\u2013\u2014-]*"
_IS_RE = re.compile(
    rf"^(?:это|тут|здесь)\s+(?:чат\s+)?(?:(?:с|со|для)\s+)?(?:(?P<t>{_TENANT_WORD})|(?P<s>{_SELLER_WORD})){_SEP}(?P<name>.+)$",
    re.IGNORECASE | re.DOTALL)
_BIND_RE = re.compile(
    rf"^(?:пере)?привяж\w*\s+(?:(?:этот|данный|наш)\s+чат\s+)?(?:к|на)\s+"
    rf"(?:(?:(?P<t>{_TENANT_WORD})|(?P<s>{_SELLER_WORD})){_SEP})?(?P<name>.+)$",
    re.IGNORECASE | re.DOTALL)


def parse_bind_command(text: str, require_mention: bool = True) -> tuple[str, str] | None:
    """(«tenant»|«seller», название) или None. require_mention: текстовая команда должна содержать
    упоминание бота (@имя); голосовая расшифровка упоминания не содержит."""
    if require_mention and not MENTION_RE.search(text):
        return None
    body = " ".join(MENTION_RE.sub(" ", text).split()).lstrip(",:;–— ").strip()
    for pattern in (_IS_RE, _BIND_RE):
        match = pattern.match(body)
        if not match:
            continue
        name = " ".join(match.group("name").replace("«", " ").replace("»", " ").strip(" \"'.,!?;:").split())
        if len(name) < 2:
            return None
        return ("tenant" if match.group("t") else "seller"), name
    return None


def is_owner_task_chat_declaration(text: str) -> bool:
    """Явное назначение общего чата задач; права автора проверяет принимающий код."""
    if not MENTION_RE.search(text):
        return False
    body = " ".join(MENTION_RE.sub(" ", text).casefold().split()).strip(" .,!:;–—")
    return re.fullmatch(
        r"(?:(?:это|тут|здесь)\s+)?(?:(?:наш|этот|общий|рабочий)\s+)*чат\s+"
        r"(?:для\s+)?(?:задач\s+(?:от\s+)?(?:владельцев|собственников)\s+(?:системы|wms|вмс)"
        r"|(?:владельцев|собственников)\s+(?:системы|wms|вмс)\s+для\s+задач)", body,
    ) is not None


class Bots:
    """Два бота: приёма (intake) и владельца (owner). Один токен — один и тот же клиент."""

    def __init__(self, intake: Any, owner: Any, owner_chat_id: int = 0) -> None:
        self.intake, self.owner, self.owner_chat_id = intake, owner, owner_chat_id

    @property
    def single(self) -> bool:
        return self.intake is self.owner

    def named(self) -> dict[str, Any]:
        return {"intake": self.intake} if self.single else {"intake": self.intake, "owner": self.owner}

    def for_chat(self, chat_id: int) -> Any:
        """Сводки и уведомления только через бота владельца; клиентам и партнёру только через бота приёма."""
        return self.owner if chat_id == self.owner_chat_id and chat_id else self.intake

    def for_role(self, role: str) -> Any:
        return self.owner if role == "owner" else self.intake


def as_bots(tg: Any, owner_chat_id: int = 0) -> Bots:
    return tg if isinstance(tg, Bots) else Bots(tg, tg, owner_chat_id)


def normalize_update(update: dict[str, Any], cfg: Config, bot: str = "intake") -> Inbound | None:
    """Сообщение только из настроенных чатов (R2).

    Бот приёма принимает клиентские и партнёрский чаты; в них владелец обычный участник, команд он
    там не отдаёт. Команды владельца (R21) принимаются ТОЛЬКО ботом владельца, в его чате и только
    от owner_user_id. Если токен один (оба бота — один), действуют оба правила."""
    edited = isinstance(update.get("edited_message"), dict)
    message = update.get("edited_message") if edited else update.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from") or {}
    if sender.get("is_bot"):
        return None
    chat_id = int((message.get("chat") or {}).get("id", 0))
    owner_chat = cfg.telegram.owner_chat_id
    single = cfg.telegram.single_bot
    title = str((message.get("chat") or {}).get("title") or "")
    is_owner = bool(cfg.telegram.owner_user_id) and int(sender.get("id", 0)) == cfg.telegram.owner_user_id
    known = cfg.telegram.chats.get(chat_id)
    text_only = message.get("text") or message.get("caption") or ""
    if (
        is_owner and chat_id < 0 and chat_id != owner_chat and (bot != "owner" or single)
        and (known is None or known.role == "client" or is_owner_task_chat_declaration(text_only))
        and MENTION_RE.search(text_only) is not None
    ):
        # Возможная привязка чата (R39/R51): принимает только бот приёма и только от владельца.
        # Свободную формулировку после @упоминания разбирает модель; поиск и подтверждение делает код.
        reply = message.get("reply_to_message") or {}
        return Inbound(
            source="telegram", chat_id=chat_id, msg_id=str(message["message_id"]), role="bind",
            author_id=str(sender.get("id", "")), author_name="владелец", ts=float(message.get("date", 0)),
            kind="text", text=text_only, chat_title=title,
            reply_to=str(reply["message_id"]) if reply.get("message_id") else None,
            caption=str(message.get("caption") or ""),
            edited=edited, edit_ts=float(message.get("edit_date") or 0) or None,
        )
    if chat_id == owner_chat and chat_id:
        if bot != "owner" and not single:
            return None  # бот приёма в чате владельца ничего не принимает
        if int(sender.get("id", 0)) != cfg.telegram.owner_user_id:
            return None
        role = "owner"
    elif chat_id in cfg.telegram.chats:
        if bot == "owner" and not single:
            return None  # бот владельца клиентские и партнёрские чаты не читает
        role = cfg.telegram.chats[chat_id].role
    else:
        return None
    voice = message.get("voice") or message.get("audio") or message.get("video_note")
    photos = message.get("photo") or []
    attachment = ((photos[-1] if photos else None) or message.get("document")
                  or message.get("video") or message.get("sticker"))
    caption = str(message.get("caption") or "")
    plain_text = str(message.get("text") or "")
    if not voice and not attachment and not plain_text:
        return None
    if voice:
        kind, text, file_id = "voice", "", voice.get("file_id")
    elif attachment:
        kind = ("photo" if photos else "document" if message.get("document") else
                "video" if message.get("video") else "sticker")
        text, file_id = caption or f"({kind} без подписи)", attachment.get("file_id")
    else:
        kind, text, file_id = "text", plain_text, None
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or str(
        sender.get("username", "")
    )
    reply = message.get("reply_to_message") or {}
    return Inbound(
        source="telegram",
        chat_id=chat_id,
        msg_id=str(message["message_id"]),
        role=role,
        author_id=str(sender.get("id", "")),
        author_name=name,
        ts=float(message.get("date", 0)),
        kind=kind,
        text=text,
        file_id=file_id,
        reply_to=str(reply["message_id"]) if reply.get("message_id") else None,
        chat_title=title,
        caption=caption,
        edited=edited,
        edit_ts=float(message.get("edit_date") or 0) or None,
    )


def reconcile_case_delivery(journal: CaseJournal, store: Store, owner_bot: Any,
                            owner_chat_id: int, item: Any) -> None:
    """Project a confirmed outbox result to its card; the delivery key makes retries safe."""
    linked = native_delivery_case_link(store, owner_chat_id, item)
    if not linked:
        return
    delivered_key = f"delivered:{item['id']}"
    card = store.kv_get(f"case_card:{linked['topic_id']}", {})
    event_exists = any(event.get('key') == delivered_key for event in card.get('events', []))
    if event_exists:
        # The event and status are already durable, but the Telegram edit may have
        # returned unknown. Re-render the same card without reapplying its old status.
        journal.update_card(owner_bot, owner_chat_id, linked['topic_id'], linked['chat_id'])
        return
    kind = linked.get('kind', 'answer')
    if kind == 'owner_question':
        event = 'Вопрос владельцу отправлен: ' + item['text']
        statuses = {'owner_needed': True}
    elif kind == 'question':
        event = 'Уточнение отправлено клиенту: ' + item['text']
        statuses = {}
    else:
        event = 'Ответ отправлен клиенту: ' + item['text']
        statuses = {'answer_sent': True}
    journal.update_card(
        owner_bot, owner_chat_id, linked['topic_id'], linked['chat_id'],
        statuses=statuses, event=event, event_key=delivered_key,
    )


def native_delivery_case_link(store: Store, owner_chat_id: int, item: Any) -> dict[str, Any] | None:
    """Return a validated association for an explicit send; reject stale/cross-chat links."""
    key = str(item['key'])
    if not key.startswith('native-send:'):
        return None
    linked = store.kv_get(f"reply_case:{key}", {})
    if not isinstance(linked, dict) or not linked.get('topic_id'):
        return None
    try:
        case_chat_id = int(linked['chat_id'])
        destination_chat_id = int(item['chat_id'])
        topic_id = str(linked['topic_id'])
    except (KeyError, TypeError, ValueError):
        return None
    if linked.get('kind') not in (None, 'answer', 'question', 'owner_question'):
        return None
    card_key = f"case_card:{topic_id}"
    card = store.kv_get(card_key, {})
    if not isinstance(card, dict):
        return None
    try:
        if int(card.get('chat_id', 0)) != case_chat_id:
            return None
    except (TypeError, ValueError):
        return None
    destination = linked.get('destination_chat_id')
    try:
        if destination is not None and int(destination) != destination_chat_id:
            return None
    except (TypeError, ValueError):
        return None
    if destination_chat_id != owner_chat_id and destination_chat_id != int(card['chat_id']):
        return None
    return linked


def reconcile_unconfirmed_native_delivery(journal: CaseJournal, store: Store, owner_bot: Any,
                                          owner_chat_id: int, item: Any) -> None:
    """Record an interrupted explicit send without guessing or retrying its outcome."""
    linked = native_delivery_case_link(store, owner_chat_id, item)
    if not linked:
        return
    card = store.kv_get(f"case_card:{linked['topic_id']}", {})

    event_key = f"unconfirmed:{item['id']}"
    if any(event.get('key') == event_key for event in card.get('events', [])):
        journal.update_card(owner_bot, owner_chat_id, linked['topic_id'], linked['chat_id'])
        return
    kind = linked.get('kind', 'answer')
    if kind == 'owner_question':
        event = (
            'Вопрос владельцу не подтверждён как доставленный. Повторно не отправляю, '
            'чтобы не продублировать; проверьте основной личный Telegram-чат.'
        )
    elif kind == 'question':
        event = (
            'Уточнение клиенту не подтверждено как доставленное. Повторно не отправляю, '
            'чтобы не продублировать; проверьте исходный Telegram-чат клиента.'
        )
    else:
        event = (
            'Ответ клиенту не подтверждён как доставленный. Повторно не отправляю, '
            'чтобы не продублировать; проверьте исходный Telegram-чат клиента.'
        )
    status = CaseJournal._current_status(card)
    if status in {'answer_sent', 'analysis_done'}:
        status = 'working'
    journal.update_card(
        owner_bot, owner_chat_id, linked['topic_id'], linked['chat_id'],
        statuses={status: True}, event=event, event_key=event_key,
    )


def flush_outbox(store: Store, tg: Any, cfg: Config, *, only_ids: set[int] | None = None,
                 explicit_native_action: bool = False,
                 allow_scoped_client_replies: bool = False) -> int:
    """Отправляет намерения. Клиенту при неизвестном исходе НЕ повторяем (R35).

    Маршрут по чату: владельцу только ботом владельца, всем остальным только ботом приёма.
    only_ids: явный набор текущего действия; пустой набор не отправляет ничего."""
    bots = as_bots(tg, cfg.telegram.owner_chat_id)
    sent = 0
    for item in store.outbox_pending():
        # An explicit bridge action must never drain older queued messages.
        if only_ids is not None and int(item['id']) not in only_ids:
            continue
        explicit_send = (explicit_native_action and only_ids is not None
                         and item['key'].startswith('native-send:'))
        scoped_send = allow_scoped_client_replies and only_ids is not None
        if (item['chat_id'] != cfg.telegram.owner_chat_id and not explicit_send and not scoped_send
                and not getattr(cfg.agent, 'client_replies_enabled', False)):
            continue
        if not store.claim_outbox(item["id"]):
            continue
        tg = bots.for_chat(item["chat_id"])
        try:
            if item["file_path"]:
                message_id = tg.send_document(
                    item["chat_id"], item["file_path"], item["text"], item["reply_to"]
                )
            elif len(item["text"].encode("utf-16-le")) // 2 > MAX_TEXT:
                # Длинное служебное сообщение уходит целиком файлом, а не обрезанным текстом.
                folder = cfg.state_path / "outbox-long"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"message-{item['id']}.txt"
                path.write_text(item["text"], encoding="utf-8")
                message_id = tg.send_document(
                    item["chat_id"], str(path), item["text"][:900] + "…\n(полный текст в файле)",
                    item["reply_to"],
                )
            else:
                message_id = tg.send_message(item["chat_id"], item["text"], item["reply_to"])
        except TelegramError as exc:
            attempts = item["attempts"] + 1
            if exc.outcome == "rejected":
                store.finish_outbox(item["id"], "failed")
                log.warning("outbox %s rejected: %s", item["key"], exc.code)
            elif exc.outcome == "not_sent" and attempts < MAX_SEND_ATTEMPTS:
                store.execute("UPDATE outbox SET status='pending' WHERE id=?", (item["id"],))
            elif exc.outcome == "unknown" and item["repeat_ok"] and attempts < MAX_SEND_ATTEMPTS:
                store.execute("UPDATE outbox SET status='pending' WHERE id=?", (item["id"],))
            elif exc.outcome == "unknown":
                store.finish_outbox(item["id"], "unknown")
                _tell_owner_unconfirmed(store, cfg, item)
            else:
                store.finish_outbox(item["id"], "failed")
            continue
        store.finish_outbox(item["id"], "sent", message_id)
        if getattr(cfg.agent, 'visible_moderator', False) or explicit_send:
            journal = CaseJournal(store, getattr(cfg.agent, 'history_dir', '')
                                  or Path(cfg.repo) / 'var/support-conversations')
            journal.sync_chat(int(item['chat_id']))
            reconcile_case_delivery(journal, store, bots.owner, cfg.telegram.owner_chat_id, item)
        sent += 1
    return sent


def _tell_owner_unconfirmed(store: Store, cfg: Config, item: Any) -> None:
    store.queue_message(
        key=f"unconfirmed:{item['id']}",
        chat_id=cfg.telegram.owner_chat_id,
        text=(
            f"Отправка сообщения клиенту не подтверждена (обращение {item['ticket_id']}): "
            "связь оборвалась в момент отправки. Повторно я его не отправляю, "
            "чтобы не дублировать. Проверьте чат."
        ),
        purpose="owner_notice",
        repeat_ok=True,
    )


def recover_after_restart(store: Store, cfg: Config) -> None:
    for item in store.settle_interrupted_sends():
        _tell_owner_unconfirmed(store, cfg, item)
