from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ManualInvoiceV2LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    amount: str
    unit_price: str | None = None


class ManualInvoiceV2DraftIn(BaseModel):
    creation_mode: Literal["manual"]
    seller_id: uuid.UUID
    lines: list[ManualInvoiceV2LineIn] = Field(min_length=1, max_length=10)


class SelectedOperationsInvoiceV2DraftIn(BaseModel):
    creation_mode: Literal["selected_operations"]
    seller_id: uuid.UUID
    date_from: date
    date_to: date
    # Пустой список допустим, когда выбрана только строка хранения. Отказ на
    # «не выбрано вообще ничего» даёт сервис: он видит обе части сразу.
    selected_root_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    # Хранение берётся из ночных начислений за период, пересчёта больше нет.
    include_storage: bool = False


InvoiceV2DraftRequest = Annotated[
    ManualInvoiceV2DraftIn | SelectedOperationsInvoiceV2DraftIn,
    Field(discriminator="creation_mode"),
]


class InvoiceV2LineOut(BaseModel):
    id: uuid.UUID
    description: str
    unit_price_kopecks: int | None
    total_amount_kopecks: int
    sort_order: int


class InvoiceV2Out(BaseModel):
    id: uuid.UUID
    seller_id: uuid.UUID
    number: str
    creation_mode: Literal["manual", "selected_operations"]
    period_start: date | None
    period_end: date | None
    status: Literal["issued", "cancelled"]
    issued_at: datetime | None
    total_amount_kopecks: int
    ff_profile: dict[str, str | None]
    seller_profile: dict[str, str | None]
    lines: list[InvoiceV2LineOut]


class InvoiceHistoryItemOut(BaseModel):
    """Строка вкладки «Выставленные счета»: и старые месячные, и новые.

    `origin` говорит экрану, за какой карточкой идти при «Открыть»: legacy
    лежит в `/billing/invoices/{id}`, новый — в `/billing/invoices-v2/{id}`.
    """

    id: uuid.UUID
    origin: Literal["legacy", "v2"]
    number: str
    seller_id: uuid.UUID
    seller_name: str
    issued_at: datetime
    period_start: date | None
    period_end: date | None
    creation_mode: Literal["monthly", "manual", "selected_operations"]
    status: Literal["issued", "cancelled"]
    total_amount_kopecks: int


class InvoiceHistoryOut(BaseModel):
    invoices: list[InvoiceHistoryItemOut]
    next_cursor: str | None = None


class InvoiceV2ListOut(BaseModel):
    invoices: list[InvoiceV2Out]
    next_cursor: str | None = None
