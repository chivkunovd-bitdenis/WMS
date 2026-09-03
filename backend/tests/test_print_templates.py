from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.print_template import LAYOUT_BLOCK_CZ, LAYOUT_BLOCK_LABEL, USER_LAST_LAYOUT_NAME
from app.services import print_template_service as pt_svc
from app.services.tokens import decode_access_token


async def _seed_tenant_seller_product(
    async_client: AsyncClient,
) -> tuple[str, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    email = f"pt-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Print Template FF",
            "slug": f"pt-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    payload = decode_access_token(token)
    tenant_id = uuid.UUID(str(payload["tenant_id"]))
    user_id = uuid.UUID(str(payload["sub"]))
    headers = {"Authorization": f"Bearer {token}"}

    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "PT Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller_resp.status_code == 201, seller_resp.text
    seller_id = uuid.UUID(seller_resp.json()["id"])

    product_resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Шаблон-товар",
            "sku_code": f"PT-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": str(seller_id),
        },
    )
    assert product_resp.status_code == 200, product_resp.text
    product_id = uuid.UUID(product_resp.json()["id"])

    return token, tenant_id, user_id, seller_id, product_id


def _label_cz_layout() -> dict[str, object]:
    return {
        "units": [
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
            {"block": LAYOUT_BLOCK_CZ, "copies": 1},
        ],
    }


@pytest.mark.asyncio
async def test_resolve_default_template_product_over_seller_over_system(
    async_client: AsyncClient,
) -> None:
    token, tenant_id, _user_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}

    async with SessionLocal() as session:
        system_row = await pt_svc.resolve_default_print_template(
            session,
            tenant_id,
            product_id=product_id,
            seller_id=seller_id,
        )
        assert system_row.is_system is True
        assert system_row.name == "Парами"
        assert system_row.layout.units[0].block == LAYOUT_BLOCK_CZ
        assert system_row.layout.units[0].copies == 2

        await pt_svc.create_print_template(
            session,
            tenant_id,
            name="Seller default",
            layout={"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 1}]},
            seller_id=seller_id,
            is_default=True,
        )
        await session.commit()

    async with SessionLocal() as session:
        seller_row = await pt_svc.resolve_default_print_template(
            session,
            tenant_id,
            product_id=product_id,
            seller_id=seller_id,
        )
        assert seller_row.is_system is False
        assert seller_row.name == "Seller default"
        assert seller_row.layout.units[0].copies == 1

    create_product_tpl = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Product default",
            "layout": _label_cz_layout(),
            "product_id": str(product_id),
            "is_default": True,
        },
    )
    assert create_product_tpl.status_code == 201, create_product_tpl.text

    resolve_resp = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved = resolve_resp.json()
    assert resolved["name"] == "Product default"
    assert resolved["is_system"] is False
    assert resolved["layout"]["units"] == [
        {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
        {"block": LAYOUT_BLOCK_CZ, "copies": 1},
    ]


@pytest.mark.asyncio
async def test_print_template_crud(async_client: AsyncClient) -> None:
    token, _tenant_id, _user_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "My template",
            "layout": _label_cz_layout(),
            "seller_id": str(seller_id),
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    template_id = create_resp.json()["id"]

    list_resp = await async_client.get(
        "/operations/marking-codes/print-templates",
        headers=headers,
        params={"seller_id": str(seller_id)},
    )
    assert list_resp.status_code == 200, list_resp.text
    assert any(row["id"] == template_id for row in list_resp.json())

    update_resp = await async_client.put(
        f"/operations/marking-codes/print-templates/{template_id}",
        headers=headers,
        json={"name": "Renamed template", "is_default": True},
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["name"] == "Renamed template"
    assert update_resp.json()["is_default"] is True

    delete_resp = await async_client.delete(
        f"/operations/marking-codes/print-templates/{template_id}",
        headers=headers,
    )
    assert delete_resp.status_code == 204, delete_resp.text

    list_after = await async_client.get(
        "/operations/marking-codes/print-templates",
        headers=headers,
        params={"product_id": str(product_id)},
    )
    assert list_after.status_code == 200, list_after.text
    assert all(row["id"] != template_id for row in list_after.json())


@pytest.mark.asyncio
async def test_is_default_clears_previous_flag(async_client: AsyncClient) -> None:
    token, tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}

    first = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "First default",
            "layout": {"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 1}]},
            "seller_id": str(seller_id),
            "is_default": True,
        },
    )
    assert first.status_code == 201, first.text
    first_id = uuid.UUID(first.json()["id"])

    second = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Second default",
            "layout": {"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 2}]},
            "seller_id": str(seller_id),
            "is_default": True,
        },
    )
    assert second.status_code == 201, second.text

    async with SessionLocal() as session:
        first_row = await pt_svc.get_print_template(session, tenant_id, first_id)
        assert first_row.is_default is False


