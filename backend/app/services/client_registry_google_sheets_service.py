"""WMS-515: one-way client-register export to a single Google Sheet.

The Sheet is intentionally the source of truth for its manual values.  This
module only writes columns A:F and only inserts a new client immediately before
the expense divider, so Google never receives a destructive rewrite of G:I or
the expense rows below the register.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.document_event import SOURCE_USER, DocumentEvent
from app.models.fbs_order_pick import FbsOrderPick, FbsOrderPickEvent
from app.models.inventory_count import InventoryCount
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCodeEvent
from app.models.packaging_task import PackagingTaskEvent
from app.models.tenant import Tenant
from app.models.user import User

MOSCOW = ZoneInfo("Europe/Moscow")
SHEET_TITLE = "Клиенты"
CLIENT_HEADER_ROW = 6
FIRST_CLIENT_ROW = CLIENT_HEADER_ROW + 1
CLIENT_HEADERS = [
    "ID клиента",
    "Фулфилмент",
    "Дата регистрации",
    "Последняя активность",
    "Доступ",
    "Оплачено до",
    "Дата оплаты",
    "Сумма, ₽",
    "Следующая оплата",
]
LEGACY_CLIENT_HEADERS = [
    "tenant_id",
    "FF",
    "Дата регистрации",
    "Последняя активность",
    "Доступ",
    "Оплачено до",
    "Дата платежа",
    "Сумма, ₽",
    "Следующий платёж",
]
EXPENSES_MARKER = "Расходы"
EXPENSES_HEADERS = ["Дата", "На что", "Сумма, ₽"]


class ClientRegistryGoogleSheetsError(Exception):
    """A stable, credential-safe reason for a scheduled sync failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ClientRegistryRow:
    tenant_id: uuid.UUID
    name: str
    registration_date: datetime
    latest_activity: datetime | None
    has_access: bool
    paid_until: date | None

    def system_values(self) -> list[str]:
        return [
            str(self.tenant_id),
            self.name,
            _format_date(self.registration_date),
            _format_datetime(self.latest_activity),
            "Да" if self.has_access else "Нет",
            _format_date(self.paid_until),
        ]


@dataclass(frozen=True)
class RegistrySheetSnapshot:
    sheet_id: int
    values: list[list[str]]


@dataclass(frozen=True)
class RegistrySyncPlan:
    initialize: bool
    existing_updates: dict[int, list[str]]
    new_rows: list[list[str]]
    insert_at_row: int
    separator_row: int


class ClientRegistryGateway(Protocol):
    @property
    def lock_scope(self) -> str: ...

    def read_snapshot(self) -> RegistrySheetSnapshot: ...

    def apply(self, plan: RegistrySyncPlan) -> None: ...


