"""Chrome regression: old auth reply must preserve B before storage delivery.

All data are synthetic and /api requests are intercepted by session_acceptance.
A capture listener delays only the application delivery of real storage events,
so response-vs-storage task ordering can be tested deterministically.
Default asserts the desired fixed result. --expect-vulnerable records baseline.
"""
import argparse
import asyncio
import importlib.util
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

spec = importlib.util.spec_from_file_location("acceptance", Path(__file__).with_name("session_acceptance.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
original_profile = fixture.profile


async def scenario(browser, status, wrong_portal=False):
    started = time.monotonic()
    timeline = []

    def mark(event, **details):
        timeline.append({"event": event, "elapsed_ms": round((time.monotonic() - started) * 1000, 1), **details})

    harness = await fixture.Harness(browser).start()
    harness.hold(fixture.A, "/auth/me", status)
    await harness.page.add_init_script('''
      window.heldStorageEvents=[];
      window.storageBlocked=true;
      window.addEventListener('storage', event => {
        if (window.storageBlocked) {
          window.heldStorageEvents.push({key:event.key,oldValue:event.oldValue,newValue:event.newValue,url:event.url});
          event.stopImmediatePropagation();
        }
      },true);
      window.releaseStorageEvents=()=>{
        window.storageBlocked=false;
        for(const e of window.heldStorageEvents) window.dispatchEvent(new StorageEvent('storage',{...e,storageArea:localStorage}));
        window.heldStorageEvents=[];
      };
    ''')
    await harness.navigate()
    await harness.reached(fixture.A, "/auth/me")
    mark("A_auth_request_held")
    await harness.switch(fixture.B)
    mark("B_written_by_other_tab")
    await harness.page.wait_for_function("window.heldStorageEvents.length>0")
    mark("storage_event_held_before_useAuth")
    before = await harness.driver.evaluate("localStorage.getItem('wms_token_seller')")
    if wrong_portal:
        def profile(actor):
            result = original_profile(actor)
            if actor == fixture.A:
                result["role"] = "fulfillment_admin"
            return result
        fixture.profile = profile
    harness.release(fixture.A, "/auth/me")
    mark("old_A_response_released", status=status, wrong_portal=wrong_portal)
    await harness.page.wait_for_timeout(350)
    after = await harness.driver.evaluate("localStorage.getItem('wms_token_seller')")
    mark("after_old_response", stored=after)
    body = await harness.page.inner_text("body")
    await harness.page.evaluate("window.releaseStorageEvents()")
    mark("storage_events_delivered")
    await harness.page.wait_for_timeout(350)
    final = await harness.driver.evaluate("localStorage.getItem('wms_token_seller')")
    counter = harness.page.get_by_test_id("seller-catalog-filter-count")
    count = await counter.inner_text() if await counter.count() else None
    mark("final_state", stored=final, catalog_count=count)
    result = {
        "scenario": "late_wrong_portal_profile_before_storage" if wrong_portal else "late_401_before_storage",
        "before_old_response": before,
        "after_old_response": after,
        "after_storage_delivery": final,
        "catalog_after_storage": count,
        "shows_profile_mismatch": "Этот адрес только для селлера" in body,
        "expected_new_session_preserved": final == fixture.B and count == "Найдено: 19 из 19",
        "page_errors": harness.errors,
        "timeline": timeline,
    }
    fixture.profile = original_profile
    await harness.close()
    return result


async def main(expect_vulnerable):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome")
        results = [await scenario(browser, 401), await scenario(browser, 200, True)]
        await browser.close()
    report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "results": results}
    path = Path(__file__).parent / "local" / "storage-order-race.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if expect_vulnerable:
        assert all(row["before_old_response"] == fixture.B and row["after_storage_delivery"] is None for row in results)
    else:
        assert all(row["expected_new_session_preserved"] for row in results), "Old auth reply erased/replaced the new session"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-vulnerable", action="store_true")
    asyncio.run(main(parser.parse_args().expect_vulnerable))
