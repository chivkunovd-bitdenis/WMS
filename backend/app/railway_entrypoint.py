"""One image, three Railway services; API migrates, worker/beat require that head.

Use railway.toml for API, railway.worker.toml and railway.beat.toml for background
services. All three must reference the SAME DATABASE_URL, CELERY_BROKER_URL,
WMS_SECRETS_FERNET_KEY, WITHDRAWAL_ENVIRONMENT and submit flag in Railway.
This entrypoint proves configuration prerequisites, not a running deployment.
"""

from __future__ import annotations

import asyncio
import os

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from alembic import command
from app.core.settings import settings


def role_command(role: str) -> list[str]:
    if role == "api":
        return ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000")]
    if role in {"worker", "beat"}:
        return ["celery", "-A", "app.celery_app", role, "--loglevel=info"]
    raise ValueError("WMS_SERVICE_ROLE must be api, worker or beat")


async def require_migration_head(config: Config) -> None:
    from app.db.session import engine

    expected = set(ScriptDirectory.from_config(config).get_heads())
    try:
        async with engine.connect() as connection:
            actual = set(
                (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalars()
            )
        if actual != expected:
            raise RuntimeError("Run the API migration release before worker/beat")
    finally:
        await engine.dispose()


def main() -> None:
    role = os.environ.get("WMS_SERVICE_ROLE", "api")
    args = role_command(role)
    if not settings.celery_broker_url or not settings.celery_broker_url.startswith(
        ("redis://", "rediss://")
    ):
        raise RuntimeError("A shared Redis CELERY_BROKER_URL is required for API/worker/beat")
    if not os.environ.get("WMS_SECRETS_FERNET_KEY"):
        raise RuntimeError("A shared WMS_SECRETS_FERNET_KEY is required for API/worker/beat")
    config = Config("alembic.ini")
    if role == "api":
        command.upgrade(config, "head")
    else:
        asyncio.run(require_migration_head(config))
    os.execvp(args[0], args)


if __name__ == "__main__":
    main()
