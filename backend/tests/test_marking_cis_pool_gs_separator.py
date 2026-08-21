"""I5: пул кодов маркировки хранится обрезанным (docs/BACKLOG-2026-08-19-CHAT-RU.md).

Импорт PDF продавца собирал «голую» строку GS1 "01<gtin>21<serial>" и
отбрасывал GS-разделитель, который сам WB требует даже у короткого (без
криптохвоста) КИЗ — см. WB-инструкцию
tasks/fbs-marketplace-orders/wb-docs/04-labeling/kiz-common-errors.md,
раздел «Короткий и длинный КИЗ». Без разделителя WB отвечает "sgtinNoGS"
(верифицировано разбором инцидента 20.08.2026, а не эмулятором WB — см.
предупреждение в наряде, что эмулятор раньше подтверждал неверные допущения).

Этот файл проверяет: разбор кода с настоящим криптохвостом и разделителями,
канонизацию короткого формата, восстановление накопленных обрезанных кодов
(идемпотентно, без перезаписи и без потерь), защиту перед отправкой в WB и то,
что поиск кода по хвосту не сломан добавлением невидимого байта в конец.
"""

from __future__ import annotations

import json
import uuid

import fitz
import pytest
from httpx import AsyncClient
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import MarkingCode, MarkingCodeImportFile
from app.services.marking_code_service import (
    GS_SEPARATOR,
    extract_gtin_from_cis,
    is_cis_missing_gs_separator,
    mask_cis_code,
    normalize_cis,
    restore_truncated_pool_cis_codes,
)

# ---------------------------------------------------------------------------
# Разбор кода: настоящая структура КИЗ по документации WB
# ---------------------------------------------------------------------------
#
# tasks/fbs-marketplace-orders/wb-docs/04-labeling/verify-product-identifiers.md,
# раздел «Как устроен код КИЗ»: GTIN (тег 01, 14 цифр) — серийный номер
# (тег 21) — ключ проверки (тег 91, 4 цифры) — криптохвост (тег 92/93).
# Между 21<serial> и 91<key> живёт единственный настоящий GS-разделитель:
# GTIN и ключ проверки в GS1 фиксированной длины и терминатора не требуют,
# а перед вариативным серийником он не нужен, раз других полей перед ним нет.
_REAL_GTIN = "04600000000001"
_REAL_SERIAL = "abcDEF12345"  # >=13 симв. не обязательно — реальные КИЗ короче в тестовых данных
_REAL_KEY = "A1B2"
_REAL_CRYPTO_TAIL = "XyZ9kkLmNoPqRsTuVwXyZ0123456789+/=ABCDEFabcdef01"
_FULL_CIS_WITH_CRYPTO = (
    f"01{_REAL_GTIN}21{_REAL_SERIAL}{GS_SEPARATOR}91{_REAL_KEY}92{_REAL_CRYPTO_TAIL}"
)


def test_full_cis_with_crypto_tail_and_real_gs_is_not_missing_separator() -> None:
    """Полный код (as documented) содержит настоящий GS — не должен считаться
    «обрезанным пула», это как раз то, что должно проходить без вмешательства."""
    assert not is_cis_missing_gs_separator(_FULL_CIS_WITH_CRYPTO)


def test_normalize_cis_preserves_full_cis_including_embedded_gs() -> None:
    """Раньше нормализация делала голый `.strip()` (Unicode-пробелы), а Python
    относит `\\x1c`-`\\x1f` (включая GS `\\x1d`) к пробельным символам для
    этой операции — значит хвостовой GS у короткого кода мог теряться прямо
    при повторной нормализации. Явный `.strip(" \\t\\r\\n\\ufeff")` должен
    сохранять и внутренний, и краевой GS."""
    normalized = normalize_cis(_FULL_CIS_WITH_CRYPTO)
    assert normalized == _FULL_CIS_WITH_CRYPTO
    assert GS_SEPARATOR in normalized
    assert normalized.count(GS_SEPARATOR) == 1


