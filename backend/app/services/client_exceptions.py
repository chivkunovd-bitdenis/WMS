"""Признаки, которые включены только для одного клиента (клиентские исключения).

Каждое исключение записано в реестре docs/KLIENTSKIE_ISKLYUCHENIYA.md: кому и что
меняется, какие места кода затронуты и как снять исключение. У каждого признака
свой набор UUID, поэтому снять один признак нельзя, задев другой (WMS-710 R7).
"""

from __future__ import annotations

import uuid

# WMS-710: лист подбора FBS печатает места в порядке вкладки «Подбор» ТОЛЬКО для
# «Империи ФФ». Остальные клиенты печатают лист как раньше. Исключение записано в
# docs/KLIENTSKIE_ISKLYUCHENIYA.md, там же условие его снятия.
FBS_PICK_LIST_TAB_ORDER_TENANTS = frozenset(
    {uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")}
)


def uses_fbs_pick_list_tab_order(tenant_id: uuid.UUID) -> bool:
    return tenant_id in FBS_PICK_LIST_TAB_ORDER_TENANTS
