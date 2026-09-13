"""Explicit opt-in migration proof; never use the warehouse/UI database."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command


def test_existing_accounts_survive_identity_migration(monkeypatch):
    url = os.environ.get("WMS443_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated WMS443 migration database")
    parsed = make_url(url)
    assert parsed.host in ("localhost", "127.0.0.1")
    assert parsed.database == "wms443_tests"
    from app.core.settings import settings

    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    engine = create_engine(url)
    command.upgrade(config, "20260911_0304")
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO tenants(id,name,slug) VALUES (:id,'Identity migration',:slug)"),
                     {"id": tenant_id, "slug": f"migration-{tenant_id.hex}"})
        conn.execute(text("""INSERT INTO users(id,tenant_id,email,password_hash,role,
            must_set_password,packaging_rate_kopecks) VALUES
            (:id,:tenant,:email,'dummy-preserved-hash','fulfillment_admin',false,1234)"""),
                     {"id": user_id, "tenant": tenant_id,
                      "email": f"migration-{user_id.hex}@example.com"})
        before = conn.execute(text("SELECT id,tenant_id,email,password_hash,role,"
                                   "must_set_password,packaging_rate_kopecks,created_at "
                                   "FROM users WHERE id=:id"), {"id": user_id}).one()
    command.upgrade(config, "20260913_0443")
    with engine.begin() as conn:
        after = conn.execute(text("SELECT id,tenant_id,email,password_hash,role,"
                                  "must_set_password,packaging_rate_kopecks,created_at "
                                  "FROM users WHERE id=:id"), {"id": user_id}).one()
        assert after == before
        assert conn.execute(text("SELECT full_name,job_title FROM users WHERE id=:id"),
                            {"id": user_id}).one() == (None, None)
    command.downgrade(config, "20260911_0304")
    command.upgrade(config, "20260913_0443")
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO users(id,tenant_id,email,full_name,password_hash,role,
            must_set_password,packaging_rate_kopecks) VALUES
            (:id,:tenant,NULL,'Тестовый Работник','dummy-test-hash',
             'fulfillment_staff',false,0)"""),
                     {"id": uuid.uuid4(), "tenant": tenant_id})
    with pytest.raises(RuntimeError, match="resolving email-free accounts"):
        command.downgrade(config, "20260911_0304")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "20260913_0443"
        assert conn.scalar(text("SELECT count(*) FROM users WHERE tenant_id=:id"),
                           {"id": tenant_id}) == 2
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant_id})
    command.downgrade(config, "20260911_0304")
    engine.dispose()
