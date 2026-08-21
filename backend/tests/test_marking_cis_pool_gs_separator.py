"""I5 / I5-2: пул кодов маркировки хранится обрезанным (docs/BACKLOG-2026-08-19-CHAT-RU.md).

Импорт PDF продавца собирал «голую» строку GS1 "01<gtin>21<serial>" и
отбрасывал GS-разделитель, который сам WB требует даже у короткого (без
криптохвоста) КИЗ — см. WB-инструкцию
tasks/fbs-marketplace-orders/wb-docs/04-labeling/kiz-common-errors.md,
раздел «Короткий и длинный КИЗ». Без разделителя WB отвечает "sgtinNoGS"
(верифицировано разбором инцидента 20.08.2026, а не эмулятором WB — см.
предупреждение в наряде, что эмулятор раньше подтверждал неверные допущения).

Первая попытка почини́ть это (I5) была недостаточной: она «досочиняла»
короткий код прямо из текста PDF, дописывая GS-разделитель без ключа
проверки (тег 91) — а WB требует и его тоже, даже у короткого формата. На
бою это оставило 2806 кодов с GS, но без ключа — всё ещё непригодных для
отправки. Единственный источник полного кода — картинка DataMatrix на
этикетке (человекочитаемый текст рядом с ней никогда не несёт ни ключ
проверки, ни криптохвост), поэтому I5-2 распознаёт код с картинки
(`app.services.marking_datamatrix_service`, библиотека `zxing-cpp`), а не
собирает его из текста.

Этот файл проверяет: структурные предикаты (`is_cis_missing_gs_separator`,
`is_cis_missing_verification_key`, `is_cis_incomplete_for_wb`), импорт PDF с
настоящей картинкой DataMatrix, восстановление накопленных обрезанных кодов
(идемпотентно, без перезаписи и без потерь, не трогая коды не в статусе
«доступен» и коды другого товара), защиту перед отправкой в WB и то, что
поиск кода по хвосту не сломан добавлением невидимого байта в конец.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from marking_datamatrix_test_helpers import (
    build_datamatrix_label_pdf,
    build_full_cis,
    build_two_datamatrix_label_pdf,
    encode_datamatrix_png,
)
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_APPLIED, MarkingCode, MarkingCodeImportFile
from app.services.marking_code_service import (
    GS_SEPARATOR,
    extract_gtin_from_cis,
    is_cis_incomplete_for_wb,
    is_cis_missing_gs_separator,
    is_cis_missing_verification_key,
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
_SHORT_CIS_WITH_KEY = f"01{_REAL_GTIN}21{_REAL_SERIAL}{GS_SEPARATOR}91{_REAL_KEY}"


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
# I5-2: структурный заслон требует ключ проверки, а не любой GS-разделитель
# ---------------------------------------------------------------------------


def test_bare_code_with_no_gs_is_missing_gs_separator_and_incomplete() -> None:
    """Самая грубая обрезка (I5, исходный баг импорта): нет GS вообще."""
    bare = f"01{_REAL_GTIN}21{_REAL_SERIAL}"
    assert is_cis_missing_gs_separator(bare)
    assert is_cis_missing_verification_key(bare)  # GS нет — значит и AI(91) после него нет
    assert is_cis_incomplete_for_wb(bare)


def test_gs_terminated_code_with_no_key_is_missing_verification_key() -> None:
    """Ровно то, что оставил после себя прошлый, недостаточный прогон
    восстановления: GS есть, а после него сразу конец строки — ключа
    проверки (тег 91) нет. `is_cis_missing_gs_separator` в одиночку это не
    ловит (GS ведь есть) — но `is_cis_missing_verification_key` и общий
    `is_cis_incomplete_for_wb` обязаны."""
    gs_only = f"01{_REAL_GTIN}21{_REAL_SERIAL}{GS_SEPARATOR}"
    assert not is_cis_missing_gs_separator(gs_only)
    assert is_cis_missing_verification_key(gs_only)
    assert is_cis_incomplete_for_wb(gs_only)


def test_short_code_with_key_is_complete_for_wb() -> None:
    """Короткий формат (без криптохвоста), но с ключом проверки — именно то,
    что документация WB называет допустимым «коротким КИЗ»."""
    assert not is_cis_missing_gs_separator(_SHORT_CIS_WITH_KEY)
    assert not is_cis_missing_verification_key(_SHORT_CIS_WITH_KEY)
    assert not is_cis_incomplete_for_wb(_SHORT_CIS_WITH_KEY)


def test_full_code_with_crypto_tail_is_complete_for_wb() -> None:
    assert not is_cis_incomplete_for_wb(_FULL_CIS_WITH_CRYPTO)


# ---------------------------------------------------------------------------
# Импорт PDF с настоящей картинкой DataMatrix (полный код теперь берётся
# именно с неё, а не «досочиняется» из текста рядом)
# ---------------------------------------------------------------------------


async def _import_one_pdf_code(
    async_client: AsyncClient,
    *,
    gtin: str,
    serial: str,
    seller_name: str,
    product_name: str,
    sku_suffix: str,
    key: str = "A1B2",
) -> dict[str, object]:
    """Импортирует один код через PDF с настоящей картинкой DataMatrix (путь,
    где живёт I5-2) и возвращает его строку из
    /operations/marking-codes/products/{id}/codes."""
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

    full_cis = build_full_cis(gtin, serial, key=key)
    pdf_bytes = build_datamatrix_label_pdf(gtin=gtin, serial=serial, key=key)
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
        "full_cis": full_cis,
        "bare_prefix": f"01{gtin}21{serial}",
    }


@pytest.mark.asyncio
async def test_pdf_import_decodes_full_code_from_datamatrix_picture(
    async_client: AsyncClient,
) -> None:
    """The actual I5-2 fix: a freshly PDF-imported pool code must carry the
    FULL code decoded from the DataMatrix picture (GS separator + AI(91) key)
    — not a "canonical" short code fabricated from the label's text, which
    never carries the key."""
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
    assert not is_cis_incomplete_for_wb(stored)
    assert stored == seeded["full_cis"]
    assert stored.startswith(seeded["bare_prefix"] + GS_SEPARATOR)


@pytest.mark.asyncio
async def test_pdf_import_without_datamatrix_picture_rejects_without_storing_prefix(
    async_client: AsyncClient,
) -> None:
    """Text-only labels are rejected explicitly and never create a bare CIS."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "No Picture Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "No picture product",
            "sku_code": f"SKU-NOPIC-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    import fitz

    gtin = "04600000000099"
    serial = "NOPICTURESERIAL"
    doc = fitz.open()
    page = doc.new_page(width=164, height=113)
    page.insert_text((12, 24), "Честный знак", fontsize=8)
    page.insert_text((12, 42), f"(01) {gtin}", fontsize=6)
    page.insert_text((12, 54), f"(21) {serial}", fontsize=6)
    pdf_bytes = bytes(doc.tobytes())
    doc.close()

    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "No picture pool", "product_ids": [product_id]}]
            ),
        },
        files=[("files", ("labels.pdf", pdf_bytes, "application/pdf"))],
    )
    assert imp.status_code == 422, imp.text
    assert imp.json()["detail"] == "pdf_no_decodable_datamatrix"

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert codes.json() == []


