"""CLI: load operator seed orders for three emulator sellers (idempotent upsert)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wb_emulator.db import get_session_factory, init_db
from wb_emulator.services.orders_store import (
    count_seeded_orders,
    seed_orders_from_templates,
)
from wb_emulator.settings import get_settings

_SEED_DIR = Path(__file__).resolve().parent
_DEFAULT_TEMPLATES = _SEED_DIR / "order_templates.json"
_DEFAULT_TOKENS = _SEED_DIR / "tokens.json"


def load_token_map(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return {str(token): str(seller_key) for token, seller_key in raw.items()}


def run_seed(*, db_path: Path | None = None, seller_keys: list[str] | None = None) -> dict[str, int]:
    if db_path is not None:
        import os

        os.environ["WB_EMULATOR_DB_PATH"] = str(db_path)
        get_settings.cache_clear()

    init_db()
    session = get_session_factory()()
    try:
        counts = seed_orders_from_templates(session, seller_keys=seller_keys)
        total = count_seeded_orders(session)
        print(f"Seeded orders by seller: {counts}; total rows={total}")
        return counts
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load WB emulator operator seed orders")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite path (WB_EMULATOR_DB_PATH)")
    parser.add_argument(
        "--templates",
        type=Path,
        default=_DEFAULT_TEMPLATES,
        help="order_templates.json path (informational; uses package default)",
    )
    parser.add_argument(
        "--tokens",
        type=Path,
        default=_DEFAULT_TOKENS,
        help="tokens.json path (informational; configure WB_EMULATOR_TOKEN_MAP_FILE separately)",
    )
    parser.add_argument(
        "--seller",
        action="append",
        dest="sellers",
        help="Limit to seller_key (repeatable); default all sellers in templates",
    )
    args = parser.parse_args()
    _ = args.templates, args.tokens
    run_seed(db_path=args.db_path, seller_keys=args.sellers)


if __name__ == "__main__":
    main()
