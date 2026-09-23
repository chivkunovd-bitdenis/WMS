from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.settings import settings
from app.models.document_event import SOURCE_SYSTEM, SOURCE_USER, DocumentEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.services.client_registry_google_sheets_service import (
    ClientRegistryRow,
    GoogleSheetsClientRegistryGateway,
    RegistrySheetSnapshot,
    RegistrySyncPlan,
    _client_registry_lock,
    _summary_values,
    _update_cells_request,
    build_registry_sync_plan,
    collect_client_registry_rows,
)
from app.tasks.billing_tasks import run_client_registry_google_sheets_sync_task


def _registry_snapshot(*, tenant_id: str, manual_values: list[str]) -> RegistrySheetSnapshot:
    return RegistrySheetSnapshot(
        sheet_id=1,
        values=[
            [],
            [],
            ["", "Доход", "=sum"],
            [],
            ["Клиенты"],
            [
                "ID клиента",
                "Фулфилмент",
                "Дата регистрации",
                "Последняя активность",
                "Доступ",
                "Оплачено до",
                "Дата оплаты",
                "Сумма, ₽",
                "Следующая оплата",
            ],
            [tenant_id, "Старое имя", "01.01.2026", "", "Да", "", *manual_values],
            ["Расходы"],
            ["Дата", "На что", "Сумма, ₽"],
            ["01.02.2026", "Связь", "1500"],
        ],
    )


def _client(
    tenant_id: uuid.UUID,
    *,
    name: str,
    paid_until: date | None = None,
) -> ClientRegistryRow:
    return ClientRegistryRow(
        tenant_id=tenant_id,
        name=name,
        registration_date=datetime(2026, 1, 1, tzinfo=UTC),
        latest_activity=None,
        has_access=True,
        paid_until=paid_until,
    )


def test_plan_updates_only_system_cells_and_inserts_before_expenses() -> None:
    existing_id = uuid.uuid4()
    new_id = uuid.uuid4()
    snapshot = _registry_snapshot(
        tenant_id=str(existing_id),
        manual_values=["11.02.2026", "12000", "11.03.2026"],
    )

    plan = build_registry_sync_plan(
        snapshot,
        [_client(existing_id, name="Новое имя"), _client(new_id, name="Новый FF")],
    )

    assert not plan.initialize
    assert plan.existing_updates == {7: [str(existing_id), "Новое имя", "01.01.2026", "", "Да", ""]}
    assert plan.insert_at_row == 8
    assert plan.separator_row == 8
    assert plan.new_rows == [[str(new_id), "Новый FF", "01.01.2026", "", "Да", "", "", "", ""]]
    # The plan does not carry G:I of an existing row, so an API adapter cannot
    # overwrite values entered by the owner while changing the fulfilment name.
    assert snapshot.values[6][6:] == ["11.02.2026", "12000", "11.03.2026"]
    assert snapshot.values[9] == ["01.02.2026", "Связь", "1500"]


def test_blank_sheet_initializes_one_list_with_no_manual_values() -> None:
    tenant_id = uuid.uuid4()

    plan = build_registry_sync_plan(
        RegistrySheetSnapshot(sheet_id=1, values=[]),
        [_client(tenant_id, name="Первый FF")],
    )

    assert plan.initialize
    assert plan.insert_at_row == 7
    assert plan.separator_row == 7
    assert plan.new_rows == [[str(tenant_id), "Первый FF", "01.01.2026", "", "Да", "", "", "", ""]]