@pytest.mark.asyncio
async def test_user_last_layout_preferred_over_seller_default(
    async_client: AsyncClient,
) -> None:
    token, tenant_id, user_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    user_layout = {
        "units": [
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
            {"block": LAYOUT_BLOCK_CZ, "copies": 2},
        ],
    }

    async with SessionLocal() as session:
        await pt_svc.create_print_template(
            session,
            tenant_id,
            name="Seller default",
            layout={"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 1}]},
            seller_id=seller_id,
            is_default=True,
        )
        await pt_svc.save_user_last_print_layout(session, tenant_id, user_id, user_layout)

    resolve_resp = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved = resolve_resp.json()
    assert resolved["name"] == "Последняя раскладка"
    assert resolved["user_id"] == str(user_id)
    assert resolved["layout"]["units"] == user_layout["units"]


@pytest.mark.asyncio
async def test_two_users_get_different_last_layouts(async_client: AsyncClient) -> None:
    token_a, tenant_id, user_a_id, seller_id, product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    suffix = uuid.uuid4().hex[:8]
    staff_email = f"pt-staff-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=headers_a,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]
    patched = await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=headers_a,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": True,
        },
    )
    assert patched.status_code == 200, patched.text
    await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    login_b = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    assert login_b.status_code == 200, login_b.text
    token_b = login_b.json()["access_token"]
    user_b_id = uuid.UUID(str(decode_access_token(token_b)["sub"]))
    headers_b = {"Authorization": f"Bearer {token_b}"}

    layout_a = {"units": [{"block": LAYOUT_BLOCK_LABEL, "copies": 1}]}
    layout_b = {"units": [{"block": LAYOUT_BLOCK_CZ, "copies": 3}]}

    async with SessionLocal() as session:
        await pt_svc.save_user_last_print_layout(session, tenant_id, user_a_id, layout_a)
        await pt_svc.save_user_last_print_layout(session, tenant_id, user_b_id, layout_b)

    resolve_a = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers_a,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    resolve_b = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=headers_b,
        params={"product_id": str(product_id), "seller_id": str(seller_id)},
    )
    assert resolve_a.status_code == 200, resolve_a.text
    assert resolve_b.status_code == 200, resolve_b.text
    assert resolve_a.json()["layout"]["units"] == layout_a["units"]
    assert resolve_b.json()["layout"]["units"] == layout_b["units"]
    assert resolve_a.json()["user_id"] == str(user_a_id)
    assert resolve_b.json()["user_id"] == str(user_b_id)


