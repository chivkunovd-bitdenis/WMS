"""Резолвер доступа к отчётам в зависимости от роли пользователя.

Раздел «Отчёты» видит:
- ФФ-сотрудник с PERM_INVENTORY/PERM_CELLS: весь tenant
- Селлер: только свой seller_id (жёсткий scope, никакого выбора)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass
class ReportingScope:
    """Доступ пользователя в отчётах.

    Атрибуты:
        tenant_id: обязательный tenant
        seller_ids: None = весь tenant; set с одним/несколькими id = только эти селлеры
        warehouse_ids: None = все склады; set = только эти (зарезервировано для будущего)
        marketplace_ids: None = все МП; set = только эти (зарезервировано)
    """
    tenant_id: uuid.UUID
    seller_ids: set[uuid.UUID] | None = None
    warehouse_ids: set[uuid.UUID] | None = None
    marketplace_ids: set[str] | None = None

    def is_seller_accessible(self, seller_id: uuid.UUID) -> bool:
        """Доступен ли этот селлер в scope."""
        if self.seller_ids is None:
            return True
        return seller_id in self.seller_ids

    def is_warehouse_accessible(self, warehouse_id: uuid.UUID) -> bool:
        """Доступен ли этот склад в scope."""
        if self.warehouse_ids is None:
            return True
        return warehouse_id in self.warehouse_ids

    def is_marketplace_accessible(self, marketplace_id: str) -> bool:
        """Доступен ли этот маркетплейс в scope."""
        if self.marketplace_ids is None:
            return True
        return marketplace_id in self.marketplace_ids


async def resolve_reporting_scope(
    user: User, session: AsyncSession
) -> ReportingScope:
    """Резолвить scope доступа пользователя в отчёты.

    Args:
        user: текущий пользователь
        session: асинхронная сессия БД

    Returns:
        ReportingScope с перечнем доступных ресурсов
    """
    # Селлер видит только свой seller_id (если он его имеет)
    if user.seller_id:
        return ReportingScope(
            tenant_id=user.tenant_id,
            seller_ids={user.seller_id},
        )

    # Остальные (ФФ-сотрудники, админы) видят весь tenant
    return ReportingScope(
        tenant_id=user.tenant_id,
        seller_ids=None,
    )
