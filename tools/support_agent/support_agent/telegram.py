"""Telegram Bot API (long polling: у мака нет публичного адреса) и надёжная отправка (R35)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Config
from .store import Store

log = logging.getLogger(__name__)
API = "https://api.telegram.org"
MAX_SEND_ATTEMPTS = 5


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

    def _call(self, method: str, payload: dict[str, Any], timeout: float = 30) -> Any:
        try:
            response = self.http.post(f"{API}/bot{self.token}/{method}", json=payload, timeout=timeout)
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
            raise TelegramError("rejected", f"http_{response.status_code}")
        return body["result"]

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        result = self._call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
            timeout=timeout + 15,
        )
        assert isinstance(result, list)
        return result

    def send_message(self, chat_id: int, text: str, reply_to: str | None = None) -> str:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000]}
        if reply_to:
            payload["reply_to_message_id"] = int(reply_to)
            payload["allow_sending_without_reply"] = True
        return str(self._call("sendMessage", payload)["message_id"])

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


def normalize_update(update: dict[str, Any], cfg: Config) -> Inbound | None:
    """Сообщение только из настроенных чатов (R2); команды владельца — только от него (R21)."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from") or {}
    if sender.get("is_bot"):
        return None
    chat_id = int((message.get("chat") or {}).get("id", 0))
    if chat_id == cfg.telegram.owner_chat_id and chat_id:
        if int(sender.get("id", 0)) != cfg.telegram.owner_user_id:
            return None
        role = "owner"
    elif chat_id in cfg.telegram.chats:
        role = cfg.telegram.chats[chat_id].role
    else:
        return None
    voice = message.get("voice") or message.get("audio") or message.get("video_note")
    text = message.get("text") or message.get("caption") or ""
    if not voice and not text:
        return None
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
        kind="voice" if voice and not text else "text",
        text=text,
        file_id=voice.get("file_id") if voice and not text else None,
        reply_to=str(reply["message_id"]) if reply.get("message_id") else None,
    )


def flush_outbox(store: Store, tg: TelegramClient, cfg: Config) -> int:
    """Отправляет намерения. Клиенту при неизвестном исходе НЕ повторяем (R35)."""
    sent = 0
    for item in store.outbox_pending():
        if not store.claim_outbox(item["id"]):
            continue
        try:
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