@pytest.mark.asyncio
async def test_print_auto_saves_user_last_layout(async_client: AsyncClient) -> None:
    from test_marking_print_pool import _seed_product_with_pool_codes
    from test_packaging_tasks import _inventory_at_location

    h, _seller_id, product_id, wh_id = await _seed_product_with_pool_codes(
        async_client, code_count=5
    )
    user_id = uuid.UUID(str(decode_access_token(h["Authorization"].split()[1])["sub"]))
    tenant_id = uuid.UUID(str(decode_access_token(h["Authorization"].split()[1])["tenant_id"]))

    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=5,
        location_code="pt-user-layout",
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {
                    "product_id": product_id,
                    "storage_location_id": loc_id,
                    "quantity": 5,
                }
            ],
        },
    )
    assert task.status_code == 201, task.text
    line_id = task.json()["lines"][0]["id"]

    custom_layout = {
        "units": [
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
            {"block": LAYOUT_BLOCK_CZ, "copies": 1},
            {"block": LAYOUT_BLOCK_LABEL, "copies": 1},
        ],
    }
    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"layout_json": custom_layout, "allow_partial": False},
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["quantity"] == 5

    resolve_resp = await async_client.get(
        "/operations/marking-codes/print-templates/resolve",
        headers=h,
        params={"product_id": product_id},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved = resolve_resp.json()
    assert resolved["user_id"] == str(user_id)
    assert resolved["layout"]["units"] == custom_layout["units"]

    list_resp = await async_client.get(
        "/operations/marking-codes/print-templates",
        headers=h,
    )
    assert list_resp.status_code == 200, list_resp.text
    assert all(row["name"] != USER_LAST_LAYOUT_NAME for row in list_resp.json())

    async with SessionLocal() as session:
        row = await pt_svc.resolve_default_print_template(
            session,
            tenant_id,
            user_id=user_id,
            product_id=uuid.UUID(product_id),
        )
        assert row.layout.units[0].block == LAYOUT_BLOCK_LABEL
        assert len(row.layout.units) == 3



@pytest.mark.asyncio
async def test_label_options_survive_save_and_read(async_client: AsyncClient) -> None:
    """Состав этикетки закрепляется за селлером и не теряется при сохранении.

    Хранилище шаблонов с привязкой к селлеру существует с июня, но хранило
    только ленту — какие блоки и сколько копий. Состав самой этикетки жил в
    момент печати и забывался, поэтому «настроить этикетку селлеру» не работало:
    ручка молча выбрасывала опции.
    """
    token, _tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Без состава и бренда",
            "seller_id": str(seller_id),
            "is_default": True,
            "layout": {
                "units": [{"block": "label", "copies": 1}],
                "label_options": {
                    "include_size": True,
                    "include_color": True,
                    "include_brand": False,
                    "include_composition": False,
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["layout"]["label_options"] == {
        "include_size": True,
        "include_color": True,
        "include_brand": False,
        "include_composition": False,
    }

    resolved = await async_client.get(
        f"/operations/marking-codes/print-templates/resolve?seller_id={seller_id}",
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["layout"]["label_options"]["include_brand"] is False
    assert resolved.json()["layout"]["label_options"]["include_composition"] is False


@pytest.mark.asyncio
async def test_old_template_without_options_prints_everything(async_client: AsyncClient) -> None:
    """Шаблон, заведённый до 03.09.2026, хранит только ленту.

    Для него действует прежнее поведение — печатаем всё, что есть в данных.
    Иначе выкатка молча урезала бы уже настроенные этикетки.
    """
    from app.services.print_template_service import parse_layout

    layout = parse_layout({"units": [{"block": "cz", "copies": 2}]})
    assert layout.label_options.include_size is True
    assert layout.label_options.include_color is True
    assert layout.label_options.include_brand is True
    assert layout.label_options.include_composition is True


@pytest.mark.asyncio
async def test_seller_template_is_visible_to_every_operator(async_client: AsyncClient) -> None:
    """Настройка продавца — общая, а не личная настройка того, кто её сохранил.

    Ручка всегда штамповала шаблон id администратора, а глобальный шаблон
    продавца выбирается только при пустом user_id. Другой оператор такой шаблон
    не находил и печатал по-старому, не зная об этом.
    """
    token, _tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Этикетка продавца",
            "seller_id": str(seller_id),
            "is_default": True,
            "layout": {"units": [{"block": "label", "copies": 1}]},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["user_id"] is None, created.text


@pytest.mark.asyncio
async def test_operator_layout_does_not_carry_label_options_across_sellers(
    async_client: AsyncClient,
) -> None:
    """Привычка печати переносится между продавцами, состав этикетки — нет.

    Раскладка оператора сознательно важнее умолчания продавца: это его привычка,
    сколько блоков гнать лентой. Но состав этикетки — свойство товара продавца.
    Пока он попадал в ту же раскладку, оператор, напечатав для одного продавца,
    уносил его состав на следующего.
    """
    from app.services.print_template_service import resolve_default_print_template

    token, tenant_id, user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Без бренда",
            "seller_id": str(seller_id),
            "is_default": True,
            "layout": {
                "units": [{"block": "label", "copies": 1}],
                "label_options": {
                    "include_size": True,
                    "include_color": True,
                    "include_brand": False,
                    "include_composition": True,
                },
            },
        },
    )
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        # Оператор до этого печатал парами — привычка сохранена как его раскладка.
        await pt_svc.save_user_last_print_layout(
            session,
            tenant_id,
            user_id,
            {"units": [{"block": "cz", "copies": 2}]},
        )
        await session.commit()

    async with SessionLocal() as session:
        resolved = await resolve_default_print_template(
            session, tenant_id, user_id=user_id, seller_id=seller_id
        )
    # Лента — его привычка.
    assert [(u.block, u.copies) for u in resolved.layout.units] == [("cz", 2)]
    # Состав — от продавца, а не то, что осталось от прошлой печати.
    assert resolved.layout.label_options.include_brand is False


@pytest.mark.asyncio
async def test_seller_label_options_do_not_change_the_print_tape(
    async_client: AsyncClient,
) -> None:
    """Настройка состава этикетки не имеет права переписывать ленту печати.

    Панель настроек отвечает за одно: что печатать на этикетке ШК. Пока она
    сохраняла шаблон целиком, вместе с составом уезжала лента «один ШК» — и у
    оператора, у которого нет своей раскладки, из печати молча пропадал Честный
    знак. Проверяем оба конца: и что состав закрепился, и что лента осталась
    системной.
    """
    token, _tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    saved = await async_client.put(
        "/operations/marking-codes/print-templates/seller-label-options",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "label_options": {
                "include_size": True,
                "include_color": True,
                "include_brand": False,
                "include_composition": True,
            },
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["layout"]["label_options"]["include_brand"] is False
    assert body["layout"]["units"] == [{"block": "cz", "copies": 2}], body

    resolved = await async_client.get(
        f"/operations/marking-codes/print-templates/resolve?seller_id={seller_id}",
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    layout = resolved.json()["layout"]
    assert layout["label_options"]["include_brand"] is False
    assert layout["units"] == [{"block": "cz", "copies": 2}], layout


@pytest.mark.asyncio
async def test_seller_label_options_keep_an_existing_seller_tape(
    async_client: AsyncClient,
) -> None:
    """У продавца со своей лентой настройка состава её тоже не трогает."""
    token, _tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Лента продавца",
            "seller_id": str(seller_id),
            "is_default": True,
            "layout": {"units": [{"block": "cz", "copies": 1}, {"block": "label", "copies": 3}]},
        },
    )
    assert created.status_code == 201, created.text

    saved = await async_client.put(
        "/operations/marking-codes/print-templates/seller-label-options",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "label_options": {
                "include_size": False,
                "include_color": True,
                "include_brand": True,
                "include_composition": True,
            },
        },
    )
    assert saved.status_code == 200, saved.text
    layout = saved.json()["layout"]
    assert layout["units"] == [
        {"block": "cz", "copies": 1},
        {"block": "label", "copies": 3},
    ], layout
    assert layout["label_options"]["include_size"] is False


@pytest.mark.asyncio
async def test_label_options_do_not_reach_a_seller_without_a_template(
    async_client: AsyncClient,
) -> None:
    """Ненастроенный продавец печатает полным составом, а не чужим.

    Именно этот случай чинили: раньше при отсутствии своего шаблона возвращалась
    раскладка оператора целиком, вместе с составом предыдущего продавца.
    """
    from app.services.print_template_service import resolve_default_print_template

    token, tenant_id, user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    saved = await async_client.put(
        "/operations/marking-codes/print-templates/seller-label-options",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "label_options": {
                "include_size": False,
                "include_color": False,
                "include_brand": False,
                "include_composition": False,
            },
        },
    )
    assert saved.status_code == 200, saved.text

    async with SessionLocal() as session:
        # Оператор печатает у настроенного продавца — его личная раскладка
        # сохраняется, и в неё не должен попасть чужой состав.
        await pt_svc.save_user_last_print_layout(
            session,
            tenant_id,
            user_id,
            {
                "units": [{"block": "cz", "copies": 2}],
                "label_options": {
                    "include_size": False,
                    "include_color": False,
                    "include_brand": False,
                    "include_composition": False,
                },
            },
        )
        # Следующий продавец — без своего шаблона вовсе.
        other = await resolve_default_print_template(
            session, tenant_id, user_id=user_id, product_id=None, seller_id=None
        )
    assert other.layout.label_options.include_brand is True
    assert other.layout.label_options.include_composition is True
    assert other.layout.label_options.include_size is True
    assert other.layout.label_options.include_color is True


