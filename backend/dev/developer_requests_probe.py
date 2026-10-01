"""WMS-624 isolated acceptance harness; no live call without an explicit live command.

Run from backend with its Python environment. State/credentials must stay outside Git.
The production API and sync services are reused; only the single manifest request may
be delivered, and the harness permits at most one external create attempt per run.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
import os
import stat
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

BACKEND = Path(__file__).resolve().parents[1]
CHECKOUT = BACKEND.parent
DEFAULT_STATE = Path.home() / ".local/state/wms624-live-probe"
BOARD_LINK = "WPtAFgrM"
LISTS = {
    "review": "6abe7ba2fd030d99fda2a8d5",
    "queued": "6abe7bce7b7c1e08c889ecd3",
    "in_progress": "6abe7bd83d572a7b4165127f",
    "completed": "6abe7be85614ea1f234a4b88",
}
LABEL_ID = "6abe7ae514ec9eb3faaae3d5"
TEST_PASSWORD = "WMS624-local-test-only"
FF_NAME = "WMS624 Test FF"
SELLER_NAME = "WMS624 Test Seller"
EMAILS = {FF_NAME: "ff@wms624.example.com", SELLER_NAME: "seller@wms624.example.com"}


class ProbeError(Exception):
    """A fixed diagnostic code safe to print without provider content or credentials."""


def check(condition: bool, code: str) -> None:
    if not condition:
        raise ProbeError(code)


def outside_checkout(path: Path) -> Path:
    path = path.expanduser().resolve()
    check(not path.is_relative_to(CHECKOUT), "probe_path_must_be_outside_git")
    # Also reject the primary checkout when invoked from one of its worktrees.
    primary = next((p for p in CHECKOUT.parents if p.name == ".worktrees"), None)
    if primary:
        check(not path.is_relative_to(primary.parent), "probe_path_must_be_outside_git")
    return path


def write_private(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".writing")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class State:
    def __init__(self, directory: Path) -> None:
        self.directory = outside_checkout(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "probe-state.json"
        self.data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            check(self.data.get("version") == 1, "probe_state_version_invalid")

    def save(self) -> None:
        write_private(self.path, self.data)

    @contextmanager
    def lock(self) -> Iterator[None]:
        with (self.directory / "probe.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ProbeError("probe_another_command_running") from None
            try:
                self.reload()
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def configure_local(state: State) -> None:
    check(not (state.directory / ".env").exists(), "probe_state_directory_must_not_have_dotenv")
    os.chdir(state.directory)  # Settings must never read the checkout's .env.
    sys.path.insert(0, str(BACKEND))
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{state.directory / 'wms_test_624_probe.sqlite'}",
            "JWT_SECRET_KEY": "wms624-isolated-local-test-only-signing-key-2026",
            "APP_ENV": "development",
            "WMS_DATA_DIR": str(state.directory / "data"),
            "WMS_AUTO_CREATE_SCHEMA": "0",
            "WMS_BOOTSTRAP_ADMIN": "0",
            "WMS_ALLOW_PUBLIC_REGISTRATION": "false",
        }
    )
    # Never inherit production/provider credentials into the local API process.
    for name in list(os.environ):
        if name.startswith("TRELLO_") or name in {"CELERY_BROKER_URL", "WMS_SECRETS_FERNET_KEY"}:
            del os.environ[name]
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def login(client: httpx.AsyncClient, name: str) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={
            "email": EMAILS[name],
            "password": TEST_PASSWORD,
            "portal": "seller" if name == SELLER_NAME else "fulfillment",
        },
    )
    check(response.status_code == 200, "probe_local_login_failed")
    return {"Authorization": "Bearer " + str(response.json()["access_token"])}


async def ensure_local_emails(state: State) -> None:
    from app.db.session import SessionLocal
    from app.models.user import User

    async with SessionLocal() as session:
        for field, name in (("ff_user_id", FF_NAME), ("seller_user_id", SELLER_NAME)):
            user = await session.get(User, uuid.UUID(state.data[field]))
            check(
                user is not None
                and str(user.tenant_id) == state.data["tenant_id"]
                and user.full_name == name,
                "probe_account_identity_invalid",
            )
            assert user is not None
            check(user.email in (None, EMAILS[name]), "probe_account_email_unexpected")
            user.email = EMAILS[name]
        await session.commit()


async def initialize(state: State) -> dict[str, Any]:
    if state.data.get("local_only_request_id") and state.data.get("live_request_id"):
        await ensure_local_emails(state)
        return {
            "initialized": True,
            "live_request_id": state.data["live_request_id"],
            "local_only_request_id": state.data["local_only_request_id"],
            "state_dir": str(state.directory),
        }
    check(not state.data.get("create_started"), "probe_cannot_reseed_after_create")
    from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
    from app.db.session import SessionLocal, engine
    from app.main import create_app
    from app.models import Base
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services.passwords import hash_password

    if not state.data:
        run_id = uuid.uuid4()
        state.data = {"version": 1, "run_id": str(run_id), "create_started": False}
        for field in ("tenant_id", "seller_id", "ff_user_id", "seller_user_id"):
            state.data[field] = str(uuid.uuid5(run_id, field))
        state.save()
    async with engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        await connection.run_sync(Base.metadata.create_all)
    tenant_id = uuid.UUID(state.data["tenant_id"])
    seller_id = uuid.UUID(state.data["seller_id"])
    async with SessionLocal() as session:
        if await session.get(Tenant, tenant_id) is None:
            session.add(
                Tenant(
                    id=tenant_id,
                    name="[WMS-624 TEST] Проверка интеграции",
                    slug="wms624-live-probe",
                )
            )
            await session.flush()
            session.add(
                Seller(id=seller_id, tenant_id=tenant_id, name="[WMS-624 TEST] Тестовый селлер")
            )
            await session.flush()
        for field, name, role, shop in (
            ("ff_user_id", FF_NAME, FULFILLMENT_ADMIN, None),
            ("seller_user_id", SELLER_NAME, FULFILLMENT_SELLER, seller_id),
        ):
            user_id = uuid.UUID(state.data[field])
            if await session.get(User, user_id) is None:
                session.add(
                    User(
                        id=user_id,
                        tenant_id=tenant_id,
                        seller_id=shop,
                        full_name=name,
                        email=EMAILS[name],
                        role=role,
                        password_hash=hash_password(TEST_PASSWORD),
                    )
                )
        await session.commit()
    await ensure_local_emails(state)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://probe"
    ) as client:
        for kind, name, fields in (
            (
                "bug",
                FF_NAME,
                {
                    "description": (
                        "[WMS-624 LOCAL ONLY] Проверка формы ошибки без доставки в Trello."
                    )
                },
            ),
            (
                "improvement",
                SELLER_NAME,
                {
                    "screen": "[WMS-624 TEST] Единственная тестовая карточка интеграции",
                    "problem": (
                        "Проверка полного пути: форма WMS, база, приватная доска Trello "
                        "и обратное чтение статуса."
                    ),
                    "proposal": (
                        "Провести только эту тестовую карточку по четырём клиентским "
                        "колонкам; существующие карточки не изменять."
                    ),
                },
            ),
        ):
            response = await client.post(
                "/developer-requests",
                headers=await login(client, name),
                json={
                    "idempotency_key": str(uuid.uuid5(uuid.UUID(state.data["run_id"]), kind)),
                    "type": kind,
                    "page_url": "/seller/products" if kind == "improvement" else "/app/ff/fbs",
                    **fields,
                },
            )
            check(response.status_code == 200, "probe_local_seed_request_failed")
            state.data["live_request_id" if kind == "improvement" else "local_only_request_id"] = (
                response.json()["id"]
            )
        state.save()
    return {
        "initialized": True,
        "live_request_id": state.data["live_request_id"],
        "local_only_request_id": state.data["local_only_request_id"],
        "state_dir": str(state.directory),
    }


def load_credentials(path: Path) -> dict[str, str]:
    path = outside_checkout(path)
    check(stat.S_IMODE(path.stat().st_mode) == 0o600, "probe_config_must_be_mode_600")
    value = json.loads(path.read_text())
    check(isinstance(value, dict), "probe_config_invalid")
    for field in ("TRELLO_API_KEY", "TRELLO_TOKEN"):
        check(isinstance(value.get(field), str) and bool(value[field]), "probe_credentials_missing")
    check(value.get("board_short_link", BOARD_LINK) == BOARD_LINK, "probe_board_not_approved")
    names = {
        "review": "REVIEW",
        "queued": "QUEUED",
        "in_progress": "IN_PROGRESS",
        "completed": "COMPLETED",
    }
    for status_name, list_id in LISTS.items():
        check(
            value.get(f"TRELLO_{names[status_name]}_LIST_ID", list_id) == list_id,
            "probe_list_not_approved",
        )
    check(value.get("TRELLO_CLIENT_LABEL_ID", LABEL_ID) == LABEL_ID, "probe_label_not_approved")
    return {"key": value["TRELLO_API_KEY"], "token": value["TRELLO_TOKEN"]}


async def snapshot(client: Any) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    cursor = ""
    while True:
        params = {
            "filter": "all",
            "fields": "id,idList,idBoard,closed",
            "limit": "1000",
            "sort": "-id",
        }
        if cursor:
            params["before"] = cursor
        page = await client._request("GET", f"boards/{client.config.board_id}/cards", params=params)
        check(isinstance(page, list), "probe_snapshot_invalid")
        for item in page:
            check(
                isinstance(item, dict) and isinstance(item.get("id"), str), "probe_snapshot_invalid"
            )
            check(item["id"] not in cards, "probe_snapshot_paging_not_advancing")
            cards[item["id"]] = {
                field: item.get(field) for field in ("idList", "idBoard", "closed")
            }
        if len(page) < 1000:
            return cards
        cursor = page[-1]["id"]


@asynccontextmanager
async def live_client(state: State, config_path: Path) -> AsyncIterator[Any]:
    from app.services.developer_request_trello import TrelloClient, TrelloConfig, TrelloError

    credentials = load_credentials(config_path)
    async with httpx.AsyncClient(follow_redirects=False) as http:
        lookup = TrelloClient(
            TrelloConfig(
                credentials["key"],
                credentials["token"],
                BOARD_LINK,
                {v: k for k, v in LISTS.items()},
                LABEL_ID,
            ),
            http,
        )
        board = await lookup._request(
            "GET", f"boards/{BOARD_LINK}", params={"fields": "id,shortLink,prefs,closed"}
        )
        check(
            isinstance(board, dict)
            and board.get("shortLink") == BOARD_LINK
            and isinstance(board.get("id"), str),
            "probe_board_identity_invalid",
        )
        config = TrelloConfig(
            credentials["key"],
            credentials["token"],
            board["id"],
            {v: k for k, v in LISTS.items()},
            LABEL_ID,
        )

        class OneCardClient(TrelloClient):
            async def create_card(self, request: Any) -> dict[str, Any]:
                if str(request.id) != state.data.get("live_request_id") or state.data.get(
                    "create_started"
                ):
                    raise TrelloError("probe_extra_create_forbidden")
                check(bool(state.data.get("preflight_at")), "probe_preflight_required")
                state.data["create_started"] = True
                state.save()  # Durable BEFORE network: a restart cannot create a second card.
                return await super().create_card(request)

        client = OneCardClient(config, http)
        await client.check_board()
        label = await client._request("GET", f"labels/{LABEL_ID}")
        check(
            label.get("idBoard") == board["id"]
            and label.get("name") == "Клиент"
            and label.get("color") == "blue",
            "probe_client_label_invalid",
        )
        if "board_id" in state.data:
            check(state.data["board_id"] == board["id"], "probe_board_identity_changed")
        state.data["board_id"] = board["id"]
        if "baseline_cards" not in state.data:
            check(not state.data.get("create_started"), "probe_baseline_missing_after_create")
            state.data["baseline_cards"] = await snapshot(client)
            state.data["preflight_at"] = datetime.now(UTC).isoformat()
        state.save()
        yield client


async def adopt(state: State, request_id: uuid.UUID | None) -> dict[str, Any]:
    check(request_id is not None, "probe_request_id_required")
    check(not state.data.get("create_started"), "probe_selection_locked_after_create")
    from app.db.session import SessionLocal
    from app.models.developer_request import DeveloperRequest

    async with SessionLocal() as session:
        row = await session.get(DeveloperRequest, request_id)
        check(row is not None, "probe_request_not_found")
        assert row is not None
        check(
            row.delivery_state == "pending"
            and row.trello_card_id is None
            and row.create_attempts == 0,
            "probe_selected_request_already_attempted",
        )
        previous = state.data.get("live_request_id")
        state.data["live_request_id"] = str(row.id)
        try:
            await row_for_probe(state)
        except Exception:
            state.data["live_request_id"] = previous
            raise
        state.save()
    return {"selected_request_id": str(request_id), "external_create_started": False}


async def row_for_probe(state: State) -> Any:
    from app.db.session import SessionLocal
    from app.models.developer_request import DeveloperRequest

    check(bool(state.data.get("live_request_id")), "probe_init_required")
    async with SessionLocal() as session:
        row = await session.get(DeveloperRequest, uuid.UUID(state.data["live_request_id"]))
        check(
            row is not None
            and str(row.tenant_id) == state.data["tenant_id"]
            and str(row.created_by_user_id) == state.data["seller_user_id"]
            and row.type == "improvement"
            and row.title.startswith("[WMS-624 TEST]"),
            "probe_request_identity_invalid",
        )
        return row


async def sync_only_probe(state: State, client: Any) -> Any:
    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models.developer_request import DeveloperRequest
    from app.services.developer_request_sync import sync_request

    row = await row_for_probe(state)
    async with SessionLocal() as session:
        await session.execute(
            update(DeveloperRequest)
            .where(DeveloperRequest.id == row.id)
            .values(next_sync_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    await sync_request(
        row.id, client
    )  # Never run the batch: the second local form must stay local.
    return await row_for_probe(state)


async def api_readback(api_base: str, request_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=api_base, timeout=15, trust_env=False) as client:
        response = await client.get(
            f"/developer-requests/{request_id}", headers=await login(client, SELLER_NAME)
        )
        check(response.status_code == 200, "probe_api_readback_failed")
        value: dict[str, Any] = response.json()
        return value


async def assert_own_card(state: State, client: Any, row: Any) -> dict[str, Any]:
    from app.services.developer_request_content import marker

    check(row.delivery_state == "linked" and bool(row.trello_card_id), "probe_card_not_linked")
    check(
        row.trello_card_id not in state.data["baseline_cards"], "probe_existing_card_is_protected"
    )
    card = await client._request(
        "GET",
        f"cards/{row.trello_card_id}",
        params={"fields": "id,idBoard,idList,name,desc,idLabels,closed,shortUrl"},
    )
    check(
        card.get("idBoard") == state.data["board_id"]
        and marker(row) in card.get("desc", "").splitlines()
        and "[WMS-624 TEST]" in card.get("name", "")
        and LABEL_ID in card.get("idLabels", [])
        and card.get("closed") is False,
        "probe_created_card_identity_invalid",
    )
    state.data["card_id"] = row.trello_card_id
    state.save()
    return dict(card)


async def run_live(state: State, args: argparse.Namespace) -> dict[str, Any]:
    check(bool(state.data.get("live_request_id")), "probe_init_required")
    check(args.config is not None, "probe_explicit_config_path_required")
    async with live_client(state, Path(args.config)) as client:
        result: dict[str, Any] = {
            "board_id": state.data["board_id"],
            "private_board": True,
            "client_label": "Клиент / blue",
            "baseline_cards": len(state.data["baseline_cards"]),
        }
        if args.command == "preflight":
            return result
        row = await row_for_probe(state)
        if args.command == "deliver":
            row = await sync_only_probe(state, client)
            if row.delivery_state != "linked":
                return {
                    **result,
                    "delivery_state": row.delivery_state,
                    "last_error": row.last_error,
                    "create_attempted": state.data["create_started"],
                    "instruction": (
                        "No new POST permitted. For outcome_unknown, deliver repeats "
                        "production read-only recovery."
                    ),
                }
        card = await assert_own_card(state, client, row)
        visits = []
        if args.command == "cycle":
            statuses = [args.step] if args.step else list(LISTS)
            for status_name in statuses:
                card = await assert_own_card(state, client, await row_for_probe(state))
                if card["idList"] != LISTS[status_name]:
                    # Only the created, marked, non-baseline card may be moved.
                    # No delete/archive operation exists.
                    await client._request(
                        "PUT", f"cards/{row.trello_card_id}", data={"idList": LISTS[status_name]}
                    )
                row = await sync_only_probe(state, client)
                received = await api_readback(args.api_base, str(row.id))
                check(received["status"] == status_name, "probe_status_readback_mismatch")
                visits.append(
                    {
                        "status": status_name,
                        "api_status": received["status"],
                        "at": datetime.now(UTC).isoformat(),
                    }
                )
                state.data.setdefault("status_visits", []).append(visits[-1])
                state.save()
        received = await api_readback(args.api_base, str(row.id))
        current_cards = await snapshot(client)
        unchanged = all(
            current_cards.get(card_id) == before
            for card_id, before in state.data["baseline_cards"].items()
        )
        check(unchanged, "probe_baseline_cards_changed_externally_or_missing")
        result.update(
            card_id=row.trello_card_id,
            card_url=card.get("shortUrl"),
            request_id=str(row.id),
            delivery_state=row.delivery_state,
            api_status=received["status"],
            baseline_unchanged=unchanged,
            status_visits=visits,
        )
        state.data["last_result"] = result
        state.save()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("init", "serve", "adopt", "preflight", "deliver", "cycle", "inspect")
    )
    parser.add_argument("--request-id", type=uuid.UUID)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--config", help="Explicit private JSON path, read only for live commands")
    parser.add_argument("--api-base", default="http://127.0.0.1:18240")
    parser.add_argument("--port", type=int, default=18240)
    parser.add_argument("--step", choices=tuple(LISTS))
    args = parser.parse_args()
    base = urlsplit(args.api_base)
    check(
        base.scheme == "http"
        and base.hostname in {"127.0.0.1", "localhost", "::1"}
        and not base.username
        and not base.password
        and not base.query
        and not base.fragment,
        "probe_api_must_be_loopback",
    )
    state = State(args.state_dir)
    configure_local(state)
    if args.command == "serve":
        import uvicorn

        check(bool(state.data.get("live_request_id")), "probe_init_required")
        uvicorn.run(
            "app.main:create_app",
            factory=True,
            host="127.0.0.1",
            port=args.port,
            access_log=False,
            log_level="warning",
        )
        return
    with state.lock():
        if args.command == "init":
            result = asyncio.run(initialize(state))
        elif args.command == "adopt":
            result = asyncio.run(adopt(state, args.request_id))
        elif args.command == "inspect":
            result = {
                key: state.data.get(key)
                for key in (
                    "run_id",
                    "live_request_id",
                    "local_only_request_id",
                    "create_started",
                    "card_id",
                    "last_result",
                    "status_visits",
                )
            }
        else:
            result = asyncio.run(run_live(state, args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except ProbeError as error:
        print(json.dumps({"error": str(error)}))
        raise SystemExit(1) from None
    except Exception as error:
        # Never dump provider errors, request objects, private config or a traceback.
        print(json.dumps({"error": "probe_failed", "exception_type": type(error).__name__}))
        raise SystemExit(1) from None
