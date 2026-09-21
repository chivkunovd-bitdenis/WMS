"""Render the deployed seller bundle with exact read-only per-user responses.

All /api calls are intercepted. The browser never logs in or mutates production.
This verifies UI rendering with production data, not production authentication.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright


async def main():
    snapshots = json.loads(Path(sys.argv[1]).read_text())
    evidence = Path(__file__).parent / "local"
    evidence.mkdir(exist_ok=True)
    victim_catalog = max(snapshots, key=lambda item: len(item["responses"]["/products/wb-catalog"]["body"]))["responses"]["/products/wb-catalog"]["body"]
    victim_sku = victim_catalog[0]["sku_code"]
    results = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome")
        for snap in snapshots:
            context = await browser.new_context(viewport={"width": 1440, "height": 1100})
            await context.add_init_script("localStorage.setItem('wms_token_seller', 'readonly-ui-replay-placeholder')")
            requests = []

            async def replay(route):
                path = urlparse(route.request.url).path.removeprefix("/api")
                response = snap["responses"].get(path)
                requests.append({"method": route.request.method, "path": path, "captured": response is not None})
                if route.request.method != "GET" or response is None:
                    await route.fulfill(status=405, content_type="application/json", body='{"detail":"readonly_replay_not_captured"}')
                    return
                await route.fulfill(status=response["status"], content_type="application/json", body=json.dumps(response["body"]))

            await context.route("**/api/**", replay)
            page = await context.new_page()
            await page.goto(os.environ.get("AUDIT_UI_BASE_URL", "https://wms.sellerfocus.pro") + "/seller/products", wait_until="domcontentloaded")
            expected = len(snap["responses"]["/products/wb-catalog"]["body"])
            count = page.get_by_test_id("seller-catalog-filter-count")
            await count.wait_for()
            await page.wait_for_function("n => document.querySelector('[data-testid=seller-catalog-filter-count]')?.textContent.includes('из ' + n)", arg=expected)
            visible_rows = await page.get_by_test_id("seller-product-row").count()
            initial_count = await count.inner_text()
            await page.screenshot(path=str(evidence / f"ui-{snap['user_id']}.png"), full_page=True)
            await page.get_by_test_id("seller-catalog-search").fill(victim_sku)
            await page.wait_for_timeout(150)
            searched_count = await count.inner_text()
            profile = snap["responses"]["/auth/me"]["body"]
            results.append({"user_id":snap["user_id"],"home_seller_id":profile["home_seller_id"],"active_seller_id":profile["active_seller_id"],"expected_catalog":expected,"visible_rows":visible_rows,"initial_count":initial_count,"foreign_sku_search":searched_count,"api_requests":requests,"scripts":await page.locator('script[src]').evaluate_all('(els) => els.map(el => el.src)')})
            await context.close()
        await browser.close()
    (evidence / "ui-replay-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))


asyncio.run(main())
