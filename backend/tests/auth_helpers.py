"""Помощники входа для тестов.

Приглашение и сброс пароля идут ссылкой из письма (WMS-378). Тест не читает
почту, поэтому берёт тот же токен, что ушёл бы в письме, и открывает «ссылку».
"""

from __future__ import annotations

from httpx import AsyncClient, Response
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.services.auth_link_tokens import create_auth_link_token


async def password_link_token(email: str, *, purpose: str = "invite") -> str:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == email.strip().lower())
        )
        user = result.scalar_one()
        return create_auth_link_token(user, purpose=purpose)  # type: ignore[arg-type]


async def set_password_via_link(
    client: AsyncClient, email: str, password: str
) -> Response:
    token = await password_link_token(email)
    return await client.post(
        "/auth/set-password",
        json={"token": token, "password": password},
    )
