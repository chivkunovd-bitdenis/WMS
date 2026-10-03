from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SupportAgentRequestOut(BaseModel):
    """What the dispatcher agent may read about one developer request (WMS-641 R4)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: Literal["bug", "improvement"]
    title: str
    description: str | None
    screen: str | None
    problem: str | None
    proposal: str | None
    page_url: str | None
    client_name: str
    # WMS-641 R43: серверная привязка заявки к селлеру (у сотрудника фулфилмента seller_id пуст)
    tenant_id: uuid.UUID
    seller_id: uuid.UUID | None
    status: Literal["review", "queued", "in_progress", "completed"]
    created_at: datetime
    updated_at: datetime
    delivery_state: str
    trello_card_id: str | None
