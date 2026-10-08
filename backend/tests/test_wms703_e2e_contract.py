"""Keep the evidence behind the ten PR #408 E2E baselines reviewable.

These source-contract checks are intentionally narrow: they guard named E2E
cases against accidental removal, weakening, or skipping. They do not replace
the browser tests or prove that the application behaves correctly at runtime.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CaseContract:
    case_id: str
    path: str
    title: str
    required: tuple[str, ...]
    file_required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


CASES = (
    CaseContract(
        "E1",
        "frontend/tests-e2e/auth-dual-portal-sessions.spec.ts",
        "FF admin and staff opening /seller/products see human access denied",
        (
            "await expectAccessDeniedOnSellerProductsWithFfToken(page)",
            "await clientRouteTo(page, '/seller/products')",
            "await expectSellerAccessDeniedWithFfToken(page)",
            "await storeFulfillmentTokenOnly(page, staffToken)",
        ),
        (
            "getByTestId('ff-access-denied')",
            "нет сессии селлера",
            "Войти как селлер",
            "getByTestId('seller-products-table')).toHaveCount(0)",
            "localStorage.getItem('wms_token_ff')",
        ),
    ),
    CaseContract(
        "E2",
        "frontend/tests-e2e/ff-fbs-stock-sync.spec.ts",
        "fbs seller warehouses: row binding, manual sync, status panel",
        (
            "await expect(row).toContainText('E2E Seller Warehouse')",
            "await expect(row).toContainText('Moscow')",
            "await expect(row).toContainText('WB ID 501001')",
            "await expect(page.getByTestId('fbs-stock-add-binding')).toHaveCount(0)",
            "await expect(row).toContainText('публикация выключена')",
            "page.on('request'",
            "syncRequestsBeforeToggle.push",
            "await expect(syncRequestsBeforeToggle).toHaveLength(0)",
            "page.off('request', trackSyncBeforeToggle)",
            "row.getByTestId('fbs-stock-sync-toggle').click()",
            "await expect(row).toContainText('публикация включена')",
            "r.url().includes('/stocks/sync')",
            "await expect(page.getByTestId('fbs-stock-status-panel')).toBeVisible()",
            "r.url().includes('/warehouse-bindings/501001')",
        ),
    ),
    CaseContract(
        "E3",
        "frontend/tests-e2e/ff-products.spec.ts",
        "ff products: catalog shows current fields, stock and seller filters",
        (
            "const headers = (await tableHead.locator('th').allTextContents())",
            "'Артикул продавца'",
            "'Селлер'",
            "'Остаток'",
            "'ТЗ'",  # noqa: RUF001
            "'ЧЗ'",
            "'Резервы'",
            "expect(headers).not.toContain('WB/nmId')",
            "await expect(alphaRow.locator('td').nth(2)).toContainText('ART-A')",
            "await expect(alphaRow.locator('td').nth(3)).toContainText(skuA)",
            "await expect(alphaRow.locator('td').nth(4)).toContainText(barcodeA)",
            "await expect(alphaRow.locator('td').nth(5)).toHaveText('46')",
            "await expect(alphaRow.locator('td').nth(6)).toHaveText('E2E Seller A')",
            "await expect(betaRow.locator('td').nth(6)).toHaveText('E2E Seller B')",
            "await expect(privateRow.locator('td').nth(6)).toHaveText('E2E Seller A')",
            "await expect(page.getByTestId('ff-product-row')).toHaveCount(3)",
            "ff-catalog-stock-in-storage-${product.id}",
            "'В ячейках 0'",  # noqa: RUF001
            "ff-catalog-stock-on-hand-${product.id}",
            "'На ФФ 0'",  # noqa: RUF001
            "ff-catalog-stock-free-fbo-${product.id}",
            "'Свободный FBO 0'",
            "page.getByTestId('ff-catalog-search')",
            "await search.fill(skuA)",
            "page.getByTestId('ff-catalog-seller-filter')",
            "page.getByRole('option', { name: 'E2E Seller A' }).click()",
            "page.getByRole('option', { name: 'Все селлеры' }).click()",  # noqa: RUF001
        ),
    ),
    CaseContract(
        "E4",
        "frontend/tests-e2e/ff-products.spec.ts",
        "ff products: marking icon shows count and opens honest sign product card",
        (
            "requires_honest_sign: true",
            "const cis1 =",
            "const cis2 =",
            "Buffer.from(`cis\\n${cis1}\\n${cis2}`)",
            "row.getByTestId(`ff-honest-sign-status-${productId}`)",
            "await expect(honestSignChip).toHaveCount(1)",
            "await expect(honestSignChip).toBeVisible()",
            "await expect(markingLink).toContainText('2')",
            "await markingLink.click()",
            "ff-honest-sign-product-page",
            "new URL(page.url()).pathname).toBe(`/app/ff/honest-sign/product/${productId}`)",
            "ff-honest-sign-product-codes",
            "await expect(codeRows).toHaveCount(2)",
            "const cis1Row = codeRows.filter({ hasText: cis1 })",
            "const cis2Row = codeRows.filter({ hasText: cis2 })",
            "await expect(cis1Row).toHaveCount(1)",
            "await expect(cis2Row).toHaveCount(1)",
            "expect(await cis1Row.getAttribute('data-testid')).not.toBe(",
            "await cis2Row.getAttribute('data-testid')",
        ),
    ),
    CaseContract(
        "E5",
        "frontend/tests-e2e/ff-products.spec.ts",
        "ff products: import tz xlsx creates catalog products with packaging",
        (
            "ff-tz-import-preview-table')).toContainText('123456789')",
            "ff-tz-import-preview-table')).toContainText('E2E merged TZ')",
            "ff-tz-import-preview-table')).toContainText('E2E-ART-48')",
            "await expect(page.getByTestId('ff-products-import-notice')).toContainText(",
            "page.request.get('/api/products', { headers: h })",
            "product.seller_id === sellerId && product.sku_code === 'E2E-ART-46'",
            "product.seller_id === sellerId && product.sku_code === 'E2E-ART-48'",
            "product46?.wb_nm_id).toBe(123456789)",
            "product46?.wb_size).toBe('46')",
            "product46?.wb_barcode).toBe('2039000000001')",
            "product46?.packaging_instructions).toBe('E2E merged TZ')",
            "product48?.wb_nm_id).toBe(123456789)",
            "product48?.wb_size).toBe('48')",
            "product48?.wb_barcode).toBe('2039000000002')",
            "product48?.packaging_instructions).toBe('E2E merged TZ')",
            "await expect(page.getByTestId('ff-product-row')).toHaveCount(2)",
            "await expect(row46.locator('td').nth(4)).toContainText('2039000000001')",
            "await expect(row48.locator('td').nth(4)).toContainText('2039000000002')",
            "ff-packaging-edit-${product46?.id}",
            "ff-packaging-edit-${product48?.id}",
        ),
    ),
    CaseContract(
        "E6",
        "frontend/tests-e2e/ff-reception-sorting.spec.ts",
        "ff verify posts to sorting zone; sorting queue and product columns",
        (
            "expect(row?.quantity_in_sorting).toBe(4)",
            (
                "await expect(page.getByTestId('ff-inbound-queue-sorting-qty').first())"
                ".toHaveText('4')"
            ),
            "await expect(page.getByTestId('ff-sorting-all-done')).toBeVisible()",
            "expect(doneRow?.quantity_in_sorting).toBe(0)",
            "expect(doneRow?.quantity_in_storage).toBe(4)",
            "await expect(catalogHead).toContainText('Артикул продавца')",
        ),
    ),
    CaseContract(
        "E7",
        "frontend/tests-e2e/ff-reports.spec.ts",
        "FF reports: section opens and shows movement summary for a product with intake",
        (
            "fulfillInboundViaBoxScans(page.request, adminHeaders, rid, boxes, seed.sku, [6])",
            "const destinationRes = await page.request.post("
            "`/api/warehouses/${seed.warehouseId}/locations`",
            "const destinationId = String(((await destinationRes.json()) as { id: string }).id)",
            "page.request.patch(`${INBOUND_API}/${rid}/lines/",
            "storage_location_id: destinationId",
            "expect(locationAssignment.ok()).toBeTruthy()",
            "const movementPath = `${INBOUND_API}/${rid}/movements`",
            "const movementsBeforeVerifyRes = await page.request.get(movementPath",
            "expect(movementsBeforeVerify).toHaveLength(0)",
            "expect(verify.ok()).toBeTruthy()",
            "expect(post.ok()).toBeTruthy()",
            "movement.movement_type === 'inbound_intake'",
            "expect(inboundMovements).toHaveLength(1)",
            "expect(inboundMovements[0]?.quantity_delta).toBe(6)",
            "postState.status).toBe('done')",
            "postState.lines[0] && postState.lines[0].posted_qty).toBe(6)",
            "expect(inboundMovementsAfterPost).toHaveLength(1)",
            "expect(inboundMovementsAfterPost[0]?.quantity_delta).toBe(6)",
            "const duplicatePost = await page.request.post(`${INBOUND_API}/${rid}/post`",
            "expect(duplicatePost.status()).toBe(409)",
            "expect(duplicatePostBody.detail).toBe('already_posted')",
            "expect(inboundMovementsAfterRetry).toHaveLength(1)",
            "expect(inboundMovementsAfterRetry[0]?.quantity_delta).toBe(6)",
            "await expect(cells.nth(5)).toHaveText('6')",
            "await expect(cells.last()).toHaveText('6')",
            "await page.getByTestId('ff-reports-search').fill('нет-такого-товара-xyz')",
        ),
    ),
    CaseContract(
        "E8",
        "frontend/tests-e2e/ff-staff-users.spec.ts",
        "ff staff rights: four compact work blocks pass UI and direct-route gates",
        (
            "await expectDenied(page, '/seller/products')",
            "await expectDenied(page, '/app/ff/reception')",
            "await expectDenied(page, '/app/ff/settings')",
            "await expectDenied(page, '/app/ff/inventory')",
            "await expectDenied(page, '/app/ff/fbs')",
            "await expectDenied(page, '/app/ff/packaging')",
            "await expectDenied(page, '/app/ff/mp-shipments')",
            "await expectDenied(page, '/app/catalog')",
            "await expect(page.getByTestId('ff-reception-page')).toBeVisible()",
            "await expect(page.getByTestId('ff-mp-shipments-page')).toBeVisible()",
            "await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()",
            "await expect(page.getByTestId('ff-packaging-page')).toBeVisible()",
            "await expect(page.getByTestId('ff-products-list')).toBeVisible()",
            "await expect(page.getByTestId('ff-settings-screen')).toBeVisible()",
            "await expect(page.getByTestId('nav-ff-reception')).toBeVisible()",
            "await expect(page.getByTestId('nav-ff-mp-shipments')).toBeVisible()",
            "await expect(page.getByTestId('nav-ff-fbs')).toBeVisible()",
            "await expect(page.getByTestId('nav-ff-packaging')).toBeVisible()",
            "await expect(page.getByTestId('nav-ff-mp-shipments')).toHaveCount(0)",
            "await expect(page.getByTestId('nav-catalog')).toBeVisible()",
            "await expectNoPayrollUi(page)",
            "await expectDenied(page, '/app/ops/inbound')",
        ),
        (
            "getByTestId('ff-access-denied')",
            "нет сессии селлера",
            "Войти как селлер",
            "if (path === '/seller/products')",
            "await expect(denial).toContainText('нет сессии селлера')",
            "await expect(page.getByRole('button', { name: 'Войти как селлер' })).toBeVisible()",
        ),
    ),
    CaseContract(
        "E9",
        "frontend/tests-e2e/seller-available-stock.spec.ts",
        "seller products table and next MP picker show current stock after MP plan",
        (
            "await expect(tableHead).toContainText('Артикул продавца')",
            "const productsRes = await page.request.get(`${e2eApi}/products`",
            "productsRes.ok()",
            "products.find((product) => product.id === productId)",
            "linkedProduct?.wb_nm_id).toBe(424242)",
            "seller-catalog-stock-on-hand-${productId}",
            "'На ФФ 10'",   # noqa: RUF001
            "seller-catalog-stock-in-storage-${productId}",
            "'В ячейках 10'",   # noqa: RUF001
            "seller-catalog-stock-free-fbo-${productId}",
            "'Свободный FBO 10'",
            "await expect(pickerRow.locator('td').nth(6)).toHaveText('6')",
        ),
    ),
    CaseContract(
        "E10",
        "frontend/tests-e2e/seller-stock-directions.spec.ts",
        "FF user creates, edits and deletes reserve directions in FF catalog",
        (
            "await page.goto('/app/ff/products')",
            "await expect(page.getByTestId('ff-products-table')).toBeVisible()",
            "ff-catalog-stock-in-storage-${productId}",
            "'В ячейках 10'",  # noqa: RUF001
            "ff-catalog-stock-on-hand-${productId}",
            "'На ФФ 10'",  # noqa: RUF001
            "ff-catalog-stock-free-fbo-${productId}",
            "'Свободный FBO 10'",
            "ff-catalog-reserves-${productId}",
            "ff-stock-directions-panel-${productId}",
            "ff-stock-direction-name-${productId}",
            "ff-stock-direction-quantity-${productId}",
            "ff-stock-direction-comment-${productId}",
            "ff-stock-direction-submit-${productId}",
            "ff-stock-direction-row-${firstDirectionId}",
            "ff-stock-direction-edit-${reserveDirectionId}",
            "ff-stock-direction-delete-${firstDirectionId}",
            "ff-stock-direction-confirm-delete",
            "Резерв/набор · 3 шт",
            "Резерв/набор · 4 шт",
            "const reserveSummary = panel.locator('.MuiTypography-caption')",
            "await expect(reserveSummary).toHaveCount(1)",
            "await expect(freeFboSummary).toHaveCount(1)",
            "await expect(reserveSummary.locator('..')).toContainText",
            "await expect(freeFboSummary.locator('..')).toContainText",
            "expectReserveTotals(3, 7)",
            "expectReserveTotals(5, 5)",
            "expectReserveTotals(7, 3)",
            "expectReserveTotals(4, 6)",
            "firstCreateReq.postDataJSON() as { is_fbs: boolean }).is_fbs).toBe(false)",
            "reservePatchReq.postDataJSON() as { is_fbs: boolean; quantity: number }))",
            "is_fbs: false",
            "response.request().method() === 'POST'",
            "response.status() === 422",
            "getByTestId('ff-products-error')",
            "Нельзя распределить больше, чем есть на ФФ",
            "expect(deleteRequests).toBe(0)",
            "expect(deleteRequests).toBe(1)",
            "loginAsSeller(page, sellerEmail, password, { firstTime: true })",
            "nav-seller-products",
            "seller-products-table",
            "seller-catalog-stock-free-fbo-${productId}",
            "seller-catalog-reserves-${productId}",
            "seller-reserves-panel-${productId}",
            "seller-reserve-direction-row-${reserveDirectionId}",
            "const sellerReserveSummary = sellerPanel",
            "await expect(sellerReserveSummary).toHaveCount(1)",
            "await expect(sellerFreeFboSummary).toHaveCount(1)",
            "sellerReserveSummary.locator('..')).toContainText('4 шт')",
            "sellerFreeFboSummary.locator('..')).toContainText('6 шт')",
            "Редактировать' })).toHaveCount(0)",
            "Удалить' })).toHaveCount(0)",
            "seller-reserves-close",
            "getByRole('button')).toHaveCount(1)",
        ),
        forbidden=(
            "seller-stock-",
            "seller-fbs-",
            "ff-stock-direction-fbs-",
            "'/seller/products'",
        ),
    ),
)


def _source(path: str, overrides: Mapping[str, str]) -> str:
    if path in overrides:
        return overrides[path]
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _without_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("//")
    )


def _test_block(source: str, title: str) -> tuple[str, str | None]:
    title_pattern = re.escape(title)
    declaration = re.compile(
        rf"\btest(?P<modifier>\.(?:skip|only))?\s*\(\s*(['\"])\s*{title_pattern}\s*\2",
    )
    matches = list(declaration.finditer(source))
    if len(matches) != 1:
        return "", f"expected one declaration for {title!r}, found {len(matches)}"

    match = matches[0]
    if match.group("modifier"):
        return "", f"{title!r} is marked {match.group('modifier')}"

    remainder = source[match.end() :]
    next_test = re.search(r"(?m)^test(?:\.(?:skip|only))?\s*\(", remainder)
    if next_test:
        block = source[match.start() : match.end() + next_test.start()]
    else:
        block = source[match.start() :]
    return block, None


def audit_contract(overrides: Mapping[str, str] | None = None) -> list[str]:
    sources = overrides or {}
    errors: list[str] = []
    for case in CASES:
        source = _without_comments(_source(case.path, sources))
        block, declaration_error = _test_block(source, case.title)
        if declaration_error:
            errors.append(f"{case.case_id}: {declaration_error}")
            continue
        if re.search(r"\btest\.(?:skip|fixme)\s*\(", block):
            errors.append(f"{case.case_id}: target test contains a runtime skip/fixme")
        for fragment in case.required:
            if fragment not in block:
                errors.append(f"{case.case_id}: missing protected assertion {fragment!r}")
        for fragment in case.file_required:
            if fragment not in source:
                errors.append(f"{case.case_id}: missing access-control assertion {fragment!r}")
        for fragment in case.forbidden:
            if fragment in block:
                errors.append(f"{case.case_id}: unsupported UI assertion {fragment!r}")
    return errors


def test_named_e2e_cases_retain_their_required_business_assertions() -> None:
    errors = audit_contract()
    assert not errors, "WMS-703 E2E contract regressed:\n" + "\n".join(errors)


@pytest.mark.parametrize(
    ("case", "fragment"),
    [
        (case, fragment)
        for case in CASES
        for fragment in case.required
        if fragment in _source(case.path, {})
    ],
    ids=[
        f"{case.case_id}-{index}"
        for case in CASES
        for index, fragment in enumerate(case.required)
        if fragment in _source(case.path, {})
    ],
)
def test_guard_rejects_removal_of_a_required_assertion(
    case: CaseContract, fragment: str
) -> None:
    source = _source(case.path, {})
    block, error = _test_block(source, case.title)
    assert error is None
    assert fragment in block
    # Remove every copy so this negative control tests deletion, even when the
    # same assertion fragment appears more than once in the case.
    mutated = block.replace(fragment, "")
    full_mutated = source.replace(block, mutated, 1)
    errors = audit_contract({case.path: full_mutated})
    assert any(
        f"{case.case_id}: missing protected assertion {fragment!r}" in error
        for error in errors
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_guard_rejects_commenting_out_a_required_assertion(case: CaseContract) -> None:
    source = _source(case.path, {})
    block, error = _test_block(source, case.title)
    assert error is None
    fragment = case.required[0]
    lines = block.splitlines()
    commented = "\n".join(
        f"// {line}" if fragment in line else line for line in lines
    )
    full_mutated = source.replace(block, commented, 1)
    errors = audit_contract({case.path: full_mutated})
    assert any(
        f"{case.case_id}: missing protected assertion {fragment!r}" in error
        for error in errors
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_guard_rejects_block_commenting_out_a_required_assertion(
    case: CaseContract,
) -> None:
    source = _source(case.path, {})
    block, error = _test_block(source, case.title)
    assert error is None
    fragment = case.required[0]
    commented = "\n".join(
        f"/* {line} */" if fragment in line else line for line in block.splitlines()
    )
    full_mutated = source.replace(block, commented, 1)
    errors = audit_contract({case.path: full_mutated})
    assert any(
        f"{case.case_id}: missing protected assertion {fragment!r}" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("case", "fragment"),
    [
        (case, fragment)
        for case in CASES
        for fragment in case.file_required
        if fragment in _source(case.path, {})
    ],
    ids=[
        f"{case.case_id}-file-{index}"
        for case in CASES
        for index, fragment in enumerate(case.file_required)
        if fragment in _source(case.path, {})
    ],
)
def test_guard_rejects_removal_of_an_access_boundary(
    case: CaseContract, fragment: str
) -> None:
    source = _source(case.path, {})
    assert fragment in source
    # File-level controls also remove all copies of a boundary assertion.
    mutated = source.replace(fragment, "")
    errors = audit_contract({case.path: mutated})
    assert any(
        f"{case.case_id}: missing access-control assertion {fragment!r}" in error
        for error in errors
    )


@pytest.mark.parametrize("modifier", ["skip", "only"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_guard_rejects_skipped_or_exclusive_target_cases(
    case: CaseContract, modifier: str
) -> None:
    source = _source(case.path, {})
    marker = f"test('{case.title}'"
    if marker not in source:
        marker = f'test("{case.title}"'
    assert marker in source
    mutated = source.replace(marker, f"test.{modifier}({marker[len('test('):]}", 1)
    assert audit_contract({case.path: mutated})


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_guard_rejects_runtime_skips_inside_target_cases(case: CaseContract) -> None:
    source = _source(case.path, {})
    block, error = _test_block(source, case.title)
    assert error is None
    body = re.search(r"=>\s*\{", block)
    assert body is not None
    insertion = body.end() + (source.find(block))
    mutated = source[:insertion] + "\n  test.skip('contract mutation')" + source[insertion:]
    errors = audit_contract({case.path: mutated})
    assert any(
        f"{case.case_id}: target test contains a runtime skip/fixme" in error
        for error in errors
    )


@pytest.mark.parametrize(
    ("case", "fragment"),
    [
        (case, fragment)
        for case in CASES
        for fragment in case.forbidden
    ],
    ids=[
        f"{case.case_id}-forbidden-{index}"
        for case in CASES
        for index, _fragment in enumerate(case.forbidden)
    ],
)
def test_guard_rejects_unsupported_ui_assertions(
    case: CaseContract, fragment: str
) -> None:
    source = _source(case.path, {})
    block, error = _test_block(source, case.title)
    assert error is None
    mutated = source.replace(block, f"{block}\n{fragment}", 1)
    errors = audit_contract({case.path: mutated})
    assert any(
        f"{case.case_id}: unsupported UI assertion {fragment!r}" in error
        for error in errors
    )