def test_normalize_cis_does_not_strip_leading_or_trailing_gs() -> None:
    """Regression: GS ровно на границе строки — тоже не должен теряться."""
    short_code = f"01{_REAL_GTIN}21{_REAL_SERIAL}{GS_SEPARATOR}"
    assert normalize_cis(short_code) == short_code
    assert normalize_cis(short_code).endswith(GS_SEPARATOR)


def test_extract_gtin_from_full_cis_matches_documented_gtin() -> None:
    assert extract_gtin_from_cis(_FULL_CIS_WITH_CRYPTO) == _REAL_GTIN


def test_extract_gtin_from_short_canonical_cis_matches_documented_gtin() -> None:
    short_code = f"01{_REAL_GTIN}21{_REAL_SERIAL}{GS_SEPARATOR}"
    assert extract_gtin_from_cis(short_code) == _REAL_GTIN


# ---------------------------------------------------------------------------
# Канонизация короткого формата (что теперь пишет импорт PDF продавца)
# ---------------------------------------------------------------------------


def _build_label_pdf(cis_text: str) -> bytes:
    """Одна страница-этикетка с человекочитаемым текстом кода — ровно то, что
    печатает продавец рядом с самим DataMatrix (см.
    tasks/fbs-marketplace-orders/wb-docs/04-labeling/kiz-common-errors.md:
    «сканировать лучше, чем копировать — при копировании GS-разделители
    теряются», то есть сам PDF-текст их никогда не несёт)."""
    doc = fitz.open()
    page = doc.new_page(width=164, height=113)
    page.insert_text((12, 24), "Честный знак", fontsize=8)
    page.insert_text((12, 42), cis_text, fontsize=6)
    pdf_bytes = bytes(doc.tobytes())
    doc.close()
    return pdf_bytes


async def _import_one_pdf_code(
    async_client: AsyncClient,
    *,
    gtin: str,
    serial: str,
    seller_name: str,
    product_name: str,
    sku_suffix: str,
) -> dict[str, object]:
    """Импортирует один код через PDF (путь, где живёт I5) и возвращает его
    строку из /operations/marking-codes/products/{id}/codes."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": seller_name, "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": product_name,
            "sku_code": f"SKU-{sku_suffix}-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200, pr.text
    product_id = pr.json()["id"]

    literal_cis = f"01{gtin}21{serial}"
    pdf_bytes = _build_label_pdf(literal_cis)
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": f"Pool {sku_suffix}", "product_ids": [product_id]}]
            ),
        },
        files=[("files", ("labels.pdf", pdf_bytes, "application/pdf"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 1

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert codes.status_code == 200, codes.text
    row = codes.json()[0]

    me = await async_client.get("/auth/me", headers=h)
    assert me.status_code == 200, me.text

    return {
        "headers": h,
        "seller_id": seller_id,
        "product_id": product_id,
        "tenant_id": me.json()["tenant_id"],
        "code_id": row["id"],
        "cis_code": row["cis_code"],
        "import_id": imp.json()["import_id"],
        "literal_cis": literal_cis,
    }


@pytest.mark.asyncio
async def test_pdf_import_now_stores_short_format_code_with_gs_terminator(
    async_client: AsyncClient,
) -> None:
    """The actual I5 fix: a freshly PDF-imported pool code must already carry
    the GS terminator, not the bare "01<gtin>21<serial>" the pre-fix
    `_canonical_cis_from_match` produced."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000010",
        serial="POOLFIX0000001",
        seller_name="GS Fix Seller",
        product_name="GS fix product",
        sku_suffix="GSFIX",
    )
    stored = seeded["cis_code"]
    assert isinstance(stored, str)
    assert not is_cis_missing_gs_separator(stored)
    assert stored == f"{seeded['literal_cis']}{GS_SEPARATOR}"


# ---------------------------------------------------------------------------
# Восстановление накопленных обрезанных кодов (команда CLI поверх этого сервиса)
# ---------------------------------------------------------------------------


