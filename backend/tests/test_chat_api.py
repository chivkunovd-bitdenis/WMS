"""Chat API happy-path tests — WMS-397/WMS-399.

Cover the flows the coordinator asked for: ensure_main is idempotent,
messages dedupe on retry, seller sees only their seller_id's chats,
document attachment cards survive a reload, seller cannot open FF-only
extra chats, and file/image upload round-trips through the storage."""

from __future__ import annotations

import io
import time
import uuid

import pytest
from httpx import AsyncClient


async def _register_admin(async_client: AsyncClient) -> tuple[str, dict[str, str], str]:
    suffix = str(int(time.time() * 1_000_000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Chat Co {suffix}",
            "slug": f"chat-{suffix}",
            "admin_email": f"chat-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    return suffix, headers, str(me.json()["id"])


async def _create_seller(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
) -> tuple[dict[str, str], str, str]:
    email = f"chat-seller-{suffix}@example.com"
    created = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Chat Seller", "email": email, "password": "password123"},
    )
    assert created.status_code == 201, created.text
    seller_id = str(created.json()["seller_id"])

    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=seller_headers)
    seller_user_id = str(me.json()["id"])
    return seller_headers, seller_id, seller_user_id


@pytest.mark.asyncio
async def test_main_chat_is_idempotent_per_seller(async_client: AsyncClient) -> None:
    """Two calls to GET .../conversations/main must return the same UUID."""
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)

    first = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text
    second = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["kind"] == "main"
    assert first.json()["seller_id"] == seller_id


@pytest.mark.asyncio
async def test_seller_sees_only_own_main_chat(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_a_id, _ = await _create_seller(async_client, admin_headers, suffix)
    # Add a second seller and ensure its main chat exists.
    other_suffix = suffix + "b"
    email_b = f"chat-seller-{other_suffix}@example.com"
    created_b = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Chat Seller B", "email": email_b, "password": "password123"},
    )
    assert created_b.status_code == 201, created_b.text
    seller_b_id = str(created_b.json()["seller_id"])
    login_b = await async_client.post(
        "/auth/login",
        json={"email": email_b, "password": "password123"},
    )
    seller_b_headers = {"Authorization": f"Bearer {login_b.json()['access_token']}"}
    login_a = await async_client.post(
        "/auth/login",
        json={
            "email": f"chat-seller-{suffix}@example.com",
            "password": "password123",
        },
    )
    seller_a_headers = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

    # Materialise both chats.
    await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_a_id}",
        headers=admin_headers,
    )
    await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_b_id}",
        headers=admin_headers,
    )

    listed_a = await async_client.get(
        "/operations/chat/conversations", headers=seller_a_headers
    )
    assert listed_a.status_code == 200
    for row in listed_a.json()["items"]:
        assert row["seller_id"] == seller_a_id

    listed_b = await async_client.get(
        "/operations/chat/conversations", headers=seller_b_headers
    )
    assert listed_b.status_code == 200
    for row in listed_b.json()["items"]:
        assert row["seller_id"] == seller_b_id


@pytest.mark.asyncio
async def test_seller_cannot_open_other_sellers_chat(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_a_id, _ = await _create_seller(async_client, admin_headers, suffix)
    other_suffix = suffix + "c"
    email_b = f"chat-seller-{other_suffix}@example.com"
    await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Chat Seller C", "email": email_b, "password": "password123"},
    )
    login_b = await async_client.post(
        "/auth/login",
        json={"email": email_b, "password": "password123"},
    )
    seller_b_headers = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # A materialises their chat.
    main_a = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_a_id}",
        headers=admin_headers,
    )
    conv_id = main_a.json()["id"]

    # B must not read A's messages.
    resp = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=seller_b_headers,
    )
    assert resp.status_code == 403
    # And B must not force-open A's chat by seller_id override either.
    forced = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_a_id}",
        headers=seller_b_headers,
    )
    assert forced.status_code == 403


@pytest.mark.asyncio
async def test_post_message_dedupes_on_retry(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]

    client_id = "cli-" + uuid.uuid4().hex[:16]
    first = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={"client_message_id": client_id, "text": "hello seller"},
    )
    assert first.status_code == 201, first.text
    second = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={"client_message_id": client_id, "text": "hello seller"},
    )
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]

    listed = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
    )
    assert listed.status_code == 200
    assert len([m for m in listed.json()["items"] if m["client_message_id"] == client_id]) == 1


@pytest.mark.asyncio
async def test_attached_document_persists_across_reload(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]

    doc_id = str(uuid.uuid4())
    post = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={
            "client_message_id": "with-doc-" + uuid.uuid4().hex[:8],
            "text": "look at this order",
            "attached_document": {
                "kind": "fbs_order",
                "id": doc_id,
                "title": "FBS #A-42",
                "seller_id": seller_id,
                "seller_name": "Chat Seller",
            },
        },
    )
    assert post.status_code == 201, post.text
    # Second participant (the seller) reloads and still sees the card.
    listed = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=seller_headers,
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    doc = items[0]["attached_document"]
    assert doc is not None
    assert doc["kind"] == "fbs_order"
    assert doc["id"] == doc_id
    assert doc["seller_id"] == seller_id


