"""C16: 10-minute Chrome soak of the actual FBS React component with mock API.

Use WMS_QA_PORT to avoid another local server. All data are synthetic.
"""

import os
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

repo = Path(__file__).resolve().parents[4]
source = repo / "docs/evidence/WMS-477/astra-ui-repro/main.tsx"
fixture = repo / "frontend/tmp/wms477-final-soak"
fixture.mkdir(parents=True, exist_ok=True)
code = source.read_text()
patches = (
    ("let latency = 0", "let latency = 0\nlet persistedAdded = false"),
    ("log.push({event: 'response', id, added: true, at: Date.now()})", "persistedAdded = true\n      log.push({event: 'response', id, added: true, at: Date.now()})"),
    ("callback(response(workspace(supply, verdict, added)))", "callback(response(workspace(supply, verdict, added || persistedAdded)))"),
)
for before, after in patches:
    assert code.count(before) == 1, before
    code = code.replace(before, after)
(fixture / "main.tsx").write_text(code)
(fixture / "index.html").write_text('<!doctype html><html lang="ru"><meta charset="UTF-8"><div id="root"></div><script type="module" src="/tmp/wms477-final-soak/main.tsx"></script></html>')
output_dir = Path(__file__).resolve().parent / "local"
output_dir.mkdir(exist_ok=True)
log_path = output_dir / "soak-vite.log"
port = int(os.environ.get("WMS_QA_PORT", "5599"))
url = f"http://127.0.0.1:{port}/tmp/wms477-final-soak/index.html"
log_file = log_path.open("w")
server = subprocess.Popen(["./node_modules/.bin/vite", "--host", "127.0.0.1", "--port", str(port), "--strictPort"], cwd=repo / "frontend", stdout=log_file, stderr=subprocess.STDOUT)
result = {
    "sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
    "duration_seconds": 0,
    "polls": 0,
    "added_order": False,
    "page_errors": [],
    "failed": None,
}
started = time.monotonic()
try:
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError(log_path.read_text())
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Vite did not start")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda exc: result["page_errors"].append(str(exc)))
        page.goto(url, wait_until="networkidle")
        page.locator('[data-order-id="A1"]').wait_for()
        page.evaluate("window.qa.setLatency(0)")
        scan = page.locator('[data-testid="fbs-kiz-scan-input"] input')
        scan.fill("UNFINISHED-QR-123")
        page.locator('[data-order-id="A1"] [data-testid="fbs-packing-select-order"] input').check()
        scan.focus()
        handled = set()
        verdicts = ["accepted", "rejected", "pending"]
        next_add_at = int(os.environ.get("WMS_QA_ADD_AT_POLL", "20"))
        deadline = started + float(os.environ.get("WMS_QA_DURATION_SECONDS", "610"))
        while time.monotonic() < deadline:
            pending = page.evaluate("window.qa.pending()")
            for request_id in pending:
                if request_id in handled:
                    continue
                handled.add(request_id)
                verdict = verdicts[result["polls"] % len(verdicts)]
                page.evaluate("(args) => window.qa.resolve(args.id, 'A', args.verdict, false)", {"id": request_id, "verdict": verdict})
                expected = {"accepted": "ЧЗ принят WB", "rejected": "WB не принял ЧЗ", "pending": "WB ещё не подтвердил ЧЗ"}[verdict]
                page.get_by_text(expected, exact=True).first.wait_for(timeout=5000)
                result["polls"] += 1
                assert page.get_by_role("tab", name="УПАКОВКА И МАРКИРОВКА").get_attribute("aria-selected") == "true"
                assert page.locator('[data-order-id="A1"] [data-testid="fbs-packing-select-order"] input').is_checked()
                scan = page.locator('[data-testid="fbs-kiz-scan-input"] input')
                assert scan.input_value() == "UNFINISHED-QR-123"
                assert scan.evaluate("(el) => document.activeElement === el")
                if result["added_order"]:
                    added = page.locator('[data-order-id="6"]')
                    assert added.count() == 1
                    text = added.inner_text()
                    assert "0006" in text
                    size = " ".join(added.locator('[data-testid="fbs-packing-size"]').inner_text().split())
                    assert size == "Размер L", size
                if result["polls"] == next_add_at:
                    page.get_by_role("tab", name="СОСТАВ ✓").click()
                    page.locator('[data-testid="fbs-05-workspace-add-orders"]').click()
                    page.locator('[data-testid="fbs-05-workspace-add-orders-table"] input[type=checkbox]').first.check()
                    page.locator('[data-testid="fbs-05-workspace-add-orders-submit"]').click()
                    page.get_by_role("tab", name="УПАКОВКА И МАРКИРОВКА").click()
                    page.locator('[data-order-id="6"]').wait_for()
                    page.locator('[data-testid="fbs-kiz-scan-input"] input').fill("UNFINISHED-QR-123")
                    page.locator('[data-order-id="A1"] [data-testid="fbs-packing-select-order"] input').check()
                    page.locator('[data-testid="fbs-kiz-scan-input"] input').focus()
                    result["added_order"] = True
                if result["polls"] % 5 == 0:
                    print(f"polls={result['polls']} elapsed={time.monotonic()-started:.1f}s added={result['added_order']}", flush=True)
            page.wait_for_timeout(500)
        assert result["polls"] >= int(os.environ.get("WMS_QA_MIN_POLLS", "38")), result["polls"]
        assert result["added_order"]
        assert not result["page_errors"], result["page_errors"]
        log = page.evaluate("window.qa.log")
        gets = [e for e in log if e.get("path") == "workspace" and e.get("event") == "request"]
        responses = [e for e in log if e.get("event") == "response" and e.get("id") in {g["id"] for g in gets}]
        assert len(gets) == len(responses), (len(gets), len(responses))
        result["get_requests"] = len(gets)
        result["get_responses"] = len(responses)
        browser.close()
except Exception as exc:
    result["failed"] = f"{type(exc).__name__}: {exc}"
    raise
finally:
    result["duration_seconds"] = round(time.monotonic() - started, 2)
    (output_dir / "soak-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
    log_file.close()
    print(json.dumps(result, ensure_ascii=False), flush=True)
