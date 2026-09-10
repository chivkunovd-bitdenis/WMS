"""WMS-397/WMS-399: in-app chat between seller and fulfillment.

Adds four tables to store conversations, participants, messages and
attachments. The chat reuses existing users/sellers/permissions — no separate
account system, no per-document channels. Exactly one *main* chat can exist
per (tenant, seller); additional *extra* chats have no such uniqueness.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260910_0300"
down_revision = "20260908_0257"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "seller_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("sellers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chat_conversations_tenant_id",
        "chat_conversations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_chat_conversations_seller",
        "chat_conversations",
        ["tenant_id", "seller_id"],
    )
    op.create_index(
        "uq_chat_conversations_main",
        "chat_conversations",
        ["tenant_id", "seller_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'main'"),
        sqlite_where=sa.text("kind = 'main'"),
    )

    op.create_table(
        "chat_participants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "added_by_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "conversation_id", "user_id", name="uq_chat_participants_conv_user"
        ),
    )
    op.create_index(
        "ix_chat_participants_tenant_id",
        "chat_participants",
        ["tenant_id"],
    )
    op.create_index(
        "ix_chat_participants_conversation_id",
        "chat_participants",
        ["conversation_id"],
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("client_message_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("attached_document", sa.JSON(), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "author_user_id",
            "client_message_id",
            name="uq_chat_messages_author_client_id",
        ),
    )
    op.create_index(
        "ix_chat_messages_tenant_id",
        "chat_messages",
        ["tenant_id"],
    )
    op.create_index(
        "ix_chat_messages_conv_created",
        "chat_messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploader_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("is_image", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chat_attachments_tenant_id",
        "chat_attachments",
        ["tenant_id"],
    )
    op.create_index(
        "ix_chat_attachments_message",
        "chat_attachments",
        ["message_id"],
    )
    op.create_index(
        "ix_chat_attachments_uploader",
        "chat_attachments",
        ["tenant_id", "uploader_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_uploader", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_message", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_tenant_id", table_name="chat_attachments")
    op.drop_table("chat_attachments")

    op.drop_index("ix_chat_messages_conv_created", table_name="chat_messages")
    op.drop_index("ix_chat_messages_tenant_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index(
        "ix_chat_participants_conversation_id", table_name="chat_participants"
    )
    op.drop_index("ix_chat_participants_tenant_id", table_name="chat_participants")
    op.drop_table("chat_participants")

    op.drop_index("uq_chat_conversations_main", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_seller", table_name="chat_conversations")
    op.drop_index("ix_chat_conversations_tenant_id", table_name="chat_conversations")
    op.drop_table("chat_conversations")