@pytest.mark.asyncio
async def test_attached_document_wrong_seller_rejected(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    _, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]
    resp = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={
            "client_message_id": "mismatch-" + uuid.uuid4().hex[:8],
            "text": "should fail",
            "attached_document": {
                "kind": "fbs_order",
                "id": str(uuid.uuid4()),
                "title": "wrong seller",
                "seller_id": str(uuid.uuid4()),
            },
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "document_seller_mismatch"


@pytest.mark.asyncio
async def test_upload_and_download_attachment(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]

    file_bytes = b"screenshot-bytes"
    upload = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/attachments",
        headers=admin_headers,
        files={"file": ("paste.png", io.BytesIO(file_bytes), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    att = upload.json()
    assert att["is_image"] is True
    assert att["filename"] == "paste.png"
    assert att["size_bytes"] == len(file_bytes)

    # Attach to a message.
    post = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={
            "client_message_id": "pic-" + uuid.uuid4().hex[:8],
            "text": "screenshot",
            "attachment_ids": [att["id"]],
        },
    )
    assert post.status_code == 201, post.text
    msg = post.json()
    assert len(msg["attachments"]) == 1
    assert msg["attachments"][0]["is_image"] is True

    # Seller reloads and downloads the content.
    listed = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=seller_headers,
    )
    items = listed.json()["items"]
    assert len(items) == 1
    attachment_id = items[0]["attachments"][0]["id"]
    download = await async_client.get(
        f"/operations/chat/attachments/{attachment_id}/content",
        headers=seller_headers,
    )
    assert download.status_code == 200
    assert download.content == file_bytes


@pytest.mark.asyncio
async def test_edit_message_only_by_author(async_client: AsyncClient) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, _ = await _create_seller(async_client, admin_headers, suffix)
    main = await async_client.get(
        f"/operations/chat/conversations/main?seller_id={seller_id}",
        headers=admin_headers,
    )
    conv_id = main.json()["id"]
    post = await async_client.post(
        f"/operations/chat/conversations/{conv_id}/messages",
        headers=admin_headers,
        json={"client_message_id": "edit-" + uuid.uuid4().hex[:8], "text": "first"},
    )
    msg_id = post.json()["id"]

    ok = await async_client.patch(
        f"/operations/chat/messages/{msg_id}",
        headers=admin_headers,
        json={"text": "fixed typo"},
    )
    assert ok.status_code == 200
    assert ok.json()["text"] == "fixed typo"
    assert ok.json()["edited_at"] is not None

    denied = await async_client.patch(
        f"/operations/chat/messages/{msg_id}",
        headers=seller_headers,
        json={"text": "not allowed"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_extra_chat_requires_admin_and_hides_from_stranger(
    async_client: AsyncClient,
) -> None:
    suffix, admin_headers, _ = await _register_admin(async_client)
    seller_headers, seller_id, seller_user_id = await _create_seller(
        async_client, admin_headers, suffix
    )
    # Seller cannot create extra chats.
    denied = await async_client.post(
        "/operations/chat/conversations/extra",
        headers=seller_headers,
        json={"seller_id": seller_id, "title": "seller attempt"},
    )
    assert denied.status_code == 403

    # Admin creates one and adds the seller-user.
    created = await async_client.post(
        "/operations/chat/conversations/extra",
        headers=admin_headers,
        json={
            "seller_id": seller_id,
            "title": "Escalation",
            "participant_user_ids": [seller_user_id],
        },
    )
    assert created.status_code == 201, created.text
    conv_id = created.json()["id"]

    # Seller can list and read; a stranger seller cannot.
    listed = await async_client.get(
        "/operations/chat/conversations", headers=seller_headers
    )
    assert any(c["id"] == conv_id for c in listed.json()["items"])

    read_ok = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages", headers=seller_headers
    )
    assert read_ok.status_code == 200

    # Second seller (unrelated) does not see it and cannot read.
    other_suffix = suffix + "d"
    email_c = f"chat-seller-{other_suffix}@example.com"
    await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={"name": "Other seller", "email": email_c, "password": "password123"},
    )
    login_c = await async_client.post(
        "/auth/login", json={"email": email_c, "password": "password123"}
    )
    other_headers = {"Authorization": f"Bearer {login_c.json()['access_token']}"}

    forbidden = await async_client.get(
        f"/operations/chat/conversations/{conv_id}/messages", headers=other_headers
    )
    assert forbidden.status_code == 403
    listed_other = await async_client.get(
        "/operations/chat/conversations", headers=other_headers
    )
    assert not any(c["id"] == conv_id for c in listed_other.json()["items"])
