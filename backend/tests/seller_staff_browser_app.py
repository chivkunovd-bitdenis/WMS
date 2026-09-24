"""Local-only browser fixture: run with an isolated SQLite DB and no SMTP.

uvicorn tests.seller_staff_browser_app:app --host 127.0.0.1 --port 18463
Never deploy this test app: its outbox intentionally exposes test invitation links.
"""

from app.main import create_app
from app.services import auth_service

messages: list[dict[str, str]] = []


async def capture_mail(*, to: str, subject: str, body: str) -> bool:
    messages.append({"to": to, "subject": subject, "body": body})
    return True


auth_service.send_email = capture_mail
app = create_app()


@app.get("/_test/mail")
async def outbox() -> list[dict[str, str]]:
    return messages
