"""Offline guard tests. No credentials or external transport are used."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from dev import developer_requests_probe as probe


@pytest.mark.asyncio
async def test_timeout_never_allows_second_external_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.developer_request_trello import TrelloError

    state = probe.State(tmp_path)
    state.data = {"version": 1, "live_request_id": "selected", "create_started": False}
    state.save()
    calls: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        path = request.url.path
        if request.method == "POST":
            # The persisted guard exists even if the network response is lost.
            assert json.loads(state.path.read_text())["create_started"] is True
            raise httpx.ReadTimeout("simulated response loss")
        if path.endswith("/lists"):
            value: Any = [{"id": item} for item in probe.LISTS.values()]
        elif "/labels/" in path:
            value = {"idBoard": "board", "name": "Клиент", "color": "blue"}
        elif path.endswith("/cards"):
            value = []
        else:
            value = {
                "id": "board",
                "shortLink": probe.BOARD_LINK,
                "closed": False,
                "prefs": {"permissionLevel": "private"},
            }
        return httpx.Response(200, json=value)

    client_type = httpx.AsyncClient
    monkeypatch.setattr(probe, "load_credentials", lambda _: {"key": "fake", "token": "fake"})
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(transport), **kwargs),
    )
    monkeypatch.setattr("app.services.developer_request_trello.card_payload", lambda *_: {})
    async with probe.live_client(state, tmp_path / "not-read") as client:
        with pytest.raises(TrelloError, match="probe_extra_create_forbidden"):
            await client.create_card(SimpleNamespace(id="other"))
        with pytest.raises(TrelloError, match="trello_transport_error"):
            await client.create_card(SimpleNamespace(id="selected"))
    # Restart/reload the manifest: no second POST is allowed for either same or other row.
    async with probe.live_client(probe.State(tmp_path), tmp_path / "not-read") as client:
        with pytest.raises(TrelloError, match="probe_extra_create_forbidden"):
            await client.create_card(SimpleNamespace(id="selected"))
    assert calls.count("POST") == 1


@pytest.mark.asyncio
async def test_snapshot_pages_and_rejects_repeated_page() -> None:
    calls: list[dict[str, str]] = []

    class Client:
        config = SimpleNamespace(board_id="board")

        async def _request(self, *_: Any, params: dict[str, str]) -> Any:
            calls.append(params.copy())
            if "before" not in params:
                return [{"id": str(i), "idList": "list", "closed": False} for i in range(1000)]
            return [{"id": "last", "idList": "list", "closed": True}]

    result = await probe.snapshot(Client())
    assert len(result) == 1001
    assert calls[1]["before"] == "999"
    assert result["last"]["closed"] is True

    class Repeating(Client):
        async def _request(self, *_: Any, params: dict[str, str]) -> Any:
            return [{"id": str(i)} for i in range(1000)]

    with pytest.raises(probe.ProbeError, match="probe_snapshot_paging_not_advancing"):
        await probe.snapshot(Repeating())


@pytest.mark.asyncio
async def test_existing_card_cannot_be_moved(tmp_path: Path) -> None:
    state = probe.State(tmp_path)
    state.data = {"baseline_cards": {"old": {}}}
    row = SimpleNamespace(delivery_state="linked", trello_card_id="old")
    # Fails before any provider call, so a client is deliberately absent.
    with pytest.raises(probe.ProbeError, match="probe_existing_card_is_protected"):
        await probe.assert_own_card(state, None, row)


def test_lock_reloads_manifest_to_prevent_stale_create_guard(tmp_path: Path) -> None:
    first, stale = probe.State(tmp_path), probe.State(tmp_path)
    first.data = {"version": 1, "create_started": True}
    first.save()
    with stale.lock():
        assert stale.data["create_started"] is True
    assert first.path.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_selection_cannot_reset_after_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uuid

    state = probe.State(tmp_path)
    selected = str(uuid.uuid4())
    state.data = {
        "version": 1,
        "create_started": True,
        "live_request_id": selected,
        "local_only_request_id": str(uuid.uuid4()),
    }

    # Repeat init is a no-op: it cannot restore the seeded row over an adopted one.
    async def accounts(_: probe.State) -> None:
        pass

    monkeypatch.setattr(probe, "ensure_local_emails", accounts)
    result = await probe.initialize(state)
    assert result["live_request_id"] == selected
    with pytest.raises(probe.ProbeError, match="probe_selection_locked_after_create"):
        await probe.adopt(state, uuid.uuid4())
    assert state.data["live_request_id"] == selected
