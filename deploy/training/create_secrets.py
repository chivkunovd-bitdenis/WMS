#!/usr/bin/env python3
"""Run on the destination Linux host only, after explicit owner authorization."""
import argparse
import base64
import json
import os
import secrets
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
parser.add_argument("--public-url", required=True)
args = parser.parse_args()
os.umask(0o077)
root = args.directory.resolve()
private = root / "private"
private.mkdir(mode=0o700, exist_ok=True)
env = root / ".env"
if env.exists():
    raise SystemExit("Existing training secrets preserved; refusing to replace .env")
token_map = {secrets.token_urlsafe(32): name for name in ("seller_a", "seller_b", "seller_c")}
(private / "emulator-tokens.json").write_text(json.dumps(token_map))
values = {
    "TRAINING_DB_PASSWORD": secrets.token_hex(24),
    "TRAINING_JWT_SECRET": secrets.token_urlsafe(48),
    "TRAINING_FERNET_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
    "TRAINING_EMULATOR_ADMIN_TOKEN": secrets.token_urlsafe(32),
    "TRAINING_PUBLIC_URL": args.public_url,
    "TRAINING_BIND_ADDRESS": "0.0.0.0",
    "TRAINING_HTTP_PORT": "8088",
}
with env.open("x") as f:
    f.write("".join(f"{k}={v}\n" for k, v in values.items()))
(private / "training-login.json").write_text(json.dumps({
    "email": "training@example.com", "password": secrets.token_urlsafe(18),
    "tenant_id": "9c31f3f4-ce62-4c1f-891a-295b278f1e69",
}))
print("Training secrets created on the destination; values not printed.")