def test_legacy_headers_remain_readable_without_changing_manual_columns() -> None:
    tenant_id = uuid.uuid4()
    snapshot = _registry_snapshot(tenant_id=str(tenant_id), manual_values=["", "", ""])
    snapshot.values[5] = [
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

    plan = build_registry_sync_plan(snapshot, [_client(tenant_id, name="FF")])

    assert plan.existing_updates[7] == [str(tenant_id), "FF", "01.01.2026", "", "Да", ""]


def test_summary_expenses_formula_starts_after_actual_expense_header() -> None:
    assert _summary_values(24)[4] == "=SUM(C24:C)"
    assert _summary_values(9)[4] == "=SUM(C9:C)"


def test_system_value_starting_with_equals_is_written_as_literal_string() -> None:
    request = _update_cells_request(1, 7, 1, ["=not-a-formula"])

    value = request["updateCells"]["rows"][0]["values"][0]["userEnteredValue"]
    assert value == {"stringValue": "=not-a-formula"}


class _FakeBatchUpdate:
    def __init__(self) -> None:
        self.bodies: list[dict[str, object]] = []

    def batchUpdate(self, *, spreadsheetId: str, body: dict[str, object]) -> _FakeBatchUpdate:
        assert spreadsheetId == "sheet-id"
        self.bodies.append(body)
        return self

    def execute(self) -> dict[str, object]:
        return {}


class _FakeGoogleService:
    def __init__(self) -> None:
        self.batch = _FakeBatchUpdate()

    def spreadsheets(self) -> _FakeBatchUpdate:
        return self.batch


def test_insert_and_client_values_share_one_google_batch_update() -> None:
    gateway = GoogleSheetsClientRegistryGateway(
        spreadsheet_id="sheet-id", service_account_file="not-read-by-this-test"
    )
    fake = _FakeGoogleService()
    gateway._service = fake
    gateway._sheet_id = 1
    plan = RegistrySyncPlan(
        initialize=False,
        existing_updates={},
        new_rows=[["tenant-id", "=FF name", "01.01.2026", "", "Да", "", "", "", ""]],
        insert_at_row=22,
        separator_row=22,
    )

    gateway.apply(plan)

    assert len(fake.batch.bodies) == 1
    requests = fake.batch.bodies[0]["requests"]
    assert isinstance(requests, list)
    assert any("insertDimension" in request for request in requests)
    update_cells = next(request["updateCells"] for request in requests if "updateCells" in request)
    assert update_cells["rows"][0]["values"][1]["userEnteredValue"] == {"stringValue": "=FF name"}


class _PostgresLockSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def connection(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def scalar(self, statement: object, _params: object) -> None:
        self.calls.append(str(statement))


@pytest.mark.asyncio
async def test_registry_lock_is_transaction_scoped_without_explicit_unlock() -> None:
    session = _PostgresLockSession()

    async with _client_registry_lock(session, "sheet-id"):  # type: ignore[arg-type]
        pass

    assert len(session.calls) == 1
    assert "pg_advisory_xact_lock" in session.calls[0]
    assert "pg_advisory_unlock" not in session.calls[0]


@pytest.mark.asyncio
async def test_collects_only_fulfilment_admins_and_human_activity(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    fulfilment = Tenant(
        name="Рабочий FF",
        slug="wms-515-fulfilment",
        subscription_paid_until=date(2026, 9, 23),
        created_at=now - timedelta(days=5),
    )
    seller_only = Tenant(name="Не клиент", slug="wms-515-seller-only", created_at=now)
    db_session.add_all([fulfilment, seller_only])
    await db_session.flush()
    admin = User(
        tenant_id=fulfilment.id,
        email="wms515-admin@example.com",
        password_hash="test",
        role="fulfillment_admin",
    )
    seller_user = User(
        tenant_id=seller_only.id,
        email="wms515-seller@example.com",
        password_hash="test",
        role="fulfillment_seller",
    )
    db_session.add_all([admin, seller_user])
    await db_session.flush()
    db_session.add_all(
        [
            DocumentEvent(
                tenant_id=fulfilment.id,
                document_type="inbound_intake",
                document_id=uuid.uuid4(),
                event_type="data_changed",
                actor_user_id=admin.id,
                source=SOURCE_USER,
                occurred_at=now - timedelta(hours=2),
                payload_json={},
            ),
            DocumentEvent(
                tenant_id=fulfilment.id,
                document_type="inbound_intake",
                document_id=uuid.uuid4(),
                event_type="status_changed",
                source=SOURCE_SYSTEM,
                occurred_at=now - timedelta(hours=1),
                payload_json={},
            ),
        ]
    )
    await db_session.commit()

    rows = await collect_client_registry_rows(db_session, today=date(2026, 9, 23))

    assert len(rows) == 1
    assert rows[0].tenant_id == fulfilment.id
    assert rows[0].name == "Рабочий FF"
    # SQLite test storage does not preserve timezone info for DateTime columns;
    # the export formatter treats this persisted representation as UTC.
    assert rows[0].latest_activity == (now - timedelta(hours=2)).replace(tzinfo=None)
    assert rows[0].has_access
    assert rows[0].system_values()[4:] == ["Да", "23.09.2026"]


def test_schedule_runs_only_three_times_in_moscow_day() -> None:
    entry = celery_app.conf.beat_schedule["client-registry-google-sheets"]

    assert entry["task"] == "wms.client_registry_google_sheets_sync"
    assert entry["schedule"].minute == {0}
    assert entry["schedule"].hour == {9, 15, 21}


def test_task_without_google_configuration_is_a_safe_noop(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "google_sheets_client_registry_sheet_id", "")
    monkeypatch.setattr(settings, "google_sheets_service_account_file", "")

    run_client_registry_google_sheets_sync_task()

    assert "configuration_missing" in caplog.text
