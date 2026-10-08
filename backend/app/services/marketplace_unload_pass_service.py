"""Пропуск на машину отгрузки FBO (WMS-686): сведения о водителе и машине.

Одна машина на отгрузку. Сведения хранятся в marketplace_unload_requests.pass_details
(JSON) и правятся до проведения отгрузки. Пропуск ничего не блокирует: ни «Завершить»,
ни подбор, ни упаковку. Ни одной внешней системы здесь не вызывается.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from openpyxl import Workbook  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.services.marketplace_unload_status import STATUS_CANCELLED, STATUS_SHIPPED
from app.services.marketplace_unload_wb_fbw_export_service import stable_xlsx

SHEET_TITLE = "Пропуск"
_CARGO_TYPE_LABELS = {"box": "Короб", "pallet": "Паллета"}

#: Заголовки и порядок столбцов файла «Пропуск». Правится здесь же, рядом со схемой.
XLSX_HEADERS = (
    "Отгрузка",
    "Фамилия водителя",
    "Имя водителя",
    "Телефон",
    "Марка и модель автомобиля",
    "Госномер",
    "Тип грузомест",
    "Количество грузомест",
    "Плановая дата приезда",
)


class MarketplaceUnloadPassError(Exception):
    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        # Для pass_field_required — имя незаполненного обязательного поля.
        self.field = field
        super().__init__(code)


#: Обязательные для сохранения поля. Проверяются в save_pass, чтобы отказ был
#: понятным кодом pass_field_required с именем поля, а не общей ошибкой схемы.
REQUIRED_FIELDS = ("driver_last_name", "driver_first_name", "car_brand", "car_number")


class MarketplaceUnloadPassDetails(BaseModel):
    """Единая схема пропуска для WB и Ozon. Набор полей правится только здесь."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    driver_last_name: str | None = Field(default=None, max_length=100)
    driver_first_name: str | None = Field(default=None, max_length=100)
    # Для Ozon телефон обязателен — это проверяется при сохранении, когда известна
    # площадка отгрузки; для WB поле необязательное.
    driver_phone: str | None = Field(default=None, max_length=32)
    car_brand: str | None = Field(default=None, max_length=100)
    # Госномер хранится так, как введён, без какой-либо нормализации.
    car_number: str | None = Field(default=None, max_length=16)
    cargo_type: Literal["box", "pallet"] | None = None
    cargo_places_count: int | None = Field(default=None, ge=1, le=100_000)
    arrival_date: date | None = None

    @field_validator(
        "driver_last_name", "driver_first_name", "driver_phone", "car_brand", "car_number"
    )
    @classmethod
    def _blank_is_missing(cls, value: str | None) -> str | None:
        return value or None

    def first_missing_required(self) -> str | None:
        for name in REQUIRED_FIELDS:
            if getattr(self, name) is None:
                return name
        return None


class MarketplaceUnloadPassBody(BaseModel):
    """Тело PUT: объект пропуска целиком заменяет сохранённый."""

    model_config = ConfigDict(extra="forbid")

    pass_details: MarketplaceUnloadPassDetails


def is_editable(req: MarketplaceUnloadRequest) -> bool:
    """Править сведения можно, пока отгрузка не проведена и не отменена."""
    return req.status not in (STATUS_SHIPPED, STATUS_CANCELLED)


async def save_pass(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    details: MarketplaceUnloadPassDetails,
) -> MarketplaceUnloadRequest:
    """Сохранить сведения целиком (PUT). Документ читается под замком, статус свежий."""
    req = await session.scalar(
        select(MarketplaceUnloadRequest)
        .where(
            MarketplaceUnloadRequest.id == request_id,
            MarketplaceUnloadRequest.tenant_id == tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if req is None:
        raise MarketplaceUnloadPassError("not_found")
    if not is_editable(req):
        raise MarketplaceUnloadPassError("pass_not_editable")
    missing = details.first_missing_required()
    if missing is not None:
        raise MarketplaceUnloadPassError("pass_field_required", missing)
    if req.marketplace == "ozon" and details.driver_phone is None:
        raise MarketplaceUnloadPassError("pass_phone_required")
    # Новый словарь, а не правка на месте: JSON-колонка так замечает изменение.
    req.pass_details = details.model_dump(mode="json")
    await session.commit()
    return req


def _text_cell(sheet: Any, row: int, column: int, value: str | None) -> None:
    cell = sheet.cell(row, column, value)
    # Строка, начинающаяся с «=», не должна стать формулой; телефон и госномер
    # остаются текстом без потери плюса и ведущих нулей.
    cell.data_type = "s"
    cell.number_format = "@"


def pass_number(req: MarketplaceUnloadRequest) -> str:
    """Номер отгрузки для файла пропуска: тот же, что виден в списке отгрузок."""
    return req.document_number or req.display_number or str(req.id)


def build_pass_xlsx(req: MarketplaceUnloadRequest) -> bytes:
    """Файл «Пропуск»: один лист, шапка и одна строка с сохранёнными значениями."""
    raw = req.pass_details
    if not raw:
        raise MarketplaceUnloadPassError("pass_not_filled")
    number = pass_number(req)
    cargo_type = raw.get("cargo_type")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_TITLE
    # Фиксированные даты: повторное скачивание тех же данных даёт тот же файл.
    workbook.properties.created = datetime(2000, 1, 1)
    workbook.properties.modified = datetime(2000, 1, 1)
    sheet.append(XLSX_HEADERS)
    values: list[str | int | None] = [
        number,
        raw.get("driver_last_name"),
        raw.get("driver_first_name"),
        raw.get("driver_phone"),
        raw.get("car_brand"),
        raw.get("car_number"),
        _CARGO_TYPE_LABELS.get(str(cargo_type)) if cargo_type else None,
        raw.get("cargo_places_count"),
        raw.get("arrival_date"),
    ]
    for column, value in enumerate(values, start=1):
        if isinstance(value, int) and not isinstance(value, bool):
            sheet.cell(2, column, value)
        else:
            _text_cell(sheet, 2, column, None if value is None else str(value))
    return stable_xlsx(workbook)
