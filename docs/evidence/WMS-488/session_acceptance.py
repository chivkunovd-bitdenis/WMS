"""Synthetic Chrome acceptance of WMS-488 session boundaries.

Run against a local production build only. Every /api request is intercepted;
fixture tokens are literal labels, not credentials. No production data is used.
Usage: AUDIT_UI_BASE_URL=http://127.0.0.1:5528 python3 session_acceptance.py
"""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

BASE = os.environ.get("AUDIT_UI_BASE_URL", "http://127.0.0.1:5528")
OUT = Path(__file__).parent / "local" / "acceptance"
OUT.mkdir(parents=True, exist_ok=True)
A, B, FF = "fixture-a", "fixture-b", "fixture-ff"
COUNTS = {A: 38, B: 19}


def profile(actor):
    seller = actor != FF
    name = {A: "Seller Alpha", B: "Seller Bravo", FF: "FF Operator"}[actor]
    return {"id": actor, "email": actor + "@example.test", "full_name": name,
        "display_name": name, "organization_name": "Test Fulfillment",
        "organization_slug": "test-fulfillment", "role": "fulfillment_seller" if seller else "fulfillment_admin",
        "seller_id": actor if seller else None, "seller_name": name if seller else None,
        "home_seller_id": actor if seller else None, "active_seller_id": actor if seller else None,
        "home_seller_name": name if seller else None, "active_seller_name": name if seller else None,
        "can_manage_seller_shops": False, "switchable_shops": [], "delegatable_shops": [],
        "permissions": {p: True for p in ["settings", "mp_shipments", "reception", "cells", "inventory", "packaging", "shift_lead"]} if not seller else None,
        "seller_permissions": {p: True for p in ["documents", "products", "honest_sign", "settings", "staff"]} if seller else None,
        "address_storage_enabled": True, "separate_marking_print_enabled": False, "fbs_shipment_cutoff_time": None}


def catalog(actor):
    prefix = "Alpha" if actor == A else "Bravo"
    return [{"id": actor + str(i), "seller_id": actor, "seller_name": profile(actor)["seller_name"],
        "sku_code": f"{prefix}-SKU-{i:03d}", "name": f"{prefix} Product {i}", "wb_vendor_code": f"{prefix}-article-{i}",
        "wb_nm_id": (100000 if actor == A else 200000) + i, "ozon_sku": None, "ozon_offer_id": None,
        "marketplaces": ["wb"], "wb_subject_name": prefix + " category", "wb_primary_image_url": None,
        "wb_barcodes": [f"{prefix}-barcode-{i}"], "wb_primary_barcode": f"{prefix}-barcode-{i}",
        "wb_size": None, "wb_color": None, "wb_brand": None, "wb_composition": None,
        "packaging_instructions": None, "requires_honest_sign": False, "has_packaging_instructions": False}
        for i in range(1, COUNTS[actor] + 1)]


