"""Pydantic response shapes for the read-only seller billing report."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class SellerReportPhysicalTotals(BaseModel):
    operation_count: int
    item_quantity: int
    not_billable_count: int
    # Сколько штук товара прошло через каждый участок за период. Значения по
    # умолчанию — ради старых ответов, собранных до появления этих полей.
    inbound_items: int = 0
    packing_items: int = 0
    outbound_items: int = 0
    fbs_items: int = 0


class SellerReportFinancialTotals(SellerReportPhysicalTotals):
    unpriced_count: int
    gross_total_kopecks: int
    reversal_total_kopecks: int
    net_total_kopecks: int


class SellerReportSummaryRow(SellerReportPhysicalTotals):
    seller_id: str
    seller_name: str
    details_target: str


class SellerReportFinancialSummaryRow(SellerReportSummaryRow, SellerReportFinancialTotals):
    pass


class SellerReportPhysicalTotalsOut(SellerReportPhysicalTotals):
    seller_count: int


class SellerReportFinancialTotalsOut(SellerReportFinancialTotals):
    seller_count: int


class SellerReportPhysicalSummaryOut(BaseModel):
    rows: list[SellerReportSummaryRow]
    totals: SellerReportPhysicalTotalsOut


class SellerReportFinancialSummaryOut(BaseModel):
    rows: list[SellerReportFinancialSummaryRow]
    totals: SellerReportFinancialTotalsOut


class SellerReportEntryBaseOut(BaseModel):
    id: str
    kind: Literal["operation_fact", "legacy_billing", "fbs_order_handed"]
    occurred_at: str
    service_code: str
    item_quantity: int | None
    source_type: str
    source_id: str
    source_target: dict[str, str] | None
    document_number: str | None
    product_name: str | None
    sku: str | None
    # Только у заказов FBS: «ВБ получил» или «Передан ВБ».
    fbs_status_label: str | None = None


class SellerReportPhysicalEntryOut(SellerReportEntryBaseOut):
    result: Literal["completed", "reversed", "not_billable"]


class SellerReportFinancialOperationFactEntryOut(SellerReportEntryBaseOut):
    kind: Literal["operation_fact"]
    result: Literal["completed", "reversed", "not_billable", "unpriced"]
    rate_kopecks: int | None
    amount_kopecks: int | None
    unit: str | None
    invoice_history: dict[str, Any]


class SellerReportFinancialHandedFbsEntryOut(SellerReportEntryBaseOut):
    """Заказ FBS, переданный в WB, но ещё не подтверждённый: денег по нему нет."""

    kind: Literal["fbs_order_handed"]
    result: Literal["not_billable"]


class SellerReportFinancialLegacyEntryOut(SellerReportEntryBaseOut):
    kind: Literal["legacy_billing"]
    result: Literal["completed", "reversed", "not_billable", "unpriced"]
    rate_kopecks: int | None
    amount_kopecks: int | None
    unit: str | None
    invoice_history: dict[str, Any]
    billing_ledger_entry_id: str


class SellerReportStorageOut(BaseModel):
    kind: Literal["storage"]
    date_from: str
    date_to: str
    liter_days: float
    status: Literal["calculated", "missing_dimensions"]
    calculation_token: str


class SellerReportFinancialStorageOut(SellerReportStorageOut):
    amount_kopecks: int | None = None


class SellerReportPhysicalDetailsOut(BaseModel):
    seller_id: str
    seller_name: str
    entries: list[SellerReportPhysicalEntryOut]
    next_cursor: str | None
    storage_row: SellerReportStorageOut | None
    totals: SellerReportPhysicalTotals


class SellerReportFinancialDetailsOut(BaseModel):
    seller_id: str
    seller_name: str
    entries: list[
        SellerReportFinancialOperationFactEntryOut
        | SellerReportFinancialLegacyEntryOut
        | SellerReportFinancialHandedFbsEntryOut
    ]
    next_cursor: str | None
    storage_row: SellerReportFinancialStorageOut | None
    totals: SellerReportFinancialTotals
