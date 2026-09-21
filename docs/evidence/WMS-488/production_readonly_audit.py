"""C9/C11: run inside the released API container; only SELECT and local ASGI GET.

No login, tokens, task dispatch, external HTTP, or production writes. Authentication
is replaced with existing users' non-secret authorization fields; real route and
SQL authorization remain. This does not test JWT validation or browser sessions.
Output contains scenario labels, counts, statuses and verdicts, never identities,
URLs, catalogue text, job payload/result/error values, or exception messages.

Run from /app: python /path/to/production_readonly_audit.py
Exit 0: observed checks pass; 1: violation/error; 2: required job class absent.
An absent class is not proof that its authorization works: cover it in test DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from app.api import (
    background_jobs,
    inventory_balances,
    products,
    reports,
    scan_resolver,
)
from app.api.deps import get_current_user
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import SessionLocal, get_db
from app.models.background_job import BackgroundJob
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User
from fastapi import FastAPI
from sqlalchemy import select, text

AVPACK_SLUG = "avpack-9uczh"
SAMPLE_LIMIT = 3  # Per job type and scenario; includes newest and oldest rows.
# Producer and result of each type are seller-scoped, including three FF-started
# syncs. Initiator alone is not an ownership or authorization signal.
SELLER_JOB_TYPES = frozenset({
    "wildberries_cards_sync",
    "storage_measurement_rebuild",
    "wildberries_supplies_sync",
    "wildberries_marketplace_orders_sync",
    "fbs_stock_sync",
})
SAFE_SELLER_ERROR = "Не удалось выполнить задачу"
JOB_CLASSES = ("home", "foreign", "tenant-wide", "ff-only")
PRIVATE_JOB_FIELDS = frozenset({"payload_json", "result_json", "error_message"})


@asynccontextmanager
async def readonly_session(session_factory=SessionLocal):
    async with session_factory() as session:
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text("SET LOCAL statement_timeout = '15000ms'"))
            if await session.scalar(text("SHOW transaction_read_only")) != "on":
                raise RuntimeError("readonly_not_enabled")
        elif dialect == "sqlite":  # Synthetic validation only; never a prod fallback.
            await session.execute(text("PRAGMA query_only = ON"))
            if await session.scalar(text("PRAGMA query_only")) != 1:
                raise RuntimeError("readonly_not_enabled")
        else:
            raise RuntimeError("unsupported_readonly_database")
        try:
            yield session
        finally:
            await session.rollback()


def make_app(session_factory=SessionLocal, *, job_router=None):
    app = FastAPI()
    for module in (products, inventory_balances, reports, scan_resolver):
        app.include_router(module.router)
    app.include_router(background_jobs.router if job_router is None else job_router)

    async def database():
        async with readonly_session(session_factory) as session:
            yield session

    app.dependency_overrides[get_db] = database
    return app


def as_uuid(value):
    try:
        return uuid.UUID(value) if isinstance(value, str) else None
    except ValueError:
        return None


@dataclass(frozen=True)
class JobReference:
    id: uuid.UUID
    job_type: str
    seller_id: uuid.UUID | None
    has_request: bool
    requester_id: uuid.UUID | None


def job_class(job: JobReference, user: User) -> str:
    if job.job_type not in SELLER_JOB_TYPES:
        return "ff-only"
    if job.seller_id is None:
        return "tenant-wide"
    return "home" if job.seller_id == user.seller_id else "foreign"


async def load_job_references(session, tenant_id):
    # Deliberately select ownership metadata, not full JSON blobs or error text.
    rows = await session.execute(
        select(
            BackgroundJob.id,
            BackgroundJob.job_type,
            BackgroundJob.payload_json["seller_id"].as_string(),
            BackgroundJob.payload_json["request_id"].as_string(),
            BackgroundJob.payload_json["requested_by_user_id"].as_string(),
        )
        .where(BackgroundJob.tenant_id == tenant_id)
        .order_by(BackgroundJob.created_at.desc(), BackgroundJob.id)
    )
    return [
        JobReference(row[0], row[1], as_uuid(row[2]), bool(row[3]), as_uuid(row[4]))
        for row in rows
    ]


def sample_jobs(candidates):
    # Keep each type represented and include historical rows after the rollout.
    # load_job_references orders newest first; checking only the latest jobs would
    # leave legacy payloads unobserved when many fresh sync jobs already exist.
    by_type = {}
    for job in candidates:
        by_type.setdefault(job.job_type, []).append(job)
    chosen = []
    for group in by_type.values():
        indices = list(dict.fromkeys([0, len(group) - 1, len(group) // 2]))
        chosen.extend(group[index] for index in indices[:SAMPLE_LIMIT])
    return chosen


def set_actor(app, user):
    async def actor():
        return user

    app.dependency_overrides[get_current_user] = actor


async def check_job(client, job, *, allow, home_id=None):
    try:
        response = await client.get(f"/operations/background-jobs/{job.id}")
        body = response.json()
    except Exception as exc:  # noqa: BLE001 - never print private SQL/body in traceback
        return {"verdict": "error", "error_type": type(exc).__name__}
    if allow:
        valid = (
            response.status_code == 200
            and isinstance(body, dict)
            and isinstance(body.get("status"), str)
        )
        if home_id is not None:
            payload = body.get("payload_json") if isinstance(body, dict) else None
            result = body.get("result_json") if isinstance(body, dict) else None
            error = body.get("error_message") if isinstance(body, dict) else None
            valid = (
                valid
                and isinstance(payload, dict)
                and as_uuid(payload.get("seller_id")) == home_id
                and (
                    not isinstance(result, dict)
                    or "seller_id" not in result
                    or as_uuid(result.get("seller_id")) == home_id
                )
                and error in (None, "", SAFE_SELLER_ERROR)
            )
    else:
        # Check that denial does not wrap private fields or a full result in detail.
        valid = (
            response.status_code in (403, 404)
            and isinstance(body, dict)
            and not (PRIVATE_JOB_FIELDS & body.keys())
            and set(body) <= {"detail"}
            and isinstance(body.get("detail"), str)
        )
    return {"status": response.status_code, "verdict": "pass" if valid else "fail"}


async def audit_jobs(app, client, session, users, tenant_id):
    output = []
    jobs = await load_job_references(session, tenant_id)
    sellers = [
        u for u in users if u.tenant_id == tenant_id and u.role == FULFILLMENT_SELLER
    ]
    admins = [
        u for u in users if u.tenant_id == tenant_id and u.role == FULFILLMENT_ADMIN
    ]
    for index, user in enumerate(sellers, 1):
        set_actor(app, user)
        for category in JOB_CLASSES:
            candidates = [
                job
                for job in jobs
                if (
                    job_class(job, user) == category
                    or category == "tenant-wide"
                    and job.seller_id is None
                )
            ]
            checks = [
                await check_job(
                    client,
                    job,
                    allow=category == "home",
                    home_id=user.seller_id if category == "home" else None,
                )
                for job in sample_jobs(candidates)
            ]
            output.append(
                {
                    "audit": "background-jobs",
                    "actor": f"seller-{index}",
                    "manager": bool(user.can_manage_seller_shops),
                    "scenario": category,
                    "available": len(candidates),
                    "checked": len(checks),
                    "verdict": combined_verdict(checks),
                    "checks": checks,
                }
            )
    for index, user in enumerate(admins, 1):
        set_actor(app, user)
        # Sorting print jobs intentionally remain private to their initiating FF
        # operator. Do not call a rightful 404 a regression in FF-wide access.
        candidates = [
            job
            for job in jobs
            if not (
                job.job_type == "fbs_label_print"
                and job.has_request
                and job.requester_id != user.id
            )
        ]
        # Include each class available to a sample seller, not just the newest jobs.
        categories = {}
        for job in candidates:
            category = job_class(job, sellers[0]) if sellers else "ff-only"
            categories.setdefault(category, []).append(job)
        for category, group in categories.items():
            checks = [
                await check_job(client, job, allow=True) for job in sample_jobs(group)
            ]
            output.append(
                {
                    "audit": "background-jobs",
                    "actor": f"ff-admin-{index}",
                    "scenario": f"ff-control-{category}",
                    "available": len(group),
                    "checked": len(checks),
                    "verdict": combined_verdict(checks),
                    "checks": checks,
                }
            )
    if not sellers or not admins:
        output.append(
            {
                "audit": "background-jobs",
                "scenario": "actors",
                "verdict": "not-covered",
                "sellers": len(sellers),
                "ff_admins": len(admins),
            }
        )
    return output


def combined_verdict(checks):
    if not checks:
        return "not-covered"
    if any(check["verdict"] == "error" for check in checks):
        return "error"
    if any(check["verdict"] == "fail" for check in checks):
        return "fail"
    if any(check["verdict"] == "not-covered" for check in checks):
        return "not-covered"
    return "pass"


def ids_from(value):
    if isinstance(value, list):
        return set().union(*(ids_from(row) for row in value)) if value else set()
    if isinstance(value, dict):
        result = {str(value[k]) for k in ("id", "product_id") if value.get(k)}
        for item in value.values():
            if isinstance(item, (dict, list)):
                result.update(ids_from(item))
        return result
    return set()


async def audit_catalog(app, client, users, product_rows, tenant_id):
    ownership = {str(p.id): (p.seller_id, p.tenant_id) for p in product_rows}
    owners = Counter(p.seller_id for p in product_rows if p.tenant_id == tenant_id)
    if not owners:
        return [
            {
                "audit": "catalog",
                "verdict": "not-covered",
                "scenario": "catalog-fixture",
            }
        ]
    victim_owner = owners.most_common(1)[0][0]
    victim = next(
        p
        for p in product_rows
        if p.tenant_id == tenant_id and p.seller_id == victim_owner
    )
    output = []
    for index, user in enumerate(users, 1):
        set_actor(app, user)
        paths = [
            ("products", "/products"),
            ("wb-catalog", "/products/wb-catalog"),
            ("linked-wb-catalog", "/products/linked-wb-catalog"),
            ("ff-catalog", "/products/ff-catalog"),
            ("ff-catalog-page", "/products/ff-catalog-page"),
            ("inventory-summary", "/operations/inventory-balances/summary"),
        ]
        if user.tenant_id != tenant_id:
            paths = [
                (label, path + "?search=" + quote(victim.sku_code, safe=""))
                for label, path in paths[:5]
            ]
            paths.append(
                (
                    "scan",
                    "/operations/scan/resolve?code=" + quote(victim.sku_code, safe=""),
                )
            )
        else:
            paths += [
                ("dimension-history", f"/products/{victim.id}/dimensions/history"),
                ("fbs-rule", f"/products/{victim.id}/fbs-rule"),
                ("stock-directions", f"/products/{victim.id}/stock-directions"),
                ("sku-search", "/products?search=" + quote(victim.sku_code, safe="")),
                (
                    "wb-sku-search",
                    "/products/wb-catalog?search=" + quote(victim.sku_code, safe=""),
                ),
                (
                    "scan",
                    "/operations/scan/resolve?code=" + quote(victim.sku_code, safe=""),
                ),
                (
                    "inventory-report",
                    f"/reports/inventory?date_from=2026-09-01T00:00:00Z&date_to=2026-09-21T23:59:59Z&seller_id={victim.seller_id}",
                ),
            ]
        checks = []
        for label, path in paths:
            try:
                response = await client.get(path)
                data = response.json()
            except Exception as exc:  # noqa: BLE001 - never print private SQL/body in traceback
                checks.append(
                    {
                        "scenario": label,
                        "verdict": "error",
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            returned = ids_from(data) & ownership.keys()
            foreign_seller = sum(
                user.role == FULFILLMENT_SELLER and ownership[pid][0] != user.seller_id
                for pid in returned
            )
            foreign_tenant = sum(
                ownership[pid][1] != user.tenant_id for pid in returned
            )
            checks.append(
                {
                    "scenario": label,
                    "status": response.status_code,
                    "products": len(returned),
                    "foreign_seller_count": foreign_seller,
                    "foreign_tenant_count": foreign_tenant,
                    "verdict": "fail"
                    if foreign_seller
                    or foreign_tenant
                    or response.status_code not in (200, 403, 404, 409)
                    else "pass",
                }
            )
        output.append(
            {
                "audit": "catalog",
                "actor": f"account-{index}",
                "role": user.role,
                "target_tenant": user.tenant_id == tenant_id,
                "verdict": combined_verdict(checks),
                "checks": checks,
            }
        )
    return output


async def run_audit(
    session_factory=SessionLocal, *, include_catalog=True, job_router=None
):
    app = make_app(session_factory, job_router=job_router)
    async with readonly_session(session_factory) as session:
        tenant_id = await session.scalar(
            select(Tenant.id).where(Tenant.slug == AVPACK_SLUG)
        )
        if tenant_id is None:
            return [{"audit": "target-tenant", "verdict": "not-covered"}]
        # Do not load user email, name, password hash, or other unrelated columns.
        rows = (
            await session.execute(
                select(
                    User.id,
                    User.tenant_id,
                    User.seller_id,
                    User.role,
                    User.can_manage_seller_shops,
                )
                .where(User.role.in_([FULFILLMENT_SELLER, FULFILLMENT_ADMIN]))
                .order_by(User.id)
            )
        ).all()
        users = [
            User(
                id=row.id,
                tenant_id=row.tenant_id,
                seller_id=row.seller_id,
                role=row.role,
                can_manage_seller_shops=row.can_manage_seller_shops,
            )
            for row in rows
        ]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://audit"
        ) as client:
            output = await audit_jobs(app, client, session, users, tenant_id)
            if include_catalog:
                product_rows = (
                    await session.execute(
                        select(
                            Product.id,
                            Product.seller_id,
                            Product.tenant_id,
                            Product.sku_code,
                        )
                    )
                ).all()
                output += await audit_catalog(
                    app, client, users, product_rows, tenant_id
                )
        return output


async def main():
    # HTTP/SQL log messages may contain request IDs, paths, or SQL parameters.
    logging.disable(logging.CRITICAL)
    try:
        output = await run_audit()
    except Exception as exc:  # noqa: BLE001 - never print private SQL/body in traceback
        output = [
            {"audit": "execution", "verdict": "error", "error_type": type(exc).__name__}
        ]
    for record in output:
        print(json.dumps(record, ensure_ascii=False), flush=True)
    verdict = combined_verdict(output)
    print(json.dumps({"audit": "summary", "verdict": verdict}), flush=True)
    return 1 if verdict in ("fail", "error") else 2 if verdict == "not-covered" else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