async def _truncate_stored_cis_like_the_pre_fix_bug(code_id: str) -> str:
    """Симулирует боевые данные I5: перезаписывает уже сохранённый (правильный,
    с GS) код на голую строку без разделителя — ровно то, что писал старый
    `_canonical_cis_from_match` при импорте. Возвращает исходное (полное)
    значение, чтобы тест мог сверить восстановленный результат."""
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(code_id))
        assert code is not None
        original_full = code.cis_code
        assert not is_cis_missing_gs_separator(original_full), (
            "фикстура должна начинать с уже нормального (не обрезанного) кода"
        )
        code.cis_code = original_full.rstrip(GS_SEPARATOR)
        await session.commit()
    return original_full


@pytest.mark.asyncio
async def test_restore_fixes_legacy_truncated_code_via_own_label_artifact(
    async_client: AsyncClient,
) -> None:
    """Основной путь восстановления: у каждой PDF-импортированной строки есть
    своя обрезанная при импорте этикетка (`label_artifact_pdf`) — из неё можно
    достать код заново, не поднимая объектное хранилище с исходным файлом
    наряда."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000011",
        serial="POOLRESTORE0001",
        seller_name="Restore Seller",
        product_name="Restore product",
        sku_suffix="RESTORE",
    )
    original_full = await _truncate_stored_cis_like_the_pre_fix_bug(seeded["code_id"])

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert report.scanned == 1
    assert report.restored == 1
    assert report.counts_by_outcome() == {"restored": 1}
    [row] = report.rows
    assert row.outcome == "restored"

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code == original_full


@pytest.mark.asyncio
async def test_restore_is_idempotent_second_run_finds_nothing(
    async_client: AsyncClient,
) -> None:
    """Повторный прогон после успешного восстановления не должен находить
    кандидатов и уж тем более трогать уже починенную строку."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000012",
        serial="POOLIDEMPOTENT01",
        seller_name="Idempotent Seller",
        product_name="Idempotent product",
        sku_suffix="IDEMP",
    )
    original_full = await _truncate_stored_cis_like_the_pre_fix_bug(seeded["code_id"])

    async with SessionLocal() as session:
        first = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()
    assert first.restored == 1

    async with SessionLocal() as session:
        second = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert second.scanned == 0
    assert second.restored == 0
    assert second.rows == []

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code == original_full


@pytest.mark.asyncio
async def test_restore_does_not_touch_codes_that_already_have_gs(
    async_client: AsyncClient,
) -> None:
    """A code imported *after* the fix already carries the GS terminator —
    restore must not even count it as a candidate, let alone rewrite it."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000013",
        serial="POOLALREADYFULL1",
        seller_name="Already Full Seller",
        product_name="Already full product",
        sku_suffix="ALREADYFULL",
    )
    stored_before = seeded["cis_code"]

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert report.scanned == 0
    assert report.restored == 0

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code == stored_before


@pytest.mark.asyncio
async def test_restore_reports_target_conflict_and_does_not_overwrite(
    async_client: AsyncClient,
) -> None:
    """If the code the restore would produce is already taken by a different
    row (duplicate/import mishap), it must be reported, not silently
    overwritten — the unique constraint on (tenant_id, cis_code) backs this
    up at the DB level, but the report should say *why* in human terms."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000014",
        serial="POOLCONFLICT0001",
        seller_name="Conflict Seller",
        product_name="Conflict product",
        sku_suffix="CONFLICT",
    )
    same_gtin_serial_literal = f"01{'04600000000014'}21{'POOLCONFLICT0001'}"
    target_full = f"{same_gtin_serial_literal}{GS_SEPARATOR}"
    assert seeded["cis_code"] == target_full  # sanity: the two rows collide on purpose

    # Second row: a legacy-truncated duplicate of the very same GTIN+serial,
    # with its own label artifact that would restore to the same full code
    # already held by `seeded`.
    async with SessionLocal() as session:
        dup = MarkingCode(
            tenant_id=uuid.UUID(seeded["tenant_id"]),
            seller_id=uuid.UUID(seeded["seller_id"]),
            product_id=uuid.UUID(seeded["product_id"]),
            import_batch_id=uuid.UUID(seeded["import_id"]),
            cis_code=same_gtin_serial_literal,
            source="pool",
            label_artifact_pdf=_build_label_pdf(same_gtin_serial_literal),
        )
        session.add(dup)
        await session.commit()
        dup_id = dup.id

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert report.scanned == 1
    assert report.restored == 0
    [row] = report.rows
    assert row.outcome == "target_conflict"
    assert row.code_id == dup_id

    async with SessionLocal() as session:
        dup_after = await session.get(MarkingCode, dup_id)
        assert dup_after is not None
        assert dup_after.cis_code == same_gtin_serial_literal  # untouched, not overwritten


