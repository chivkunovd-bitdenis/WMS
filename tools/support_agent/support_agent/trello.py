"""Trello: карточки агента с маркером WMS-AGENT-ID; не создаём повторно при неизвестном исходе."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from .config import TrelloCfg
from .store import Store

log = logging.getLogger(__name__)
API = "https://api.trello.com/1"


class TrelloError(Exception):
    def __init__(self, code: str, *, rejected: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.rejected = rejected


def agent_marker(key: str) -> str:
    return f"WMS-AGENT-ID: {key}"


class TrelloClient:
    def __init__(
        self, cfg: TrelloCfg, http: httpx.Client, redact: Callable[[str], str] = lambda t: t
    ) -> None:
        self.cfg = cfg
        self.http = http
        self.redact = redact  # маскировка секретов во всём, что уходит в Trello

    def _request(
        self, method: str, path: str, *, params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> Any:
        auth = {"key": self.cfg.api_key, "token": self.cfg.token}
        try:
            response = self.http.request(
                method, f"{API}/{path}", params={**(params or {}), **auth}, data=data, timeout=20
            )
        except httpx.HTTPError as exc:  # ключ в адресе: текст исключения не пробрасываем
            raise TrelloError(f"transport_{type(exc).__name__}") from None
        if response.status_code >= 400:
            raise TrelloError(
                f"http_{response.status_code}", rejected=400 <= response.status_code < 500
            )
        try:
            return response.json()
        except ValueError:
            raise TrelloError("invalid_response") from None

    def create_card(self, *, list_id: str, name: str, desc: str, label_id: str = "") -> dict[str, Any]:
        data = {"idList": list_id, "name": self.redact(name)[:200], "desc": self.redact(desc)[:16000]}
        if label_id:
            data["idLabels"] = label_id
        card = self._request("POST", "cards", data=data)
        if not isinstance(card, dict) or not card.get("id"):
            raise TrelloError("invalid_card")
        return card

    def find_by_marker(self, marker: str) -> dict[str, Any] | None:
        """Все карточки доски, включая архивные; несколько совпадений — ошибка, не выбор."""
        params = {"filter": "all", "fields": "id,idList,desc,shortUrl", "limit": "1000"}
        match: dict[str, Any] | None = None
        seen: set[str] = set()
        while True:
            cards = self._request("GET", f"boards/{self.cfg.board_id}/cards", params=params)
            if not isinstance(cards, list):
                raise TrelloError("invalid_response")
            for card in cards:
                if marker in str(card.get("desc", "")).splitlines():
                    if match is not None and match["id"] != card["id"]:
                        raise TrelloError("duplicate_marker")
                    match = card
            if len(cards) < 1000:
                return match
            cursor = cards[-1]["id"]
            if cursor in seen:
                raise TrelloError("paging_not_advancing")
            seen.add(cursor)
            params["before"] = cursor

    def get_card(self, card_id: str) -> dict[str, Any]:
        card = self._request("GET", f"cards/{card_id}", params={"fields": "id,idList,desc,shortUrl"})
        if not isinstance(card, dict) or not card.get("id"):
            raise TrelloError("invalid_card")
        return card

    def comments(self, card_id: str) -> list[str]:
        actions = self._request(
            "GET", f"cards/{card_id}/actions", params={"filter": "commentCard", "limit": "1000"}
        )
        return [str(a.get("data", {}).get("text", "")) for a in actions]

    def add_comment(self, card_id: str, text: str) -> None:
        self._request("POST", f"cards/{card_id}/actions/comments", data={"text": self.redact(text)[:16000]})

    def move_card(self, card_id: str, list_id: str) -> None:
        self._request("PUT", f"cards/{card_id}", data={"idList": list_id})

    def update_description(self, card_id: str, desc: str) -> None:
        self._request("PUT", f"cards/{card_id}", data={"desc": self.redact(desc)})


def ensure_card_update(store: Store, trello: TrelloClient, *, key: str, operation: str,
                       addition: str) -> CardResult:
    """Добавляет уточнение к существующей карточке, сохраняя чужой текст и проверяя неизвестный исход."""
    row = store.card(key)
    if row is None or row["status"] != "linked":
        return CardResult("unknown")
    marker, update_marker = agent_marker(key), f"WMS-AGENT-UPDATE: {operation}"
    state_key = f"trello_update:{operation}"
    state = store.kv_get(state_key)
    try:
        card = trello.get_card(row["card_id"])
    except TrelloError:
        return CardResult("unknown")
    text = str(card.get("desc") or "")
    if card.get("id") != row["card_id"] or marker not in text.splitlines():
        return CardResult("rejected")
    if update_marker in text.splitlines():
        store.kv_set(state_key, {"status": "confirmed"})
        return CardResult("linked", row["card_id"], card.get("shortUrl") or row["url"])
    if state and state.get("status") in ("sending", "unknown", "confirmed"):
        return CardResult("unknown")  # исход пока не выяснен: повторного внешнего действия нет
    desc = text + f"\n\n{addition}\n{update_marker}"
    if len(desc) > 16000:
        return CardResult("rejected")  # не обрезаем прежнее описание или новое уточнение
    store.kv_set(state_key, {"status": "sending"})
    try:
        trello.update_description(row["card_id"], desc)
    except TrelloError as exc:
        store.kv_set(state_key, {"status": "rejected" if exc.rejected else "unknown"})
        return CardResult("rejected" if exc.rejected else "unknown")
    # Проверка фактического результата нужна и после успешного HTTP-ответа.
    return ensure_card_update(store, trello, key=key, operation=operation, addition=addition)


@dataclass
class CardResult:
    status: str  # linked | unknown | rejected
    card_id: str | None = None
    url: str | None = None


def ensure_card(
    store: Store,
    trello: TrelloClient,
    *,
    key: str,
    ticket_id: int | None,
    list_id: str,
    name: str,
    body: str,
    label_id: str = "",
) -> CardResult:
    """Ровно одна карточка на key (R18, R30, R35).

    Перед запросом записывается намерение ('creating'). Если ответ потерян или процесс убит,
    результат выясняется чтением доски по маркеру; пока он не выяснен, новая карточка не
    создаётся (как в WMS-624: отсутствие маркера не разрешает повторное создание).
    """
    marker = agent_marker(key)
    row = store.card(key)
    if row is not None and row["status"] == "linked":
        return CardResult("linked", row["card_id"], row["url"])
    if row is not None and row["status"] in ("creating", "unknown"):
        try:
            found = trello.find_by_marker(marker)
        except TrelloError:
            return CardResult("unknown")
        if found is None:
            store.set_card(key, ticket_id=ticket_id, marker=marker, status="unknown")
            return CardResult("unknown")
        store.set_card(
            key, ticket_id=ticket_id, marker=marker, status="linked",
            card_id=found["id"], url=found.get("shortUrl"),
        )
        return CardResult("linked", found["id"], found.get("shortUrl"))
    store.set_card(key, ticket_id=ticket_id, marker=marker, status="creating")
    try:
        card = trello.create_card(
            list_id=list_id, name=name, desc=f"{body}\n\n{marker}", label_id=label_id
        )
    except TrelloError as exc:
        if exc.rejected:  # явный отказ 4xx: точно не создано
            store.execute("DELETE FROM cards WHERE key=?", (key,))
            return CardResult("rejected")
        store.set_card(key, ticket_id=ticket_id, marker=marker, status="unknown")
        return ensure_card(store, trello, key=key, ticket_id=ticket_id, list_id=list_id,
                           name=name, body=body, label_id=label_id)
    store.set_card(
        key, ticket_id=ticket_id, marker=marker, status="linked",
        card_id=card["id"], url=card.get("shortUrl"),
    )
    return CardResult("linked", card["id"], card.get("shortUrl"))
