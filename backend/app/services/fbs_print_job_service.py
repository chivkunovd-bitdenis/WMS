"""Печать готовой этикетки FBS на складской принтер через локального агента.

Задание печати — это существующая строка ``BackgroundJob`` с типом
``fbs_label_print``. Отдельной таблицы, журнала попыток и счётчиков здесь нет и
быть не должно: идентификатор задания задаёт ТСД, и первичный ключ сам по себе
обеспечивает идемпотентность повторного HTTP-запроса.

Границы, которые нельзя размывать:

* задание ссылается ровно на один **уже готовый** ``FbsPrintAsset``; повторной
  подготовки этикетки и повторных обращений к маркетплейсу тут не происходит.
  Актив бывает двух происхождений и обрабатывается одинаково: либо этикетка,
  которую маркетплейс отдал раньше (QR заказа, QR короба), либо готовый лист,
  который ТСД собрал сам (товарный ШК и код ЧЗ). Во втором случае сервер
  принимает файл как есть и после постановки в очередь не меняет его;
* ``done`` означает только «очередь ОС приняла файл», а не «бумага вышла».
  Поэтому статус для оператора называется «Передано в очередь принтера»;
* задание, выданное агенту (``running``), само в ``pending`` не возвращается.
  Потерянное подтверждение не превращается в повторную печать: новую печать
  оператор запускает явно, с новым идентификатором.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder
from app.models.fbs_print_asset import (
    PRINT_ASSET_KIND_CARGO_PLACE_QR,
    PRINT_ASSET_KIND_OPERATOR_DOCUMENT,
    PRINT_ASSET_KIND_ORDER_STICKER,
    PRINT_ASSET_KIND_SUPPLY_QR,
    PRINT_ASSET_STATUS_READY,
    FbsPrintAsset,
)
from app.models.fbs_supply import FbsSupply
from app.models.fbs_trbx import FbsTrbx
from app.models.warehouse import Warehouse
from app.services.background_job_service import (
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_TYPE_FBS_LABEL_PRINT,
)
from app.services.fbs_cancelled_after_pack_service import cancelled_operation_message
from app.services.fbs_print_asset_service import FbsPrintAssetError
from app.services.fbs_print_asset_storage import (
    ORDER_STICKER_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    FbsPrintAssetStorageError,
    operator_document_relative_path,
    read_print_file,
    save_print_file,
    sha256_checksum,
)

# Сколько ожидающих заданий склада агент просматривает за один запрос. Ограничение
# нужно только чтобы не тянуть из базы всю очередь разом.
_CLAIM_SCAN_LIMIT = 100

# Тот же потолок на файл этикеток, что и в ТСД: больше 16 МиБ печать не начинают.
MAX_PRINT_DOCUMENT_BYTES = 16 * 1024 * 1024

PRINT_JOB_STATUS_TEXT: dict[str, str] = {
    JOB_STATUS_PENDING: "Ожидает агента печати",
    JOB_STATUS_RUNNING: "Выдано агенту печати; подтверждение очереди не получено",
    JOB_STATUS_DONE: "Передано в очередь принтера",
    JOB_STATUS_FAILED: "Не передано в очередь принтера",
}


def print_job_status_text(status: str) -> str:
    return PRINT_JOB_STATUS_TEXT.get(status, status)


def _payload_identity(payload: dict[str, Any] | None) -> tuple[str, str, str]:
    data = payload or {}
    return (
        str(data.get("asset_id")),
        str(data.get("warehouse_id")),
        str(data.get("requested_by_user_id")),
    )


async def _resolve_asset_warehouse_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    asset: FbsPrintAsset,
) -> uuid.UUID | None:
    """Склад определяет сервер по самой этикетке, а не по слову клиента."""
    supply_id: uuid.UUID | None = asset.fbs_supply_id
    if asset.kind == PRINT_ASSET_KIND_ORDER_STICKER and asset.fbs_order_id is not None:
        order = await session.get(FbsOrder, asset.fbs_order_id)
        if order is None or order.tenant_id != tenant_id:
            return None
        if order.warehouse_id is not None:
            return order.warehouse_id
        supply_id = order.supply_id
    elif asset.kind == PRINT_ASSET_KIND_CARGO_PLACE_QR and asset.fbs_trbx_id is not None:
        trbx = await session.get(FbsTrbx, asset.fbs_trbx_id)
        if trbx is None:
            return None
        supply_id = trbx.supply_id
    if supply_id is None:
        return None
    supply = await session.get(FbsSupply, supply_id)
    if supply is None or supply.tenant_id != tenant_id:
        return None
    return supply.warehouse_id


async def _load_ready_asset(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> FbsPrintAsset:
    asset = await session.scalar(
        select(FbsPrintAsset).where(
            FbsPrintAsset.id == asset_id,
            FbsPrintAsset.tenant_id == tenant_id,
        )
    )
    if asset is None:
        raise FbsPrintAssetError("asset_not_found", message="Печатный актив не найден.")
    if asset.kind not in {
        PRINT_ASSET_KIND_ORDER_STICKER,
        PRINT_ASSET_KIND_CARGO_PLACE_QR,
        PRINT_ASSET_KIND_SUPPLY_QR,
        PRINT_ASSET_KIND_OPERATOR_DOCUMENT,
    }:
        raise FbsPrintAssetError("invalid_kind", message="Неизвестный тип печатного актива.")
    if asset.status != PRINT_ASSET_STATUS_READY or not asset.storage_path:
        raise FbsPrintAssetError(
            "asset_not_ready",
            message="Этикетка ещё не готова — запросите её в поставке.",
            context={"asset_id": str(asset_id)},
        )
    if asset.fbs_order_id is not None:
        order = await session.get(FbsOrder, asset.fbs_order_id)
        if order is not None and order.status == FBS_ORDER_STATUS_CANCELLED:
            raise FbsPrintAssetError(
                "order_cancelled",
                message=cancelled_operation_message(order, "печатать этикетку нельзя"),
                context={"order_id": str(order.id)},
            )
    return asset


def _read_asset_bytes(asset: FbsPrintAsset) -> tuple[bytes, str]:
    content_type = asset.content_type or ORDER_STICKER_CONTENT_TYPE
    if not asset.storage_path:
        raise FbsPrintAssetError("asset_not_ready", message="Файл печати недоступен.")
    try:
        payload = read_print_file(
            asset.storage_path,
            checksum=asset.checksum,
            content_type=content_type,
        )
    except FbsPrintAssetStorageError as exc:
        raise FbsPrintAssetError(
            "asset_not_ready",
            message="Файл печати недоступен.",
            context={"asset_id": str(asset.id), "reason": exc.code},
        ) from exc
    return payload, content_type


async def create_print_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    job_id: uuid.UUID,
    asset_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    user_id: uuid.UUID,
) -> BackgroundJob:
    """Поставить в очередь печать одной готовой этикетки.

    Тот же ``job_id`` с тем же намерением возвращает прежнее задание — второго
    листа не появится. Тот же ``job_id`` с другим намерением отклоняется.
    """
    existing = await session.get(BackgroundJob, job_id)
    if existing is not None:
        return _existing_or_conflict(
            existing,
            tenant_id=tenant_id,
            asset_id=asset_id,
            warehouse_id=warehouse_id,
            user_id=user_id,
        )

    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise FbsPrintAssetError("warehouse_not_found", message="Склад не найден.")

    asset = await _load_ready_asset(session, tenant_id, asset_id)
    asset_warehouse_id = await _resolve_asset_warehouse_id(session, tenant_id, asset)
    if asset_warehouse_id is None or asset_warehouse_id != warehouse_id:
        raise FbsPrintAssetError(
            "print_asset_warehouse_mismatch",
            message="Этикетка относится к другому складу.",
            context={"asset_id": str(asset_id), "warehouse_id": str(warehouse_id)},
        )
    # Файл читаем целиком уже здесь: контрольная сумма и формат проверяются до
    # того, как задание попадёт в очередь, а не когда агент придёт за файлом.
    _read_asset_bytes(asset)

    job = BackgroundJob(
        id=job_id,
        tenant_id=tenant_id,
        job_type=JOB_TYPE_FBS_LABEL_PRINT,
        status=JOB_STATUS_PENDING,
        payload_json={
            "asset_id": str(asset_id),
            "asset_kind": asset.kind,
            "warehouse_id": str(warehouse_id),
            "content_type": asset.content_type or ORDER_STICKER_CONTENT_TYPE,
            "checksum": asset.checksum,
            "width_mm": asset.width_mm,
            "height_mm": asset.height_mm,
            "requested_by_user_id": str(user_id),
        },
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raced = await session.get(BackgroundJob, job_id)
        if raced is None:
            raise
        return _existing_or_conflict(
            raced,
            tenant_id=tenant_id,
            asset_id=asset_id,
            warehouse_id=warehouse_id,
            user_id=user_id,
        )
    return job


def _existing_or_conflict(
    job: BackgroundJob,
    *,
    tenant_id: uuid.UUID,
    asset_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    user_id: uuid.UUID,
) -> BackgroundJob:
    same_intent = (
        job.tenant_id == tenant_id
        and job.job_type == JOB_TYPE_FBS_LABEL_PRINT
        and _payload_identity(job.payload_json) == (str(asset_id), str(warehouse_id), str(user_id))
    )
    if not same_intent:
        raise FbsPrintAssetError(
            "print_job_conflict",
            message="Этот номер печати уже занят другим заданием.",
            context={"job_id": str(job.id)},
        )
    return job


def _document_identity(payload: dict[str, Any] | None) -> tuple[str, str, str]:
    data = payload or {}
    return (
        str(data.get("supply_id")),
        str(data.get("checksum")),
        str(data.get("requested_by_user_id")),
    )


def _existing_document_or_conflict(
    job: BackgroundJob,
    *,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    checksum: str,
    user_id: uuid.UUID,
) -> BackgroundJob:
    same_intent = (
        job.tenant_id == tenant_id
        and job.job_type == JOB_TYPE_FBS_LABEL_PRINT
        and _document_identity(job.payload_json) == (str(supply_id), checksum, str(user_id))
    )
    if not same_intent:
        raise FbsPrintAssetError(
            "print_job_conflict",
            message="Этот номер печати уже занят другим заданием.",
            context={"job_id": str(job.id)},
        )
    return job


async def create_document_print_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    job_id: uuid.UUID,
    supply_id: uuid.UUID,
    document: bytes,
    user_id: uuid.UUID,
) -> BackgroundJob:
    """Поставить в очередь готовый лист этикеток, собранный самим ТСД.

    Это тот же самый файл, который ТСД до этого печатал у себя: товарный ШК,
    код ЧЗ и QR заказа уже нарисованы в нём. Сервер его не собирает и не
    пересобирает, к маркетплейсу не ходит — он принимает лист как есть,
    складывает его в то же хранилище печатных активов и ставит в ту же очередь.

    Повторный запрос с тем же ``job_id`` и тем же файлом возвращает прежнее
    задание: одно нажатие оператора — один лист.
    """
    checksum = sha256_checksum(document)
    existing = await session.get(BackgroundJob, job_id)
    if existing is not None:
        return _existing_document_or_conflict(
            existing,
            tenant_id=tenant_id,
            supply_id=supply_id,
            checksum=checksum,
            user_id=user_id,
        )

    if not document or len(document) > MAX_PRINT_DOCUMENT_BYTES:
        raise FbsPrintAssetError(
            "invalid_print_document",
            message="Файл этикеток пуст или превышает допустимый размер.",
        )
    supply = await session.get(FbsSupply, supply_id)
    if supply is None or supply.tenant_id != tenant_id:
        raise FbsPrintAssetError("supply_not_found", message="Поставка не найдена.")
    warehouse = await session.get(Warehouse, supply.warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise FbsPrintAssetError("warehouse_not_found", message="Склад не найден.")

    asset_id = uuid.uuid4()
    try:
        storage_path = save_print_file(
            operator_document_relative_path(asset_id),
            document,
            content_type=PDF_CONTENT_TYPE,
        )
    except FbsPrintAssetStorageError as exc:
        raise FbsPrintAssetError(
            "invalid_print_document",
            message="Файл этикеток не принят: ожидается PDF.",
            context={"reason": exc.code},
        ) from exc

    session.add(
        FbsPrintAsset(
            id=asset_id,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            kind=PRINT_ASSET_KIND_OPERATOR_DOCUMENT,
            status=PRINT_ASSET_STATUS_READY,
            content_type=PDF_CONTENT_TYPE,
            storage_path=storage_path,
            checksum=checksum,
            fbs_supply_id=supply.id,
        )
    )
    job = BackgroundJob(
        id=job_id,
        tenant_id=tenant_id,
        job_type=JOB_TYPE_FBS_LABEL_PRINT,
        status=JOB_STATUS_PENDING,
        payload_json={
            "asset_id": str(asset_id),
            "asset_kind": PRINT_ASSET_KIND_OPERATOR_DOCUMENT,
            "supply_id": str(supply_id),
            "warehouse_id": str(supply.warehouse_id),
            "content_type": PDF_CONTENT_TYPE,
            "checksum": checksum,
            "width_mm": None,
            "height_mm": None,
            "requested_by_user_id": str(user_id),
        },
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raced = await session.get(BackgroundJob, job_id)
        if raced is None:
            raise
        return _existing_document_or_conflict(
            raced,
            tenant_id=tenant_id,
            supply_id=supply_id,
            checksum=checksum,
            user_id=user_id,
        )
    return job


async def claim_next_print_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
) -> BackgroundJob | None:
    """Выдать агенту одно ожидающее задание его склада и пометить выданным.

    Перевод в ``running`` идёт условным UPDATE по статусу, поэтому два
    одновременных агента не получат одну строку: второй UPDATE не найдёт её
    ожидающей и вернёт ноль изменённых строк.
    """
    candidates = (
        await session.scalars(
            select(BackgroundJob)
            .where(
                BackgroundJob.tenant_id == tenant_id,
                BackgroundJob.job_type == JOB_TYPE_FBS_LABEL_PRINT,
                BackgroundJob.status == JOB_STATUS_PENDING,
                BackgroundJob.payload_json["warehouse_id"].as_string() == str(warehouse_id),
            )
            .order_by(BackgroundJob.created_at)
            .limit(_CLAIM_SCAN_LIMIT)
        )
    ).all()
    for candidate in candidates:
        claimed = await session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == candidate.id,
                BackgroundJob.status == JOB_STATUS_PENDING,
            )
            .values(status=JOB_STATUS_RUNNING, started_at=datetime.now(tz=UTC))
            .execution_options(synchronize_session=False)
        )
        if getattr(claimed, "rowcount", 0) != 1:
            continue
        await session.refresh(candidate)
        return candidate
    return None


async def get_agent_print_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
) -> BackgroundJob:
    job = await session.get(BackgroundJob, job_id)
    if (
        job is None
        or job.tenant_id != tenant_id
        or job.job_type != JOB_TYPE_FBS_LABEL_PRINT
        or (job.payload_json or {}).get("warehouse_id") != str(warehouse_id)
    ):
        raise FbsPrintAssetError(
            "print_job_not_found",
            message="Задание печати не найдено.",
            context={"job_id": str(job_id)},
        )
    return job


async def get_print_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
) -> BackgroundJob:
    job = await session.get(BackgroundJob, job_id)
    if job is None or job.tenant_id != tenant_id or job.job_type != JOB_TYPE_FBS_LABEL_PRINT:
        raise FbsPrintAssetError(
            "print_job_not_found",
            message="Задание печати не найдено.",
            context={"job_id": str(job_id)},
        )
    return job


async def load_print_job_content(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
) -> tuple[bytes, str]:
    """Отдать агенту файл только его выданного задания.

    Печать не «открывалась оператором», поэтому ``print_opened_at`` тут не
    трогаем: это отметка операторского просмотра, а не выдачи агенту.
    """
    job = await get_agent_print_job(session, tenant_id, job_id, warehouse_id=warehouse_id)
    if job.status != JOB_STATUS_RUNNING:
        raise FbsPrintAssetError(
            "print_job_not_running",
            message="Задание печати не выдано агенту.",
            context={"job_id": str(job_id), "status": job.status},
        )
    payload = job.payload_json or {}
    asset = await _load_ready_asset(session, tenant_id, uuid.UUID(str(payload.get("asset_id"))))
    if asset.checksum != payload.get("checksum"):
        raise FbsPrintAssetError(
            "print_asset_changed",
            message="Файл этикетки изменился после постановки в очередь.",
            context={"job_id": str(job_id)},
        )
    return _read_asset_bytes(asset)


async def finish_print_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    queue_receipt: str | None,
    handed_to_queue: bool,
    error_message: str | None,
) -> BackgroundJob:
    """Записать квитанцию очереди ОС.

    ``handed_to_queue=False`` допустим только когда агент достоверно не отдал
    файл в очередь. Обрыв, при котором приём неизвестен, подтверждением не
    является: такое задание остаётся ``running`` без конечной квитанции.
    """
    job = await get_agent_print_job(session, tenant_id, job_id, warehouse_id=warehouse_id)
    target_status = JOB_STATUS_DONE if handed_to_queue else JOB_STATUS_FAILED
    if job.status in {JOB_STATUS_DONE, JOB_STATUS_FAILED}:
        recorded = (job.result_json or {}).get("queue_receipt")
        if job.status != target_status or recorded != queue_receipt:
            raise FbsPrintAssetError(
                "print_job_result_conflict",
                message="Задание печати уже завершено с другим результатом.",
                context={"job_id": str(job_id), "status": job.status},
            )
        return job
    if job.status != JOB_STATUS_RUNNING:
        raise FbsPrintAssetError(
            "print_job_not_running",
            message="Задание печати не выдано агенту.",
            context={"job_id": str(job_id), "status": job.status},
        )
    job.status = target_status
    job.result_json = {
        "queue_receipt": queue_receipt,
        "handed_to_queue_at": datetime.now(tz=UTC).isoformat(),
    }
    job.error_message = error_message
    job.finished_at = datetime.now(tz=UTC)
    await session.flush()
    return job