@pytest.mark.asyncio
async def test_old_seller_template_keeps_its_tape_even_with_the_same_name(
    async_client: AsyncClient,
) -> None:
    """Обычный шаблон продавца остаётся хозяином своей ленты.

    Признак «этот шаблон только про состав» живёт в самом макете, а не в имени.
    Имя «Этикетка продавца» может носить и обычный шаблон, заведённый руками до
    появления настройки состава, — отбирать у него ленту нельзя.
    """
    from app.services.print_template_service import resolve_default_print_template

    token, tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    created = await async_client.post(
        "/operations/marking-codes/print-templates",
        headers=headers,
        json={
            "name": "Этикетка продавца",
            "seller_id": str(seller_id),
            "is_default": True,
            "layout": {"units": [{"block": "label", "copies": 1}]},
        },
    )
    assert created.status_code == 201, created.text

    async with SessionLocal() as session:
        row = await resolve_default_print_template(
            session, tenant_id, user_id=None, product_id=None, seller_id=seller_id
        )
    assert [(u.block, u.copies) for u in row.layout.units] == [("label", 1)]
    # Состав у него не задан — печатаем всё, как и раньше.
    assert row.layout.label_options.include_brand is True


@pytest.mark.asyncio
async def test_composition_template_never_owns_the_tape(
    async_client: AsyncClient,
) -> None:
    """Шаблон, заведённый панелью состава, ленту не диктует.

    Иначе у оператора без личной раскладки лента становилась бы «один ШК», и
    Честный знак пропадал бы из печати.
    """
    from app.services.print_template_service import resolve_default_print_template

    token, tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    saved = await async_client.put(
        "/operations/marking-codes/print-templates/seller-label-options",
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "label_options": {
                "include_size": True,
                "include_color": True,
                "include_brand": False,
                "include_composition": True,
            },
        },
    )
    assert saved.status_code == 200, saved.text

    async with SessionLocal() as session:
        row = await resolve_default_print_template(
            session, tenant_id, user_id=None, product_id=None, seller_id=seller_id
        )
    assert [(u.block, u.copies) for u in row.layout.units] == [("cz", 2)]
    assert row.layout.label_options.include_brand is False


