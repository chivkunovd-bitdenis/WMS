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
        "ff products: catalog separates product fields and hides stock columns",
        (
            "await expect(tableHead).toContainText('Название')",
            "await expect(tableHead).toContainText('Артикул продавца')",
            "await expect(tableHead).toContainText('SKU')",
            "await expect(tableHead).toContainText('ШК')",
            "await expect(tableHead).toContainText('WB/nmId')",
            "await expect(tableHead).toContainText('Размер')",
            "await expect(tableHead).toContainText('ТЗ')",  # noqa: RUF001
            "await expect(tableHead).not.toContainText('Артикул WB')",
            "await expect(tableHead).not.toContainText('Распределение')",
            "await expect(tableHead).not.toContainText('Доступно')",
            "await expect(tableHead).not.toContainText('Сортировка')",
            "await expect(tableHead).not.toContainText('Не упаковано')",  # noqa: RUF001
            "await expect(tableHead).not.toContainText('Упаковано')",
            "await expect(tableHead).not.toContainText('В ячейках')",  # noqa: RUF001
            "await expect(tableHead).not.toContainText('Технический резерв')",
            "await expect(page.getByTestId('ff-products-table')).not.toContainText('Сортировка')",
            "await expect(page.getByTestId('ff-products-table')).not.toContainText('Не упаковано')",  # noqa: RUF001
            "await expect(page.getByTestId('ff-products-table')).not.toContainText('Упаковано')",
            "await expect(page.getByTestId('ff-products-table')).not.toContainText('В ячейках')",  # noqa: RUF001
            (
                "await expect(page.getByTestId('ff-products-table'))"
                ".not.toContainText('Технический резерв')"
            ),
            "await expect(alphaRow.locator('td').nth(1)).not.toContainText('ART-A')",
            "await expect(alphaRow.locator('td').nth(1)).not.toContainText('46')",
            "await expect(alphaRow.locator('td').nth(2)).toContainText('ART-A')",
            "await expect(alphaRow.locator('td').nth(3)).toContainText(skuA)",
            "await expect(alphaRow.locator('td').nth(4)).toContainText(barcodeA)",
            "await expect(alphaRow).toContainText('46')",
            "await expect(page.getByTestId('ff-product-row')).toHaveCount(3)",
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
            "ff-honest-sign-status-${productId}",
            "await expect(honestSignChip).toHaveCount(1)",
            "await expect(honestSignChip).toBeVisible()",
            "await expect(markingLink).toContainText('2')",
            "await markingLink.click()",
            "ff-honest-sign-product-page",
        ),
    ),
    CaseContract(
        "E5",
        "frontend/tests-e2e/ff-products.spec.ts",
        "ff products: import tz xlsx creates catalog products with packaging",
        (
            (
                "await expect(page.getByTestId('ff-tz-import-preview-table'))"
                ".toContainText('123456789')"
            ),
            "await expect(page.getByTestId('ff-products-import-notice')).toContainText(",
            "await expect(page.getByTestId('ff-product-row')).toHaveCount(2)",
            "await expect(page.getByTestId('ff-products-table')).toContainText('2039000000001')",
            "page.request.get('/api/products'",
            "wb_nm_id === 123456789",
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
            (
                "const destinationRes = await page.request.post(`"
                "/api/warehouses/${seed.warehouseId}/locations`"
            ),
            "storageLocationId: destinationId",
            "page.request.patch(`${INBOUND_API}/${rid}/lines/",
            "storage_location_id: destinationId",
            "const movementPath = `${INBOUND_API}/${rid}/movements`",
            "const movementsBeforeVerifyRes = await page.request.get(movementPath",
            "expect(movementsBeforeVerify).toHaveLength(0)",
            "expect(verify.ok()).toBeTruthy()",
            "expect(post.ok()).toBeTruthy()",
            "movement.movement_type === 'inbound_intake'",
            "expect(inboundMovements).toHaveLength(1)",
            "expect(inboundMovements[0]?.quantity_delta).toBe(6)",
            "postState.status).toBe('done')",
            "postState.lines[0].posted_qty).toBe(6)",
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
        ),
    ),
    CaseContract(
        "E9",
        "frontend/tests-e2e/seller-available-stock.spec.ts",
        "seller products table and next MP picker show current stock after MP plan",
        (
            "await expect(tableHead).toContainText('Артикул продавца')",
            "await expect(row.getByTestId('seller-stock-on-hand')).toHaveText('На ФФ 10')",  # noqa: RUF001
            "await expect(row.getByTestId('seller-stock-in-storage')).toHaveText('В ячейках 10')",  # noqa: RUF001
            "await expect(distribution).toContainText('FBS 0 шт')",
            "await expect(pickerRow.locator('td').nth(6)).toHaveText('6')",
        ),
    ),
    CaseContract(
        "E10",
        "frontend/tests-e2e/seller-stock-directions.spec.ts",
        "seller creates, edits and deletes stock directions with compact FBS publication controls",
        (
            "await expect(tableHead).toContainText('Артикул продавца')",
            "r.status() === 422",
            "'Нельзя распределить больше, чем есть на ФФ'",
            "expect(deleteRequests).toBe(0)",
            "expect(deleteRequests).toBe(1)",
            (
                "await expect(row.getByTestId(`seller-stock-distribution-${productId}`))"
                ".toContainText("
            ),
            "await expect(row.getByTestId('seller-stock-free-fbo')).toHaveText('Свободный FBO 6')",
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
