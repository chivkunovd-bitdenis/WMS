"""Shared Wildberries client exceptions."""

from __future__ import annotations

from dataclasses import dataclass


class WildberriesClientError(Exception):
    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MetaValidationFailItem:
    order_id: int | None
    key: str
    value: str | None
    decision: str
    reason: str | None = None


class WildberriesBusinessError(WildberriesClientError):
    """409 and other parsed WB business rejections (safe codes, no token leakage)."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        wb_code: str | None = None,
        message: str | None = None,
        meta_validation: list[MetaValidationFailItem] | None = None,
    ) -> None:
        super().__init__(code, status_code=status_code)
        self.wb_code = wb_code
        self.message = message
        self.meta_validation: tuple[MetaValidationFailItem, ...] = tuple(
            meta_validation or ()
        )