def _format_date(value: datetime | date | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        value = value.astimezone(MOSCOW)
    return value.strftime("%d.%m.%Y")


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(MOSCOW).strftime("%d.%m.%Y %H:%M")


def _has_access(paid_until: date | None, today: date) -> bool:
    return paid_until is None or paid_until >= today


def _is_blank_sheet(values: list[list[str]]) -> bool:
    return not any(cell.strip() for row in values for cell in row if isinstance(cell, str))


def _cell(values: list[list[str]], row_index: int, column_index: int) -> str:
    if row_index >= len(values) or column_index >= len(values[row_index]):
        return ""
    return values[row_index][column_index]


def build_registry_sync_plan(
    snapshot: RegistrySheetSnapshot,
    clients: list[ClientRegistryRow],
) -> RegistrySyncPlan:
    """Build a non-destructive A:F upsert plan from current sheet values."""
    if _is_blank_sheet(snapshot.values):
        return RegistrySyncPlan(
            initialize=True,
            existing_updates={},
            new_rows=[[*client.system_values(), "", "", ""] for client in clients],
            insert_at_row=FIRST_CLIENT_ROW,
            separator_row=FIRST_CLIENT_ROW,
        )

    header_index = CLIENT_HEADER_ROW - 1
    headers = snapshot.values[header_index][: len(CLIENT_HEADERS)]
    if headers not in (CLIENT_HEADERS, LEGACY_CLIENT_HEADERS):
        raise ClientRegistryGoogleSheetsError("sheet_layout_conflict")

    separator_index: int | None = None
    existing_rows: dict[str, int] = {}
    for row_index in range(FIRST_CLIENT_ROW - 1, len(snapshot.values)):
        first_cell = _cell(snapshot.values, row_index, 0)
        if first_cell == EXPENSES_MARKER:
            separator_index = row_index
            break
        if not first_cell:
            continue
        if first_cell in existing_rows:
            raise ClientRegistryGoogleSheetsError("duplicate_tenant_id")
        existing_rows[first_cell] = row_index + 1

    if separator_index is None:
        raise ClientRegistryGoogleSheetsError("sheet_layout_conflict")
    if [
        _cell(snapshot.values, separator_index + 1, column_index)
        for column_index in range(len(EXPENSES_HEADERS))
    ] != EXPENSES_HEADERS:
        raise ClientRegistryGoogleSheetsError("sheet_layout_conflict")

    existing_updates: dict[int, list[str]] = {}
    new_rows: list[list[str]] = []
    for client in clients:
        row = existing_rows.get(str(client.tenant_id))
        if row is None:
            new_rows.append([*client.system_values(), "", "", ""])
        else:
            existing_updates[row] = client.system_values()

    return RegistrySyncPlan(
        initialize=False,
        existing_updates=existing_updates,
        new_rows=new_rows,
        insert_at_row=separator_index + 1,
        separator_row=separator_index + 1,
    )


def _activity_statement() -> Any:
    """Return the documented union of human activity timestamps by tenant."""
    activity_events = union_all(
        select(
            DocumentEvent.tenant_id.label("tenant_id"),
            DocumentEvent.occurred_at.label("at"),
        ).where(DocumentEvent.source == SOURCE_USER),
        select(
            InventoryMovement.tenant_id.label("tenant_id"),
            InventoryMovement.created_at.label("at"),
        ).where(InventoryMovement.actor_user_id.is_not(None)),
        select(InventoryCount.tenant_id.label("tenant_id"), InventoryCount.created_at.label("at")),
        select(
            InventoryCount.tenant_id.label("tenant_id"), InventoryCount.posted_at.label("at")
        ).where(
            InventoryCount.posted_at.is_not(None), InventoryCount.posted_by_user_id.is_not(None)
        ),
        select(FbsOrderPick.tenant_id.label("tenant_id"), FbsOrderPickEvent.created_at.label("at"))
        .join(FbsOrderPick, FbsOrderPick.id == FbsOrderPickEvent.pick_id)
        .where(FbsOrderPickEvent.actor_user_id.is_not(None)),
        select(
            PackagingTaskEvent.tenant_id.label("tenant_id"),
            PackagingTaskEvent.created_at.label("at"),
        ).where(PackagingTaskEvent.created_by_user_id.is_not(None)),
        select(
            MarkingCodeEvent.tenant_id.label("tenant_id"), MarkingCodeEvent.created_at.label("at")
        ).where(MarkingCodeEvent.actor_user_id.is_not(None)),
    ).subquery()
    return (
        select(
            activity_events.c.tenant_id,
            func.max(activity_events.c.at).label("latest_activity"),
        )
        .group_by(activity_events.c.tenant_id)
        .subquery()
    )


async def collect_client_registry_rows(
    session: AsyncSession,
    *,
    today: date | None = None,
) -> list[ClientRegistryRow]:
    """Read all and only fulfilments which have a fulfilment administrator."""
    latest_activity = _activity_statement()
    result = await session.execute(
        select(Tenant, latest_activity.c.latest_activity)
        .join(User, User.tenant_id == Tenant.id)
        .outerjoin(latest_activity, latest_activity.c.tenant_id == Tenant.id)
        .where(User.role == "fulfillment_admin")
        .distinct()
        .order_by(Tenant.created_at, Tenant.id)
    )
    current_day = today or datetime.now(MOSCOW).date()
    return [
        ClientRegistryRow(
            tenant_id=tenant.id,
            name=tenant.name,
            registration_date=tenant.created_at,
            latest_activity=activity,
            has_access=_has_access(tenant.subscription_paid_until, current_day),
            paid_until=tenant.subscription_paid_until,
        )
        for tenant, activity in result.all()
    ]


async def sync_client_registry(gateway: ClientRegistryGateway) -> RegistrySyncPlan:
    """Read the database, then apply one idempotent, one-way Sheet mutation."""
    async with SessionLocal() as session, _client_registry_lock(session, gateway.lock_scope):
        clients = await collect_client_registry_rows(session)
        snapshot = await asyncio.to_thread(gateway.read_snapshot)
        plan = build_registry_sync_plan(snapshot, clients)
        await asyncio.to_thread(gateway.apply, plan)
    return plan


def _client_registry_lock_key(scope: str) -> int:
    digest = hashlib.blake2b(
        f"wms:google-sheets:client-registry:{scope}".encode(), digest_size=8
    ).digest()
    raw = int.from_bytes(digest, "big", signed=False)
    return raw - (1 << 64) if raw >= 1 << 63 else raw


@asynccontextmanager
async def _client_registry_lock(session: AsyncSession, scope: str) -> AsyncIterator[None]:
    """Hold a transaction-scoped lock for one configured Google Sheet sync."""
    connection = await session.connection()
    if connection.dialect.name != "postgresql":
        yield
        return
    lock_key = _client_registry_lock_key(scope)
    # The AsyncSession exits by committing or rolling back its transaction, which
    # releases pg_advisory_xact_lock even if a preceding SQL statement aborted.
    await session.scalar(text("select pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
    yield


class GoogleSheetsClientRegistryGateway:
    """Blocking Google Sheets adapter, kept outside the database transaction."""

    def __init__(self, *, spreadsheet_id: str, service_account_file: str) -> None:
        self._spreadsheet_id = spreadsheet_id
        self._service_account_file = service_account_file
        self._service: Any | None = None
        self._sheet_id: int | None = None

    @property
    def lock_scope(self) -> str:
        return self._spreadsheet_id

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ClientRegistryGoogleSheetsError("google_client_unavailable") from exc
        try:
            credentials = Credentials.from_service_account_file(
                self._service_account_file,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
            return self._service
        except (OSError, ValueError) as exc:
            raise ClientRegistryGoogleSheetsError("credentials_unavailable") from exc

    def read_snapshot(self) -> RegistrySheetSnapshot:
        service = self._get_service()
        try:
            metadata = (
                service.spreadsheets()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    fields="sheets(properties(sheetId,title))",
                )
                .execute()
            )
            sheets = metadata.get("sheets", [])
            if len(sheets) != 1:
                raise ClientRegistryGoogleSheetsError("sheet_layout_conflict")
            properties = sheets[0]["properties"]
            if properties["title"] != SHEET_TITLE:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {
                                        "sheetId": properties["sheetId"],
                                        "title": SHEET_TITLE,
                                    },
                                    "fields": "title",
                                }
                            }
                        ]
                    },
                ).execute()
            self._sheet_id = int(properties["sheetId"])
            response = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"'{SHEET_TITLE}'!A1:I",
                )
                .execute()
            )
            values = response.get("values", [])
            return RegistrySheetSnapshot(sheet_id=self._sheet_id, values=values)
        except ClientRegistryGoogleSheetsError:
            raise
        except Exception as exc:
            raise ClientRegistryGoogleSheetsError("google_api_error") from exc

    def apply(self, plan: RegistrySyncPlan) -> None:
        if self._sheet_id is None:
            raise ClientRegistryGoogleSheetsError("sheet_not_opened")
        service = self._get_service()
        final_separator_row = plan.separator_row + len(plan.new_rows)
        requests: list[dict[str, Any]] = []
        if plan.new_rows:
            requests.append(
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": self._sheet_id,
                            "dimension": "ROWS",
                            "startIndex": plan.insert_at_row - 1,
                            "endIndex": plan.insert_at_row - 1 + len(plan.new_rows),
                        },
                        "inheritFromBefore": True,
                    }
                }
            )
        if plan.initialize:
            requests.extend(_initial_format_requests(self._sheet_id))
            requests.extend(_filter_and_data_format_requests(self._sheet_id, final_separator_row))
        elif plan.new_rows:
            requests.append(_basic_filter_request(self._sheet_id, final_separator_row))

        if plan.initialize:
            first_expense_row = final_separator_row + 2
            requests.extend(
                [
                    _update_cells_request(
                        self._sheet_id,
                        3,
                        2,
                        _summary_values(first_expense_row),
                        formula_indices=frozenset({1, 4, 7}),
                    ),
                    _update_cells_request(self._sheet_id, 5, 1, ["Клиенты"]),
                    _update_cells_request(self._sheet_id, 6, 1, CLIENT_HEADERS),
                    _update_cells_request(
                        self._sheet_id, final_separator_row, 1, [EXPENSES_MARKER]
                    ),
                    _update_cells_request(
                        self._sheet_id, final_separator_row + 1, 1, EXPENSES_HEADERS
                    ),
                ]
            )
        for row, values in plan.existing_updates.items():
            requests.append(_update_cells_request(self._sheet_id, row, 1, values))
        if plan.new_rows:
            first_row = plan.insert_at_row
            requests.append(
                _update_cells_rows_request(
                    self._sheet_id,
                    first_row,
                    [values[:6] for values in plan.new_rows],
                )
            )
        try:
            if requests:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=self._spreadsheet_id,
                    body={"requests": requests},
                ).execute()
        except Exception as exc:
            raise ClientRegistryGoogleSheetsError("google_api_error") from exc


