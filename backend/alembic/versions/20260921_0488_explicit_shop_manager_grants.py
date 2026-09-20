"""WMS-488: preserve existing delegated managers as explicit grants.

Email eligibility is retired in application code. This one-time conversion
requires an existing delegation and never creates a delegation or enables one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

revision = "20260921_0488"
down_revision = "20260913_0306"
branch_labels = None
depends_on = None

# Freeze the retired rule here; migration behavior must not follow future app code.
_LEGACY_MARKERS = ("vitalik", "vitaliy", "виталий", "denmark", "denmarks", "денмарк")


class _LegacyAllowlist(BaseSettings):
    # Frozen old configuration semantics, without loading live application settings.
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")
    emails: str = Field(
        default="",
        validation_alias=AliasChoices(
            "shop_manager_emails", "WMS_SHOP_MANAGER_EMAILS", "SHOP_MANAGER_EMAILS"
        ),
    )


def upgrade() -> None:
    connection = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("seller_id", sa.Uuid()),
        sa.column("email", sa.String()),
        sa.column("role", sa.String()),
        sa.column("can_manage_seller_shops", sa.Boolean()),
    )
    sellers = sa.table(
        "sellers",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
    )
    delegations = sa.table(
        "seller_shop_delegations",
        sa.column("user_id", sa.Uuid()),
        sa.column("target_seller_id", sa.Uuid()),
    )
    home = sellers.alias("home")
    target = sellers.alias("target")
    candidates = connection.execute(
        sa.select(users.c.id, users.c.email)
        .select_from(
            users.join(
                home,
                sa.and_(
                    home.c.id == users.c.seller_id,
                    home.c.tenant_id == users.c.tenant_id,
                ),
            )
            .join(delegations, delegations.c.user_id == users.c.id)
            .join(
                target,
                sa.and_(
                    target.c.id == delegations.c.target_seller_id,
                    target.c.tenant_id == users.c.tenant_id,
                    target.c.id != users.c.seller_id,
                ),
            )
        )
        .where(users.c.role == "fulfillment_seller", users.c.can_manage_seller_shops.is_(False))
        .distinct()
    ).all()
    configured = _LegacyAllowlist().emails
    allowed = {email.strip().lower() for email in configured.split(",") if email.strip()}
    for user_id, raw_email in candidates:
        email = (raw_email or "").strip().lower()
        if any(marker in email for marker in _LEGACY_MARKERS) or email in allowed:
            # Disabled delegations are intentional existing grants too: the old
            # manager could enable them through the shop selector at any time.
            connection.execute(
                users.update().where(users.c.id == user_id).values(can_manage_seller_shops=True)
            )


def downgrade() -> None:
    # Explicit grants are compatible with the previous application. Without an
    # extra audit table we cannot distinguish migrated grants from later manual
    # grants, so rollback must not revoke real permissions.
    pass
