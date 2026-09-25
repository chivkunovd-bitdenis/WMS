"""Check cross-tab seller session changes in the deployed bundle, no live API calls."""
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright


async def main():
    snapshots = json.loads(Path(sys.argv[1]).read_text())
    first, second = snapshots[0], snapshots[2]
    mapping = {"replay-" + item["user_id"]: item for item in snapshots}
    first_marker = "replay-" + first["user_id"]
    second_marker = "replay-" + second["user_id"]
    evidence = Path(__file__).parent / "local"
    evidence.mkdir(exist_ok=True)
    first_count = len(first["responses"]["/products/wb-catalog"]["body"])
    second_count = len(second["responses"]["/products/wb-catalog"]["body"])
    calls = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        context = await browser.new_context(viewport={"width": 1440, "height": 1100})
        await context.add_init_script("if(!localStorage.getItem('wms_token_seller')) localStorage.setItem('wms_token_seller', " + json.dumps(first_marker) + "); window.auditStorageEvents=[]; window.addEventListener('storage', e => window.auditStorageEvents.push({key:e.key,changed:e.newValue !== e.oldValue}));")
        async def replay(route):
            path = urlparse(route.request.url).path.removeprefix("/api")
            marker = route.request.headers.get("authorization", "").removeprefix("Bearer ")
            snapshot = mapping.get(marker)
            response = snapshot["responses"].get(path) if snapshot else None
            calls.append({"path":path,"actor":snapshot["user_id"] if snapshot else None})
            if route.request.method != "GET" or response is None:
                await route.fulfill(status=405,content_type="application/json",body='{"detail":"readonly_replay_not_captured"}')
            else:
                await route.fulfill(status=response["status"],content_type="application/json",body=json.dumps(response["body"]))
        await context.route("**/api/**",replay)
        tab1 = await context.new_page()
        url = os.environ.get("AUDIT_UI_BASE_URL", "https://wms.sellerfocus.pro") + "/seller/products"
        await tab1.goto(url,wait_until="domcontentloaded")
        await tab1.get_by_test_id("seller-catalog-filter-count").wait_for()
        await tab1.wait_for_function("n => document.querySelector('[data-testid=seller-catalog-filter-count]').textContent.includes('из ' + n)", arg=first_count)
        before = await tab1.get_by_test_id("seller-catalog-filter-count").inner_text()
        tab2 = await context.new_page()
        await tab2.goto(url,wait_until="domcontentloaded")
        await tab2.evaluate("value => localStorage.setItem('wms_token_seller', value)", second_marker)
        await tab2.reload(wait_until="domcontentloaded")
        await tab2.get_by_test_id("seller-catalog-filter-count").wait_for()
        await tab2.wait_for_function("n => document.querySelector('[data-testid=seller-catalog-filter-count]').textContent.includes('из ' + n)", arg=second_count)
        await tab1.wait_for_timeout(600)
        after_switch = await tab1.get_by_test_id("seller-catalog-filter-count").inner_text()
        tab2_after = await tab2.get_by_test_id("seller-catalog-filter-count").inner_text()
        await tab2.evaluate("localStorage.removeItem('wms_token_seller')")
        await tab1.wait_for_timeout(600)
        remaining_catalog = tab1.get_by_test_id("seller-catalog-filter-count")
        after_logout = await remaining_catalog.inner_text() if await remaining_catalog.count() else None
        await tab1.screenshot(path=str(evidence / "ui-cross-tab-stale-session.png"),full_page=True)
        result = {"before":before,"tab1_after_other_tab_login":after_switch,"tab2_after_login":tab2_after,"tab1_after_other_tab_logout":after_logout,"storage_events":await tab1.evaluate("window.auditStorageEvents"),"calls":calls}
        (evidence / "ui-session-replay-results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        await browser.close()


asyncio.run(main())
