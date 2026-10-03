"""One stable description for admission validation and subsequent Trello delivery."""

from __future__ import annotations

from datetime import UTC

from app.models.developer_request import DeveloperRequest

TRELLO_DESCRIPTION_MAX_LENGTH = 16384


def marker(request: DeveloperRequest) -> str:
    return f"WMS-REQUEST-ID: {request.id}"


def card_description(request: DeveloperRequest) -> str:
    detail = (
        f"Описание ошибки:\n{request.description}"
        if request.type == "bug"
        else f"Экран / процесс:\n{request.screen}\n\nВ чём сейчас проблема:\n{request.problem}"
        f"\n\nКак можно улучшить:\n{request.proposal}"
    )
    created_at = request.created_at
    if created_at.tzinfo is None:  # SQLite reads persisted UTC without timezone metadata.
        created_at = created_at.replace(tzinfo=UTC)
    timestamp = created_at.astimezone(UTC).isoformat(timespec="microseconds")
    return (
        f"Клиент: {request.client_name}\nДата поступления: {timestamp}"
        f"\nТип: {'Ошибка' if request.type == 'bug' else 'Улучшение / доработка'}"
        f"\n\n{detail}\n\nИсходный экран: {request.page_url or '—'}"
        f"\n\n{marker(request)}"
    )


def description_length(value: str) -> int:
    # Conservative JavaScript-compatible quota: astral characters use two UTF-16
    # code units. Never admit content whose JS string length exceeds Trello's cap.
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2