@pytest.mark.asyncio
async def test_restore_reports_no_source_when_no_artifact_and_no_import_file(
    async_client: AsyncClient,
) -> None:
    """A row with neither its own label artifact nor a stored import-file PDF
    (e.g. imported before either feature existed) must be reported as
    unrestorable, not crash the whole run."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000015",
        serial="POOLNOSOURCE0001",
        seller_name="No Source Seller",
        product_name="No source product",
        sku_suffix="NOSOURCE",
    )
    await _truncate_stored_cis_like_the_pre_fix_bug(seeded["code_id"])

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        code.label_artifact_pdf = None
        await session.execute(
            MarkingCodeImportFile.__table__.delete().where(
                MarkingCodeImportFile.import_batch_id == uuid.UUID(seeded["import_id"])
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert report.scanned == 1
    assert report.restored == 0
    [row] = report.rows
    assert row.outcome == "no_source_pdf"

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert is_cis_missing_gs_separator(code.cis_code)  # still untouched/truncated


# ---------------------------------------------------------------------------
# mask_cis_code — не должен показывать управляющий байт оператору
# ---------------------------------------------------------------------------


def test_mask_cis_code_hides_trailing_gs_and_shows_real_tail() -> None:
    short_code = f"01{_REAL_GTIN}21{_REAL_SERIAL}{GS_SEPARATOR}"
    masked = mask_cis_code(short_code)
    assert GS_SEPARATOR not in masked
    assert masked.endswith(_REAL_SERIAL[-12:])


def test_mask_cis_code_full_cis_unaffected() -> None:
    masked = mask_cis_code(_FULL_CIS_WITH_CRYPTO)
    assert GS_SEPARATOR not in masked
    assert masked.endswith(_REAL_CRYPTO_TAIL[-12:])


# ---------------------------------------------------------------------------
# Поиск по хвосту не должен ломаться добавленным GS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ledger_search_by_tail_still_finds_pdf_imported_code_with_gs(
    async_client: AsyncClient,
) -> None:
    """Регресс: журнал (`/operations/marking-codes/ledger?cis_mask=...`) ищет
    код по видимому хвосту через SQL `contains` (LIKE %needle%) — добавленный
    в конец GS-разделитель не должен ломать эту подстрочную проверку, потому
    что важные для оператора цифры всё ещё находятся строго перед ним, а не
    строго в конце строки."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000016",
        serial="POOLTAILSEARCH01",
        seller_name="Tail Search Seller",
        product_name="Tail search product",
        sku_suffix="TAILSEARCH",
    )
    h = seeded["headers"]
    stored_cis = seeded["cis_code"]
    assert isinstance(stored_cis, str)
    assert stored_cis.endswith(GS_SEPARATOR)

    masked = mask_cis_code(stored_cis)
    assert GS_SEPARATOR not in masked
    tail = masked.lstrip("…")[:6]

    by_mask = await async_client.get(
        "/operations/marking-codes/ledger",
        headers=h,
        params={"seller_id": seeded["seller_id"], "cis_mask": tail},
    )
    assert by_mask.status_code == 200, by_mask.text
    body = by_mask.json()
    assert body["total"] >= 1
    for row in body["rows"]:
        if row.get("aggregated_count"):
            assert row["cis_masked"] is None
        else:
            assert row["cis_masked"] is not None
            assert tail in row["cis_masked"]
