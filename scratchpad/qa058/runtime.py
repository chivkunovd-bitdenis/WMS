"""Isolated WMS-058 QA; only loopback network, no marketplace accounts."""

import json
import os
import sys
from pathlib import Path

QA = Path(__file__).resolve().parent
ROOT = QA.parents[1]
DB_NAME = "wms058_browser_5c371f39"
os.environ["DATABASE_URL"] = (
    f"postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/{DB_NAME}"
)
os.environ["JWT_SECRET_KEY"] = "synthetic-wms058-local-only-secret-32-chars"
os.environ["WMS_DATA_DIR"] = str(QA / "data")
os.environ["WMS_AUTO_CREATE_SCHEMA"] = "0"
os.environ["WMS_BOOTSTRAP_ADMIN"] = "0"
sys.path.insert(0, str(ROOT / "backend"))


def boundary(event, args):
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and address[0] not in (
            "127.0.0.1",
            "::1",
            "localhost",
        ):
            with (QA / "blocked-network.jsonl").open("a") as stream:
                stream.write(json.dumps({"address": list(address)}) + "\n")
            raise RuntimeError("Synthetic QA forbids non-loopback connections")


sys.addaudithook(boundary)
from app.main import create_app

app = create_app()


@app.middleware("http")
async def capture(request, call_next):
    if request.url.path.startswith("/operations/"):
        with (QA / "requests.jsonl").open("a") as stream:
            stream.write(
                json.dumps({"method": request.method, "path": request.url.path}) + "\n"
            )
    return await call_next(request)
