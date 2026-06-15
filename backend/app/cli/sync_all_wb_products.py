"""CLI: full WB product sync for all sellers (post-deploy)."""

from __future__ import annotations

import asyncio
import json
import logging

from app.services.wildberries_product_sync_service import run_wb_products_sync_all_sellers

logging.basicConfig(level=logging.INFO)


def main() -> None:
    summary = asyncio.run(run_wb_products_sync_all_sellers())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