class Harness:
    def __init__(self, browser):
        self.browser = browser
        self.gates = {}
        self.seen = {}
        self.override = {}
        self.calls = []
        self.errors = []

    async def start(self, actor=A):
        self.context = await self.browser.new_context(viewport={"width": 1500, "height": 1100})
        await self.context.route("**/api/**", self.route)
        await self.context.route("**/audit-driver.html", lambda r: r.fulfill(content_type="text/html", body="<html>Fixture controller</html>"))
        self.driver = await self.context.new_page()
        await self.driver.goto(BASE + "/audit-driver.html")
        await self.driver.evaluate("v => localStorage.setItem('wms_token_seller',v)", actor)
        self.page = await self.context.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        return self

    def hold(self, actor, path, status=None):
        key = actor, path
        self.gates[key] = asyncio.Event()
        self.seen[key] = asyncio.Event()
        if status:
            self.override[key] = status

    async def reached(self, actor, path):
        await asyncio.wait_for(self.seen[(actor, path)].wait(), 10)

    def release(self, actor, path):
        self.gates[(actor, path)].set()

    async def route(self, route):
        parsed = urlparse(route.request.url)
        path = parsed.path.removeprefix("/api")
        actor = route.request.headers.get("authorization", "").removeprefix("Bearer ")
        key = actor, path
        self.calls.append({"actor": actor, "path": path, "query": parsed.query})
        if key in self.gates:
            self.seen[key].set()
            await self.gates[key].wait()
        status = self.override.get(key, 200)
        if route.request.method != "GET":
            status, body = 405, {"detail": "synthetic_read_only"}
        elif status != 200:
            body = {"detail": "fixture_expired_session"}
        elif path == "/auth/me":
            body = profile(actor)
        elif path == "/subscription":
            body = {"enabled": True, "paid_until": "2027-01-01", "days_left": 120, "blocked": False, "price_rub": 0, "payment_available": False}
        elif path == "/products/wb-catalog":
            body = catalog(actor)
        elif path == "/products/ff-catalog-page":
            query = parse_qs(parsed.query)
            selected = query.get("seller_id", [None])[0]
            rows = sum([catalog(a) for a in [A, B] if selected is None or selected == a], [])
            limit, offset = int(query.get("limit", [50])[0]), int(query.get("offset", [0])[0])
            body = {"items": rows[offset:offset + limit], "total": len(rows), "scope_total": len(rows), "limit": limit, "offset": offset, "categories": list({r["wb_subject_name"] for r in rows})}
        elif path == "/sellers":
            body = [{"id": a, "name": profile(a)["seller_name"]} for a in [A, B]]
        elif path == "/operations/notifications":
            body = {"items": [], "unread_count": 0}
        else:
            body = []
        await route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    async def navigate(self):
        await self.page.goto(BASE + "/seller/products", wait_until="domcontentloaded")

    async def switch(self, actor):
        await self.driver.evaluate("v => v === null ? localStorage.removeItem('wms_token_seller') : localStorage.setItem('wms_token_seller',v)", actor)

    async def count(self, actor):
        await self.page.wait_for_function("n => document.querySelector('[data-testid=seller-catalog-filter-count]')?.textContent.includes('из ' + n)", arg=COUNTS[actor])
        body = await self.page.inner_text("body")
        assert profile(actor)["display_name"] in body, body[:500]
        other = B if actor == A else A
        assert profile(other)["display_name"] not in body
        assert ("Bravo Product" if other == B else "Alpha Product") not in body

    async def no_catalog(self):
        await self.page.wait_for_function("!document.querySelector('[data-testid=seller-catalog-filter-count]')")
        body = await self.page.inner_text("body")
        assert "Alpha Product" not in body and "Bravo Product" not in body
        assert "Seller Alpha" not in body and "Seller Bravo" not in body

    async def close(self):
        for gate in self.gates.values():
            gate.set()
        assert not self.errors, self.errors
        await self.context.close()