# ---------------------------------------------------------------------------
# Восстановление накопленных обрезанных кодов (команда CLI поверх этого сервиса)
# ---------------------------------------------------------------------------


async def _truncate_stored_cis_bare(code_id: str) -> str:
    """Симулирует боевые данные I5 (исходный баг): перезаписывает уже
    сохранённый (правильный, полный) код на голую строку без разделителя —
    ровно то, что писал старый импорт до всякого фикса. Возвращает исходное
    (полное) значение, чтобы тест мог сверить восстановленный результат."""
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(code_id))
        assert code is not None
        original_full = code.cis_code
        assert not is_cis_incomplete_for_wb(original_full), (
            "фикстура должна начинать с уже полного кода"
        )
        code.cis_code = original_full.split(GS_SEPARATOR)[0]
        await session.commit()
    return original_full


async def _truncate_stored_cis_gs_only(code_id: str) -> str:
    """Симулирует боевые данные I5-2 (след прошлого, недостаточного
    восстановления): перезаписывает код на "<gtin><serial><GS>" — GS есть, а
    ключа проверки после него нет. Возвращает исходное (полное) значение."""
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(code_id))
        assert code is not None
        original_full = code.cis_code
        assert not is_cis_incomplete_for_wb(original_full), (
            "фикстура должна начинать с уже полного кода"
        )
        bare_prefix = original_full.split(GS_SEPARATOR)[0]
        code.cis_code = f"{bare_prefix}{GS_SEPARATOR}"
        await session.commit()
    return original_full


@pytest.mark.asyncio
async def test_restore_fixes_legacy_truncated_code_via_own_label_artifact(
    async_client: AsyncClient,
) -> None:
    """Основной путь восстановления: у каждой PDF-импортированной строки есть
    своя обрезанная при импорте этикетка (`label_artifact_pdf`) — из неё
    можно распознать картинку DataMatrix заново, не поднимая объектное
    хранилище с исходным файлом наряда."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000011",
        serial="POOLRESTORE0001",
        seller_name="Restore Seller",
        product_name="Restore product",
        sku_suffix="RESTORE",
    )
    original_full = await _truncate_stored_cis_bare(seeded["code_id"])

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert report.scanned == 1
    assert report.restored == 1
    assert report.counts_by_outcome() == {"restored": 1}
    assert report.skipped_not_available == 0
    [row] = report.rows
    assert row.outcome == "restored"

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code == original_full


@pytest.mark.asyncio
async def test_restore_fixes_code_left_by_prior_insufficient_restore(
    async_client: AsyncClient,
) -> None:
    """I5-2's core regression case: a row a *prior* restore pass already
    "fixed" by appending a bare GS separator with no verification key — this
    run must recognize that as still incomplete and finish the job using the
    real DataMatrix picture, not skip it as already-restored."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000017",
        serial="POOLPRIORFIX001",
        seller_name="Prior Fix Seller",
        product_name="Prior fix product",
        sku_suffix="PRIORFIX",
    )
    original_full = await _truncate_stored_cis_gs_only(seeded["code_id"])

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert report.scanned == 1
    assert report.restored == 1
    [row] = report.rows
    assert row.outcome == "restored"

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code == original_full
        assert not is_cis_incomplete_for_wb(code.cis_code)


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
    original_full = await _truncate_stored_cis_bare(seeded["code_id"])

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
async def test_restore_does_not_touch_codes_that_already_have_full_structure(
    async_client: AsyncClient,
) -> None:
    """A code imported normally (picture decoded successfully) already
    carries GS + verification key — restore must not even count it as a
    candidate, let alone rewrite it."""
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
    target_full = seeded["full_cis"]
    assert seeded["cis_code"] == target_full  # sanity: the two rows collide on purpose

    # Second row: a legacy-truncated duplicate of the very same GTIN+serial,
    # with its own label artifact (same DataMatrix picture) that would
    # restore to the same full code already held by `seeded`.
    dup_label_pdf = build_datamatrix_label_pdf(
        gtin="04600000000014", serial="POOLCONFLICT0001", key="A1B2"
    )
    async with SessionLocal() as session:
        dup = MarkingCode(
            tenant_id=uuid.UUID(seeded["tenant_id"]),
            seller_id=uuid.UUID(seeded["seller_id"]),
            product_id=uuid.UUID(seeded["product_id"]),
            import_batch_id=uuid.UUID(seeded["import_id"]),
            cis_code=str(seeded["bare_prefix"]),
            source="pool",
            label_artifact_pdf=dup_label_pdf,
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
        assert dup_after.cis_code == seeded["bare_prefix"]  # untouched, not overwritten


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
    await _truncate_stored_cis_bare(seeded["code_id"])

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
        assert is_cis_incomplete_for_wb(code.cis_code)  # still untouched/truncated


@pytest.mark.asyncio
async def test_restore_does_not_touch_code_whose_picture_belongs_to_different_product(
    async_client: AsyncClient,
) -> None:
    """I5-2 item 2: the restored value must belong to the *same* product —
    matched by "01<GTIN>21<serial>" prefix against what's already stored. If
    a code's own label artifact somehow carries a DataMatrix for a different
    GTIN+serial (data mishap, wrong crop, corrupted upload), restore must
    refuse to touch it rather than silently overwrite with the wrong
    product's code — and the report must explain why."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000018",
        serial="POOLMISMATCH0001",
        seller_name="Mismatch Seller",
        product_name="Mismatch product",
        sku_suffix="MISMATCH",
    )
    await _truncate_stored_cis_bare(seeded["code_id"])

    # Заменяем собственную этикетку кода на картинку ДРУГОГО товара — так,
    # будто при импорте перепутались артефакты (не тот кроп попал не в ту
    # строку).
    wrong_product_pdf = build_datamatrix_label_pdf(
        gtin="04600000000099", serial="TOTALLYDIFFERENT", key="Z9Z9"
    )
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        code.label_artifact_pdf = wrong_product_pdf
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
    # На собственной этикетке штрихкод чужого товара не совпал с ожидаемым
    # префиксом ("не найден"), файла наряда для повторной попытки тоже нет —
    # значит финальный исход "no_source_pdf".
    assert row.outcome == "no_source_pdf"

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code == seeded["bare_prefix"]  # untouched


@pytest.mark.asyncio
async def test_restore_does_not_touch_codes_bound_to_an_order(
    async_client: AsyncClient,
) -> None:
    """I5-2 item 4 (находка ревью): коды, привязанные к заказу, не трогаем —
    при привязке значение копируется отдельной строкой в
    `FbsOrderMarking.value`, и переписывать `cis_code` после этого значило бы
    разъехаться с уже скопированным значением. Даже когда у кода есть
    рабочая собственная этикетка, из которой полный код *можно* было бы
    восстановить, статус "applied" должен полностью исключить его из
    выборки — код не должен появиться ни в `rows`, ни быть переписанным, а
    только попасть в отдельный счётчик `skipped_not_available`."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000019",
        serial="POOLAPPLIED00001",
        seller_name="Applied Seller",
        product_name="Applied product",
        sku_suffix="APPLIED",
    )
    await _truncate_stored_cis_bare(seeded["code_id"])

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        code.status = STATUS_APPLIED
        await session.commit()
        untouched_value = code.cis_code

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"])
        )
        await session.commit()

    assert report.scanned == 0
    assert report.restored == 0
    assert report.rows == []
    assert report.skipped_not_available == 1

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code == untouched_value
        assert code.status == STATUS_APPLIED


@pytest.mark.asyncio
async def test_restore_dry_run_reports_without_writing(async_client: AsyncClient) -> None:
    """Режим примерки: считает и репортит, как обычный прогон, но не пишет
    в базу — повторный dry-run находит тех же кандидатов."""
    seeded = await _import_one_pdf_code(
        async_client,
        gtin="04600000000020",
        serial="POOLDRYRUN000001",
        seller_name="Dry Run Seller",
        product_name="Dry run product",
        sku_suffix="DRYRUN",
    )
    original_full = await _truncate_stored_cis_bare(seeded["code_id"])

    async with SessionLocal() as session:
        report = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"]), dry_run=True
        )
        await session.commit()

    assert report.scanned == 1
    assert report.restored == 1
    [row] = report.rows
    assert row.outcome == "restored"

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(seeded["code_id"]))
        assert code is not None
        assert code.cis_code != original_full
        assert is_cis_incomplete_for_wb(code.cis_code)

    # Повторный dry-run видит того же кандидата — прошлый прогон ничего не записал.
    async with SessionLocal() as session:
        second = await restore_truncated_pool_cis_codes(
            session, tenant_id=uuid.UUID(seeded["tenant_id"]), dry_run=True
        )
    assert second.scanned == 1
    assert second.restored == 1


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
    в конец GS-разделитель (и то, что после него) не должен ломать эту
    подстрочную проверку, потому что важные для оператора цифры всё ещё
    находятся строго перед ним, а не строго в конце строки."""
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
    assert GS_SEPARATOR in stored_cis

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


# ---------------------------------------------------------------------------
# Распознавание DataMatrix напрямую (не через HTTP-импорт): точность на
# настоящей картинке, сгенерированной той же библиотекой, что и прод-декодер.
# ---------------------------------------------------------------------------


def test_decode_datamatrix_from_generated_png_roundtrips_exact_bytes() -> None:
    """Sanity-check хелпера: то, что кодируем, то и должны получить обратно —
    включая настоящий байт GS-разделителя, а не текстовый плейсхолдер."""
    import fitz

    from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page

    full = build_full_cis(_REAL_GTIN, _REAL_SERIAL, key=_REAL_KEY, crypto_tail=_REAL_CRYPTO_TAIL)
    png_bytes = encode_datamatrix_png(full)

    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=200)
        page.insert_image(fitz.Rect(10, 10, 190, 190), stream=png_bytes)
        results = decode_datamatrix_codes_on_pdf_page(doc[0])
    finally:
        doc.close()

    assert len(results) == 1
    assert results[0].value == full
    assert GS_SEPARATOR in results[0].value


@pytest.mark.asyncio
async def test_pdf_import_pairs_each_picture_with_its_own_label_on_multi_label_page(
    async_client: AsyncClient,
) -> None:
    """Two labels, two different DataMatrix pictures on one page — each
    imported code must end up with the picture that actually belongs to it,
    not swapped."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Two Label Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Two label product",
            "sku_code": f"SKU-TWOLABEL-{uuid.uuid4().hex[:6]}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    gtin = "04600000000021"
    serial_a = "TWOLABELA000001"
    serial_b = "TWOLABELB000002"
    pdf_bytes = build_two_datamatrix_label_pdf(gtin=gtin, serial_a=serial_a, serial_b=serial_b)

    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Two label pool", "product_ids": [product_id]}]
            ),
        },
        files=[("files", ("labels.pdf", pdf_bytes, "application/pdf"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 2

    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    rows = {row["cis_code"] for row in codes.json()}
    assert rows == {
        build_full_cis(gtin, serial_a),
        build_full_cis(gtin, serial_b),
    }