def _summary_values(first_expense_row: int) -> list[str]:
    return [
        "Доход",
        "=SUM(H7:H)",
        "",
        "Расходы",
        f"=SUM(C{first_expense_row}:C)",
        "",
        "Баланс",
        "=C3-F3",
    ]


def _update_cells_request(
    sheet_id: int,
    row: int,
    column: int,
    values: list[str],
    *,
    formula_indices: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    return _update_cells_rows_request(
        sheet_id,
        row,
        [values],
        start_column=column,
        formula_indices=formula_indices,
    )


def _update_cells_rows_request(
    sheet_id: int,
    first_row: int,
    rows: list[list[str]],
    *,
    start_column: int = 1,
    formula_indices: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": first_row - 1,
                "endRowIndex": first_row - 1 + len(rows),
                "startColumnIndex": start_column - 1,
                "endColumnIndex": start_column - 1 + max(len(row) for row in rows),
            },
            "rows": [
                {
                    "values": [
                        _cell_value(value, formula=column_index in formula_indices)
                        for column_index, value in enumerate(row)
                    ]
                }
                for row in rows
            ],
            "fields": "userEnteredValue",
        }
    }


def _cell_value(value: str, *, formula: bool) -> dict[str, dict[str, str]]:
    # System strings such as a tenant name must never be interpreted as a Sheet formula.
    if formula:
        return {"userEnteredValue": {"formulaValue": value}}
    return {"userEnteredValue": {"stringValue": value}}