async def main():
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        h = await Harness(browser).start()
        await h.navigate()
        await h.count(A)
        print("initial A visible", flush=True)
        # Search all four foreign identifiers in the actual table.
        search = h.page.get_by_test_id("seller-catalog-search")
        for needle in ["Bravo-SKU-001", "Bravo-article-1", "Bravo-barcode-1", "Bravo Product 1"]:
            await search.fill(needle)
            await h.page.wait_for_timeout(350)
            print(needle, repr(await h.page.get_by_test_id("seller-catalog-filter-count").inner_text()), flush=True)
            await h.page.wait_for_function("/Найдено:\\s*0/.test(document.querySelector('[data-testid=seller-catalog-filter-count]')?.textContent || '')")
        await search.fill("")
        await h.count(A)
        # Categories and printing are derived only from the authorized rows.
        await h.page.get_by_test_id("seller-catalog-category-filter").click()
        assert await h.page.get_by_role("option", name="Alpha category", exact=True).count() == 1
        assert await h.page.get_by_role("option", name="Bravo category", exact=True).count() == 0
        await h.page.get_by_role("option", name="Alpha category", exact=True).click()
        await h.page.get_by_test_id("seller-packaging-edit-" + A + "1").click()
        await h.page.get_by_test_id("seller-packaging-print").click()
        print_html = await h.page.locator("iframe[aria-hidden=true]").get_attribute("srcdoc")
        assert "Alpha Product 1" in print_html and "Bravo" not in print_html
        # Leave details open while switching; the old details must disappear too.
        h.hold(B, "/auth/me")
        await h.switch(B)
        await h.reached(B, "/auth/me")
        await h.no_catalog()  # Held B profile proves removal does not await server.
        h.release(B, "/auth/me")
        await h.count(B)
        await h.page.reload()
        await h.count(B)
        await h.page.screenshot(path=str(OUT / "seller-bravo-after-switch.png"), full_page=True)
        await h.switch(None)
        await h.no_catalog()
        await h.page.locator("input[type=password]").wait_for()
        await h.page.screenshot(path=str(OUT / "seller-logout.png"), full_page=True)
        print("scenario passed", len(results) + 1, flush=True)
        results.append({"scenario": "two_tabs_search_categories_print_details_switch_clear_reload_logout", "verdict": "PASS"})
        await h.close()
        # Older profile success and 401 must not restore A or log out B.
        for status in [200, 401]:
            h = await Harness(browser).start()
            h.hold(A, "/auth/me", status)
            await h.navigate()
            await h.reached(A, "/auth/me")
            await h.switch(B)
            await h.count(B)
            h.release(A, "/auth/me")
            await h.page.wait_for_timeout(400)
            await h.count(B)
            assert await h.driver.evaluate("localStorage.getItem('wms_token_seller')") == B
            print(f"late profile {status} passed", flush=True)
            results.append({"scenario": f"late_profile_{status}_after_switch", "verdict": "PASS"})
            await h.close()
        # Both late catalogue and profile replies, after switch and after logout.
        for path in ["/products/wb-catalog", "/auth/me"]:
            for next_actor in [B, None]:
                h = await Harness(browser).start()
                h.hold(A, path)
                await h.navigate()
                await h.reached(A, path)
                await h.switch(next_actor)
                if next_actor:
                    await h.count(next_actor)
                else:
                    await h.no_catalog()
                h.release(A, path)
                await h.page.wait_for_timeout(400)
                if next_actor:
                    await h.count(next_actor)
                else:
                    await h.no_catalog()
                print(f"late {path} to {next_actor} passed", flush=True)
                results.append({"scenario": f"late_{path}_after_{'switch' if next_actor else 'logout'}", "verdict": "PASS"})
                await h.close()
        # Real FF catalogue navigation and filters while seller session changes.
        h = await Harness(browser).start()
        await h.navigate()
        await h.count(A)
        await h.driver.evaluate("localStorage.setItem('wms_token_ff','fixture-ff')")
        ff = await h.context.new_page()
        ff.on("pageerror", lambda e: h.errors.append(str(e)))
        await ff.goto(BASE + "/app/ff/products", wait_until="domcontentloaded")
        await ff.get_by_test_id("ff-catalog-filter-count").wait_for()
        await ff.wait_for_function("document.querySelector('[data-testid=ff-catalog-filter-count]')?.textContent.includes('57')")
        for actor in [A, B]:
            await ff.get_by_test_id("ff-catalog-seller-filter").click()
            await ff.get_by_role("option", name=profile(actor)["seller_name"], exact=True).click()
            await ff.wait_for_function("n => document.querySelector('[data-testid=ff-catalog-filter-count]')?.textContent.includes('из ' + n)", arg=COUNTS[actor])
            rows = await ff.get_by_test_id("ff-products-table").inner_text()
            assert ("Bravo Product" if actor == A else "Alpha Product") not in rows
        await h.switch(B)
        await h.count(B)
        await h.switch(None)
        await h.no_catalog()
        assert "FF Operator" in await ff.inner_text("body")
        assert await ff.get_by_test_id("ff-product-row").count() > 0
        assert await h.driver.evaluate("localStorage.getItem('wms_token_ff')") == FF
        await ff.screenshot(path=str(OUT / "ff-after-seller-logout.png"), full_page=True)
        # Changing FF storage cannot clear the seller portal.
        await h.switch(A)
        await h.count(A)
        await h.driver.evaluate("localStorage.removeItem('wms_token_ff')")
        await h.page.wait_for_timeout(400)
        await h.count(A)
        results.append({"scenario": "ff_catalog_all_and_each_seller_cross_portal_sessions", "verdict": "PASS"})
        await h.close()
        await browser.close()
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
