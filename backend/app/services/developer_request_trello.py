"""Optional Trello transport. Never include provider bodies/URLs in diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from app.core.settings import Settings
from app.models.developer_request import DeveloperRequest


class TrelloError(Exception):
    def __init__(self, code: str, *, rejected: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.rejected = rejected


@dataclass(frozen=True)
class TrelloConfig:
    api_key: str = field(repr=False)
    token: str = field(repr=False)
    board_id: str
    lists: dict[str, str]
    client_label_id: str | None

    @classmethod
    def from_settings(cls, settings: Settings) -> TrelloConfig | None:
        values = (
            settings.trello_api_key,
            settings.trello_token,
            settings.trello_board_id,
            settings.trello_review_list_id,
            settings.trello_queued_list_id,
            settings.trello_in_progress_list_id,
            settings.trello_completed_list_id,
        )
        if not all(values):
            return None
        key, token, board, review, queued, progress, completed = values
        assert key and token and board and review and queued and progress and completed
        lists = {
            review: "review",
            queued: "queued",
            progress: "in_progress",
            completed: "completed",
        }
        if len(lists) != 4:
            return None
        return cls(key, token, board, lists, settings.trello_client_label_id)

    @property
    def review_list_id(self) -> str:
        return next(key for key, value in self.lists.items() if value == "review")


def marker(request: DeveloperRequest) -> str:
    return f"WMS-REQUEST-ID: {request.id}"


def card_payload(request: DeveloperRequest, config: TrelloConfig) -> dict[str, str]:
    detail = (
        f"Описание ошибки:\n{request.description}"
        if request.type == "bug"
        else f"Экран / процесс:\n{request.screen}\n\nВ чём сейчас проблема:\n{request.problem}"
        f"\n\nКак можно улучшить:\n{request.proposal}"
    )
    payload = {
        "idList": config.review_list_id,
        "name": f"Клиент: {request.client_name} — {request.title}",
        "desc": (
            f"Клиент: {request.client_name}\nДата поступления: {request.created_at.isoformat()}"
            f"\nТип: {'Ошибка' if request.type == 'bug' else 'Улучшение / доработка'}"
            f"\n\n{detail}\n\nИсходный экран: {request.page_url or '—'}"
            f"\n\n{marker(request)}"
        ),
    }
    if config.client_label_id:
        payload["idLabels"] = config.client_label_id
    return payload


class TrelloClient:
    def __init__(self, config: TrelloConfig, http: httpx.AsyncClient) -> None:
        self.config = config
        self.http = http

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> Any:
        # OAuth header keeps secrets out of URL access logs. No automatic POST retries.
        auth = (
            f'OAuth oauth_consumer_key="{quote(self.config.api_key, safe="")}", '
            f'oauth_token="{quote(self.config.token, safe="")}"'
        )
        try:
            response = await self.http.request(
                method,
                f"https://api.trello.com/1/{path}",
                params=params,
                data=data,
                headers={"Authorization": auth},
                timeout=20,
            )
        except httpx.HTTPError:
            raise TrelloError("trello_transport_error") from None
        if response.status_code >= 400:
            raise TrelloError(
                f"trello_http_{response.status_code}",
                rejected=400 <= response.status_code < 500,
            )
        if response.status_code >= 300:
            raise TrelloError("trello_unexpected_redirect")
        try:
            return response.json()
        except ValueError:
            raise TrelloError("trello_invalid_response") from None

    async def check_board(self) -> None:
        board = await self._request(
            "GET",
            f"boards/{quote(self.config.board_id, safe='')}",
            params={"fields": "prefs,closed"},
        )
        if (
            not isinstance(board, dict)
            or board.get("closed") is not False
            or not isinstance(board.get("prefs"), dict)
            or board["prefs"].get("permissionLevel") != "private"
        ):
            raise TrelloError("trello_board_must_be_private")
        lists = await self._request(
            "GET",
            f"boards/{quote(self.config.board_id, safe='')}/lists",
            params={"filter": "open", "fields": "id"},
        )
        if not isinstance(lists, list) or not set(self.config.lists).issubset(
            {item.get("id") for item in lists if isinstance(item, dict)}
        ):
            raise TrelloError("trello_list_config_invalid")

    def _card(self, value: Any) -> dict[str, Any]:
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("id"), str)
            or not value["id"]
            or not isinstance(value.get("idList"), str)
            or value.get("idBoard") != self.config.board_id
        ):
            raise TrelloError("trello_invalid_card")
        return value

    async def create_card(self, request: DeveloperRequest) -> dict[str, Any]:
        value = await self._request("POST", "cards", data=card_payload(request, self.config))
        return self._card(value)

    async def get_card(self, card_id: str) -> dict[str, Any]:
        return self._card(
            await self._request(
                "GET",
                f"cards/{quote(card_id, safe='')}",
                params={"fields": "id,idList,idBoard,desc"},
            )
        )

    async def find_card(self, request: DeveloperRequest) -> dict[str, Any] | None:
        # Include archived cards. No match NEVER authorizes another create after ambiguity.
        cards = await self._request(
            "GET",
            f"boards/{quote(self.config.board_id, safe='')}/cards",
            params={"filter": "all", "fields": "id,idList,idBoard,desc"},
        )
        if not isinstance(cards, list):
            raise TrelloError("trello_invalid_response")
        matches = [
            card
            for card in cards
            if isinstance(card, dict)
            and isinstance(card.get("desc"), str)
            and marker(request) in card["desc"].splitlines()
        ]
        if len(matches) > 1:
            raise TrelloError("trello_duplicate_marker")
        return self._card(matches[0]) if matches else None
