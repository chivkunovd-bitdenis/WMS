"""Shared typed failures and binary decoding for the Ozon FBS process."""

from __future__ import annotations

import base64


class OzonFbsProcessError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(code)


def decode_file(value: str | None) -> bytes | None:
    if not value:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise OzonFbsProcessError(
            "ozon_invalid_file", "Ozon вернул повреждённый печатный файл."
        ) from exc
