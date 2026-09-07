"""Finalize the restored private copy before the first API startup. Never run on staging."""
import json
import secrets
from pathlib import Path
from sqlalchemy import create_engine, text
from app.core.settings import settings
from app.services.integration_fernet import encrypt_secret
from app.services.passwords import hash_password

root = Path("/training")
assert settings.database_url.split("@")[-1] == "db:5432/wms", "Training DB required"
login = json.loads((root / "private/training-login.json").read_text())
tokens = json.loads((root / "private/emulator-tokens.json").read_text())
seller_map = json.loads((root / "private/seller-map.json").read_text())
engine = create_engine(settings.database_url.replace("+psycopg_async", "+psycopg"))
with engine.begin() as c:
    # Make the input gate strict so this cannot reset a running training database.
    pending = c.execute(text("SELECT count(*) FROM users WHERE password_hash = 'training-reset-required'" )).scalar_one()
    total = c.execute(text("SELECT count(*) FROM users")).scalar_one()
    assert pending == total and total > 0, "Expected freshly sanitized snapshot"
    c.execute(text("UPDATE users SET password_hash=:hash, must_set_password=false"),
              {"hash": hash_password(secrets.token_urlsafe(32))})
    for seller_id, keys in seller_map.items():
        assert len(keys) == 1, "Each copied credential must match exactly one emulator seller"
        token = next(token for token, key in tokens.items() if key == keys[0])
        encrypted = encrypt_secret(token)
        c.execute(text("""UPDATE seller_wildberries_credentials
            SET content_token_encrypted=:token, supplies_token_encrypted=:token,
                marketplace_token_encrypted=:token, marketplace_scope_ok=true
            WHERE seller_id=:seller"""), {"token": encrypted, "seller": seller_id})
    c.execute(text("UPDATE marketplace_accounts SET is_active=false, secret_encrypted=NULL, validation_status='not_configured'"))
    # Keep historical users/relationships; add one operator account to the actual staging tenant.
    import uuid
    c.execute(text("""INSERT INTO users
        (id, tenant_id, email, password_hash, role, must_set_password, can_manage_seller_shops, packaging_rate_kopecks)
        VALUES (:id, :tenant, :email, :hash, 'fulfillment_admin', false, true, 0)"""),
        {"id": str(uuid.uuid4()), "tenant": login["tenant_id"], "email": login["email"],
         "hash": hash_password(login["password"])})
    c.execute(text("UPDATE tenants SET subscription_paid_until=NULL WHERE id=:id"), {"id": login["tenant_id"]})
print("Copied credentials replaced; training operator created. Source systems were not contacted.")