@pytest.mark.asyncio
async def test_second_save_of_label_options_is_persisted(
    async_client: AsyncClient,
) -> None:
    """Повторное сохранение состава доезжает до базы.

    Ветка изменения существующего шаблона только сбрасывала изменения в
    транзакцию и не коммитила: ручка отвечала «сохранено», а следующий запрос
    читал прежние галочки.
    """
    token, _tenant_id, _user_id, seller_id, _product_id = await _seed_tenant_seller_product(
        async_client
    )
    headers = {"Authorization": f"Bearer {token}"}
    url = "/operations/marking-codes/print-templates/seller-label-options"
    first = await async_client.put(
        url,
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "label_options": {
                "include_size": True,
                "include_color": True,
                "include_brand": False,
                "include_composition": True,
            },
        },
    )
    assert first.status_code == 200, first.text
    second = await async_client.put(
        url,
        headers=headers,
        json={
            "seller_id": str(seller_id),
            "label_options": {
                "include_size": False,
                "include_color": False,
                "include_brand": False,
                "include_composition": False,
            },
        },
    )
    assert second.status_code == 200, second.text

    resolved = await async_client.get(
        f"/operations/marking-codes/print-templates/resolve?seller_id={seller_id}",
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    options = resolved.json()["layout"]["label_options"]
    assert options == {
        "include_size": False,
        "include_color": False,
        "include_brand": False,
        "include_composition": False,
    }, options