def _initial_format_requests(sheet_id: int) -> list[dict[str, Any]]:
    return [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 6}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        },
    ]


def _filter_and_data_format_requests(sheet_id: int, separator_row: int) -> list[dict[str, Any]]:
    return [
        _basic_filter_request(sheet_id, separator_row),
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": CLIENT_HEADER_ROW - 1,
                    "endRowIndex": CLIENT_HEADER_ROW,
                },
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        },
        _number_format_request(sheet_id, 2, 3, "dd.mm.yyyy"),
        _number_format_request(sheet_id, 3, 4, "dd.mm.yyyy hh:mm"),
        _number_format_request(sheet_id, 5, 6, "dd.mm.yyyy"),
        _number_format_request(sheet_id, 6, 7, "dd.mm.yyyy"),
        _number_format_request(sheet_id, 7, 8, "#,##0.00 [$₽-ru-RU]"),
        _number_format_request(sheet_id, 8, 9, "dd.mm.yyyy"),
        _number_format_request(sheet_id, 2, 3, "#,##0.00 [$₽-ru-RU]", start_row=2, end_row=3),
        _number_format_request(sheet_id, 5, 6, "#,##0.00 [$₽-ru-RU]", start_row=2, end_row=3),
        _number_format_request(sheet_id, 8, 9, "#,##0.00 [$₽-ru-RU]", start_row=2, end_row=3),
        _number_format_request(
            sheet_id,
            2,
            3,
            "#,##0.00 [$₽-ru-RU]",
            start_row=separator_row + 1,
        ),
    ]


def _basic_filter_request(sheet_id: int, separator_row: int) -> dict[str, Any]:
    return {
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": CLIENT_HEADER_ROW - 1,
                    "endRowIndex": separator_row - 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(CLIENT_HEADERS),
                }
            }
        }
    }


def _number_format_request(
    sheet_id: int,
    start_column: int,
    end_column: int,
    pattern: str,
    *,
    start_row: int = CLIENT_HEADER_ROW,
    end_row: int | None = None,
) -> dict[str, Any]:
    range_value: dict[str, int] = {
        "sheetId": sheet_id,
        "startColumnIndex": start_column,
        "endColumnIndex": end_column,
        "startRowIndex": start_row,
    }
    if end_row is not None:
        range_value["endRowIndex"] = end_row
    return {
        "repeatCell": {
            "range": range_value,
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": pattern}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }
