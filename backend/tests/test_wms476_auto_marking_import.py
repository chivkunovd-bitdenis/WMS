from __future__ import annotations

import asyncio
import json
import uuid

import fitz
import pytest
from httpx import AsyncClient
from marking_datamatrix_test_helpers import encode_datamatrix_png
from sqlalchemy import select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import MarkingCode, MarkingPool
from app.services.marking_datamatrix_service import decode_datamatrix_codes_on_pdf_page
from app.services.marking_label_artifact_service import extract_label_artifacts_from_pdf


def _damaged_matrix_png() -> bytes:
    size = 80
    pixels = bytes(
        0
        if (
            x // 4 == 0
            or y // 4 == 19
            or (y // 4 == 0 and x // 4 % 2 == 0)
            or (x // 4 == 19 and y // 4 % 2 == 0)
            or ((x // 4) * 17 + (y // 4) * 31 + (x // 4) * (y // 4)) % 7 < 3
        )
        else 255
        for y in range(size)
        for x in range(size)
    )
    pixmap = fitz.Pixmap(fitz.csGRAY, size, size, pixels, 0)
    return bytes(pixmap.tobytes("png"))


def _label_pdf(cis: str, *, article: str | None, size: str | None = None) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=220, height=220)
        y = 18
        if article is not None:
            page.insert_text((10, y), f"SKU: {article}", fontsize=8)
            y += 12
        if size is not None:
            page.insert_text((10, y), f"Size: {size}", fontsize=8)
        page.insert_image(fitz.Rect(30, 45, 190, 205), stream=encode_datamatrix_png(cis))
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _mixed_readable_and_unreadable_pdf(cis: str, *, damaged_first: bool = False) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=440, height=220)
        page.draw_rect(fitz.Rect(2, 2, 218, 218))
        page.draw_rect(fitz.Rect(222, 2, 438, 218))
        readable_x = 250 if damaged_first else 30
        damaged_x = 30 if damaged_first else 250
        readable_text_x = 230 if damaged_first else 10
        damaged_text_x = 10 if damaged_first else 230
        page.insert_text((readable_text_x, 18), "SKU: ARTICLE-A", fontsize=8)
        page.insert_text((readable_text_x, 30), "Size: M", fontsize=8)
        page.insert_image(
            fitz.Rect(readable_x, 45, readable_x + 160, 205),
            stream=encode_datamatrix_png(cis),
        )
        page.insert_text((damaged_text_x, 18), "SKU: DAMAGED", fontsize=8)
        page.insert_image(
            fitz.Rect(damaged_x, 45, damaged_x + 160, 205),
            stream=_damaged_matrix_png(),
        )
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _single_damaged_label_pdf() -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=220, height=220)
        page.draw_rect(fitz.Rect(2, 2, 218, 218))
        page.insert_text((10, 18), "SKU: DAMAGED-ONLY", fontsize=8)
        page.insert_image(fitz.Rect(30, 45, 190, 205), stream=_damaged_matrix_png())
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _rasterize_pdf_to_one_image(content: bytes) -> bytes:
    source = fitz.open(stream=content, filetype="pdf")
    output = fitz.open()
    try:
        source_page = source[0]
        pixmap = source_page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
        page = output.new_page(width=source_page.rect.width, height=source_page.rect.height)
        page.insert_image(page.rect, stream=pixmap.tobytes("png"))
        return bytes(output.tobytes())
    finally:
        output.close()
        source.close()


def _label_with_square_logo_pdf(cis: str) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=260, height=220)
        page.draw_rect(fitz.Rect(2, 2, 258, 218))
        logo = fitz.Pixmap(fitz.csGRAY, 40, 40, bytes([0] * 1600), 0)
        page.insert_image(
            fitz.Rect(20, 20, 60, 60),
            stream=bytes(logo.tobytes("png")),
        )
        page.insert_image(fitz.Rect(70, 45, 230, 205), stream=encode_datamatrix_png(cis))
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _square_logo_only_pdf() -> bytes:
    size = 80
    pixels = bytes(
        0 if (x // 8 + y // 8) % 2 == 0 else 255
        for y in range(size)
        for x in range(size)
    )
    logo = fitz.Pixmap(fitz.csGRAY, size, size, pixels, 0)
    doc = fitz.open()
    try:
        page = doc.new_page(width=220, height=220)
        page.insert_text((10, 18), "SKU: PRODUCT-IMAGE", fontsize=8)
        page.insert_image(
            fitz.Rect(30, 45, 190, 205),
            stream=bytes(logo.tobytes("png")),
        )
        return bytes(doc.tobytes())
    finally:
        doc.close()


def _mixed_readable_and_vector_damaged_pdf(cis: str) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=440, height=220)
        page.draw_rect(fitz.Rect(2, 2, 218, 218))
        page.draw_rect(fitz.Rect(222, 2, 438, 218))
        page.insert_image(fitz.Rect(30, 45, 190, 205), stream=encode_datamatrix_png(cis))
        module = 7
        start_x = 260
        start_y = 55
        for row in range(18):
            for column in range(18):
                if (
                    column == 0
                    or row == 17
                    or (row == 0 and column % 2 == 0)
                    or (column == 17 and row % 2 == 0)
                    or (row * 17 + column * 31 + row * column) % 7 < 3
                ):
                    rect = fitz.Rect(
                        start_x + column * module,
                        start_y + row * module,
                        start_x + (column + 1) * module,
                        start_y + (row + 1) * module,
                    )
                    page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0), width=0)
        return bytes(doc.tobytes())
    finally:
        doc.close()


def test_artifact_extractor_keeps_only_real_or_damaged_matrix_regions() -> None:
    cis = "010460000000000121WMS476-ARTIFACT-RAW\x1d91ABCD\x1d92RAW+/=TAIL"

    with_logo = extract_label_artifacts_from_pdf(_label_with_square_logo_pdf(cis))
    assert [(row.cis, row.code_valid) for row in with_logo] == [(cis, True)]
    assert extract_label_artifacts_from_pdf(_square_logo_only_pdf()) == []

    damaged_only = extract_label_artifacts_from_pdf(_single_damaged_label_pdf())
    assert len(damaged_only) == 1
    assert damaged_only[0].cis == ""
    assert damaged_only[0].code_valid is False

    mixed_vector = extract_label_artifacts_from_pdf(
        _mixed_readable_and_vector_damaged_pdf(cis),
    )
    assert [(row.cis, row.code_valid) for row in mixed_vector] == [
        (cis, True),
        ("", False),
    ]


def test_artifact_extractor_splits_one_image_page_and_preserves_source_order() -> None:
    cis = "010460000000000121WMS476-RASTER-MIXED-01"
    rasterized = _rasterize_pdf_to_one_image(
        _mixed_readable_and_unreadable_pdf(cis, damaged_first=True),
    )

    artifacts = extract_label_artifacts_from_pdf(rasterized)

    assert [(row.cis, row.code_valid) for row in artifacts] == [
        ("", False),
        (cis, True),
    ]
    label_codes: list[list[str]] = []
    for artifact in artifacts:
        with fitz.open(stream=artifact.label_pdf, filetype="pdf") as label_doc:
            assert label_doc[0].rect.width < 300
            label_codes.append(
                [
                    item.value
                    for page in label_doc
                    for item in decode_datamatrix_codes_on_pdf_page(page)
                ],
            )
    assert label_codes == [[], [cis]]


async def _product(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: str,
    sku: str,
    barcode: str,
    size: str,
    vendor_code: str | None = None,
) -> str:
    response = await client.post(
        "/products",
        headers=headers,
        json={
            "name": f"Product {sku}",
            "sku_code": sku,
            "seller_id": seller_id,
            "wb_barcode": barcode,
            "wb_size": size,
            "wb_vendor_code": vendor_code,
            "requires_honest_sign": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_auto_match_combines_shared_article_with_gtin(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "WMS476 combined", "email": f"wms476-c-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    matched_product_id = await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="FAMILY-M",
        barcode="04608888888881",
        size="M",
        vendor_code="FAMILY",
    )
    await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="FAMILY-L",
        barcode="04608888888882",
        size="L",
        vendor_code="FAMILY",
    )
    cis = "010460888888888121COMBINED-MATCH-01"
    response = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=headers,
        data={"seller_id": seller_id, "request_id": str(uuid.uuid4())},
        files=[("files", ("family.pdf", _label_pdf(cis, article="FAMILY"), "application/pdf"))],
    )

    assert response.status_code == 200, response.text
    assert [(row["product_id"], row["loaded_count"]) for row in response.json()["groups"]] == [
        (matched_product_id, 1),
    ]
    assert response.json()["unmatched"] == []


@pytest.mark.asyncio
async def test_auto_match_treats_one_size_label_as_wb_size_zero_only(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "WMS476 One Size", "email": f"wms476-os-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    one_size_product_id = await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="GARMENT-ONE-SIZE",
        barcode="04605555555551",
        size="0",
        vendor_code="GARMENT",
    )
    await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="GARMENT-M",
        barcode="04605555555552",
        size="M",
        vendor_code="GARMENT",
    )
    one_size_cis = "010460000000020121ONE-SIZE-WMS476-01"
    other_size_cis = "010460000000020221OTHER-SIZE-WMS476-1"
    missing_size_cis = "010460000000020321NO-SIZE-WMS476-0001"
    gtin_only_cis = "010460555555555121GTIN-ONLY-WMS476-01"

    response = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=headers,
        data={"seller_id": seller_id, "request_id": str(uuid.uuid4())},
        files=[
            (
                "files",
                (
                    "one-size.pdf",
                    _label_pdf(one_size_cis, article="GARMENT", size="One Size"),
                    "application/pdf",
                ),
            ),
            (
                "files",
                (
                    "other-size.pdf",
                    _label_pdf(other_size_cis, article="GARMENT", size="L"),
                    "application/pdf",
                ),
            ),
            (
                "files",
                (
                    "missing-size.pdf",
                    _label_pdf(missing_size_cis, article="GARMENT"),
                    "application/pdf",
                ),
            ),
            (
                "files",
                (
                    "gtin-only.pdf",
                    _label_pdf(gtin_only_cis, article=None, size="One Size"),
                    "application/pdf",
                ),
            ),
        ],
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(row["product_id"], row["loaded_count"]) for row in body["groups"]] == [
        (one_size_product_id, 1),
    ]
    unmatched_by_code = {row["marking_code"]: row for row in body["unmatched"]}
    assert unmatched_by_code[other_size_cis]["size"] == "L"
    assert "размер не совпадает" in unmatched_by_code[other_size_cis]["reason"].lower()
    assert unmatched_by_code[missing_size_cis]["size"] is None
    assert "неоднозначно" in unmatched_by_code[missing_size_cis]["reason"].lower()
    assert unmatched_by_code[gtin_only_cis]["article"] is None
    assert unmatched_by_code[gtin_only_cis]["size"] == "One Size"
    assert "размер не совпадает" in unmatched_by_code[gtin_only_cis]["reason"].lower()


@pytest.mark.asyncio
async def test_lost_assignment_response_reuses_result_and_residual_is_authoritative(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "WMS476 recovery", "email": f"wms476-r-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    first_product_id = await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="RECOVERY-A",
        barcode="04606666666661",
        size="M",
    )
    second_product_id = await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="RECOVERY-B",
        barcode="04606666666662",
        size="L",
    )
    codes = [
        "010460000000010121RECOVERY-ASSIGN-01",
        "010460000000010221RECOVERY-ASSIGN-02",
        "010460000000010321RECOVERY-ASSIGN-03",
    ]
    files = [
        ("files", (f"{index}.pdf", _label_pdf(cis, article="UNKNOWN"), "application/pdf"))
        for index, cis in enumerate(codes)
    ]
    auto_request_id = str(uuid.uuid4())
    automatic = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=headers,
        data={"seller_id": seller_id, "request_id": auto_request_id},
        files=files,
    )
    assert automatic.status_code == 200, automatic.text
    automatic_body = automatic.json()
    keys = [row["key"] for row in automatic_body["unmatched"]]
    assert keys == ["0", "1", "2"]

    # The browser may lose the response after the transaction commits. Repeating
    # the same automatic attempt after a full reload must reveal the saved outcome.
    repeated_auto = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=headers,
        data={"seller_id": seller_id, "request_id": auto_request_id},
        files=files,
    )
    assert repeated_auto.status_code == 200, repeated_auto.text
    assert repeated_auto.json() == automatic_body

    assign_request_id = str(uuid.uuid4())
    assignment_data = {
        "seller_id": seller_id,
        "request_id": assign_request_id,
        "product_id": first_product_id,
        "row_keys_json": json.dumps(keys[:2]),
    }
    committed = await async_client.post(
        "/operations/marking-codes/import/assign",
        headers=headers,
        data=assignment_data,
        files=files,
    )
    assert committed.status_code == 200, committed.text

    recovered = await async_client.post(
        "/operations/marking-codes/import/assign",
        headers=headers,
        data=assignment_data,
        files=files,
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == committed.json()
    assert recovered.json()["assigned_keys"] == keys[:2]

    changed_product = await async_client.post(
        "/operations/marking-codes/import/assign",
        headers=headers,
        data={**assignment_data, "product_id": second_product_id},
        files=files,
    )
    assert changed_product.status_code == 409
    assert changed_product.json()["detail"] == "import_request_conflict"

    stale_residual = await async_client.post(
        "/operations/marking-codes/import/unmatched-pdf",
        headers=headers,
        data={"seller_id": seller_id, "row_keys_json": json.dumps(keys)},
        files=files,
    )
    assert stale_residual.status_code == 200, stale_residual.text
    with fitz.open(stream=stale_residual.content, filetype="pdf") as residual_doc:
        assert residual_doc.page_count == 1
        assert [
            item.value
            for page in residual_doc
            for item in decode_datamatrix_codes_on_pdf_page(page)
        ] == [codes[2]]

    next_assignment = await async_client.post(
        "/operations/marking-codes/import/assign",
        headers=headers,
        data={
            "seller_id": seller_id,
            "request_id": str(uuid.uuid4()),
            "product_id": second_product_id,
            "row_keys_json": json.dumps(keys[2:]),
        },
        files=files,
    )
    assert next_assignment.status_code == 200, next_assignment.text
    assert next_assignment.json()["assigned_keys"] == keys[2:]


@pytest.mark.asyncio
async def test_auto_import_partial_assignment_and_residual_pdf(
    async_client: AsyncClient,
) -> None:
    headers = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "WMS476 seller", "email": f"wms476-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    other_seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "WMS476 other", "email": f"wms476-o-{uuid.uuid4().hex[:8]}@example.com"},
    )
    other_seller_id = other_seller.json()["id"]

    matched_product_id = await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="ARTICLE-A",
        barcode="04609999999999",
        size="M",
    )
    await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="VARIANT-M",
        barcode="04608888888881",
        size="M",
        vendor_code="FAMILY",
    )
    await _product(
        async_client,
        headers,
        seller_id=seller_id,
        sku="VARIANT-L",
        barcode="04608888888882",
        size="L",
        vendor_code="FAMILY",
    )
    await _product(
        async_client,
        headers,
        seller_id=other_seller_id,
        sku="OTHER-SELLER-ONLY",
        barcode="04607777777777",
        size="S",
    )

    damaged_only_pdf = _single_damaged_label_pdf()
    damaged_preview = await async_client.post(
        "/operations/marking-codes/import/preview",
        headers=headers,
        data={"seller_id": seller_id},
        files=[("files", ("damaged-only.pdf", damaged_only_pdf, "application/pdf"))],
    )
    assert damaged_preview.status_code == 200, damaged_preview.text
    assert damaged_preview.json() == {
        "groups": [],
        "total_codes": 0,
        "invalid_count": 1,
        "duplicates_in_file": 0,
    }
    damaged_auto = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=headers,
        data={"seller_id": seller_id, "request_id": str(uuid.uuid4())},
        files=[("files", ("damaged-only.pdf", damaged_only_pdf, "application/pdf"))],
    )
    assert damaged_auto.status_code == 200, damaged_auto.text
    assert damaged_auto.json()["groups"] == []
    assert len(damaged_auto.json()["unmatched"]) == 1
    assert damaged_auto.json()["unmatched"][0]["eligible_for_assignment"] is False

    matched_cis = "010460000000000121MATCHED-WMS476-0001"
    ambiguous_cis = "010460000000000221AMBIGUOUS-WMS476-01"
    foreign_cis = "010460000000000321FOREIGN-WMS476-0001"
    files = [
        (
            "files",
            (
                "01-mixed.pdf",
                _mixed_readable_and_unreadable_pdf(matched_cis, damaged_first=True),
                "application/pdf",
            ),
        ),
        (
            "files",
            ("02-ambiguous.pdf", _label_pdf(ambiguous_cis, article="FAMILY"), "application/pdf"),
        ),
        (
            "files",
            (
                "03-other-seller.pdf",
                _label_pdf(foreign_cis, article="OTHER-SELLER-ONLY", size="S"),
                "application/pdf",
            ),
        ),
    ]

    seller_email = f"wms476-scope-{uuid.uuid4().hex[:8]}@example.com"
    created_account = await async_client.post(
        "/auth/seller-accounts",
        headers=headers,
        json={
            "seller_id": seller_id,
            "email": seller_email,
            "password": "password123",
        },
    )
    assert created_account.status_code == 201, created_account.text
    seller_login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    assert seller_login.status_code == 200, seller_login.text
    seller_headers = {
        "Authorization": f"Bearer {seller_login.json()['access_token']}"
    }
    seller_scope_response = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=seller_headers,
        data={"seller_id": other_seller_id, "request_id": str(uuid.uuid4())},
        files=[files[-1]],
    )
    assert seller_scope_response.status_code == 200, seller_scope_response.text
    assert seller_scope_response.json()["groups"] == []
    assert seller_scope_response.json()["unmatched"][0]["reason"] == (
        "Не найден артикул в каталоге селлера"
    )

    request_id = str(uuid.uuid4())
    response, concurrent_response = await asyncio.gather(
        async_client.post(
            "/operations/marking-codes/import/auto",
            headers=headers,
            data={"seller_id": seller_id, "request_id": request_id},
            files=files,
        ),
        async_client.post(
            "/operations/marking-codes/import/auto",
            headers=headers,
            data={"seller_id": seller_id, "request_id": request_id},
            files=files,
        ),
    )
    assert response.status_code == 200, response.text
    assert concurrent_response.status_code == 200, concurrent_response.text
    body = response.json()
    assert concurrent_response.json() == body
    assert [(row["product_id"], row["loaded_count"]) for row in body["groups"]] == [
        (matched_product_id, 1)
    ]
    assert len(body["unmatched"]) == 3
    assert [row["article"] for row in body["unmatched"]] == [
        "DAMAGED",
        "FAMILY",
        "OTHER-SELLER-ONLY",
    ]
    assert [row["eligible_for_assignment"] for row in body["unmatched"]] == [
        False,
        True,
        True,
    ]
    assert "повреждён" in body["unmatched"][0]["reason"].lower()
    assert "неоднозначно" in body["unmatched"][1]["reason"].lower()
    assert "не найден" in body["unmatched"][2]["reason"].lower()

    repeated = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=headers,
        data={"seller_id": seller_id, "request_id": request_id},
        files=files,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == body

    conflicting_retry = await async_client.post(
        "/operations/marking-codes/import/auto",
        headers=headers,
        data={"seller_id": seller_id, "request_id": request_id},
        files=files[:-1],
    )
    assert conflicting_retry.status_code == 409
    assert conflicting_retry.json()["detail"] == "import_request_conflict"

    row_keys = [row["key"] for row in body["unmatched"]]
    eligible_keys = [
        row["key"] for row in body["unmatched"] if row["eligible_for_assignment"]
    ]
    residual = await async_client.post(
        "/operations/marking-codes/import/unmatched-pdf",
        headers=headers,
        data={"seller_id": seller_id, "row_keys_json": json.dumps(row_keys)},
        files=files,
    )
    assert residual.status_code == 200, residual.text
    with fitz.open(stream=residual.content, filetype="pdf") as doc:
        assert doc.page_count == 3
        residual_codes = {
            item.value
            for page in doc
            for item in decode_datamatrix_codes_on_pdf_page(page)
        }
    assert residual_codes == {ambiguous_cis, foreign_cis}
    assert matched_cis not in residual_codes

    assign_request_id = str(uuid.uuid4())
    assign = await async_client.post(
        "/operations/marking-codes/import/assign",
        headers=headers,
        data={
            "seller_id": seller_id,
            "request_id": assign_request_id,
            "product_id": matched_product_id,
            "row_keys_json": json.dumps(eligible_keys),
        },
        files=files,
    )
    assert assign.status_code == 200, assign.text
    assigned_body = assign.json()
    assert assigned_body["assigned_keys"] == eligible_keys
    assert assigned_body["product"]["loaded_count"] == 2

    repeated_assign = await async_client.post(
        "/operations/marking-codes/import/assign",
        headers=headers,
        data={
            "seller_id": seller_id,
            "request_id": assign_request_id,
            "product_id": matched_product_id,
            "row_keys_json": json.dumps(eligible_keys),
        },
        files=files,
    )
    assert repeated_assign.status_code == 200, repeated_assign.text
    assert repeated_assign.json() == assigned_body

    current_residual = await async_client.post(
        "/operations/marking-codes/import/unmatched-pdf",
        headers=headers,
        data={"seller_id": seller_id, "row_keys_json": json.dumps(row_keys[:1])},
        files=files,
    )
    assert current_residual.status_code == 200, current_residual.text
    with fitz.open(stream=current_residual.content, filetype="pdf") as doc:
        assert doc.page_count == 1
        assert [
            item.value
            for page in doc
            for item in decode_datamatrix_codes_on_pdf_page(page)
        ] == []

    async with SessionLocal() as session:
        codes = list(
            (
                await session.scalars(
                    select(MarkingCode).where(MarkingCode.seller_id == uuid.UUID(seller_id))
                )
            ).all()
        )
        assert {code.cis_code for code in codes} == {matched_cis, ambiguous_cis, foreign_cis}
        assert {code.product_id for code in codes} == {uuid.UUID(matched_product_id)}
        assert all(code.pool_id is None for code in codes)
        pools = list(
            (
                await session.scalars(
                    select(MarkingPool).where(MarkingPool.seller_id == uuid.UUID(seller_id))
                )
            ).all()
        )
        assert pools == []
