"""C17: Chrome check that a new scan and WB action work after FBS recovery.

Only synthetic token/data; real component and ErrorBoundary, mocked network.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

here = Path(__file__).resolve().parent
repo = here.parents[3]
source = here / 'main.tsx'
output = here / 'local'
output.mkdir(exist_ok=True)
fixture = repo / 'frontend/tmp/wms477-astra-repro'
fixture.mkdir(parents=True, exist_ok=True)
shutil.copyfile(source, fixture / 'main.tsx')
(fixture / 'index.html').write_text('<!doctype html><html lang="ru"><meta charset="UTF-8"><div id="root"></div><script type="module" src="/tmp/wms477-astra-repro/main.tsx"></script></html>')
port = int(os.environ.get('WMS_QA_PORT', '5582'))
log = (output / 'after_recovery_vite.log').open('w')
server = subprocess.Popen(['./node_modules/.bin/vite','--host','127.0.0.1','--port',str(port),'--strictPort'], cwd=repo/'frontend', stdout=log, stderr=subprocess.STDOUT)
results = []
try:
    for _ in range(100):
        if server.poll() is not None: raise RuntimeError('Vite exited')
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/tmp/wms477-astra-repro/index.html')
            break
        except OSError: time.sleep(.1)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        for mode in ('auto_recovery','fallback_reload'):
            page = browser.new_page(viewport={'width':1440,'height':1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.add_init_script("localStorage.setItem('wms_token_ff','qa-synthetic-only')")
            page.goto(f'http://127.0.0.1:{port}/tmp/wms477-astra-repro/index.html',wait_until='networkidle')
            page.locator('[data-order-id="A1"]').wait_for()
            page.evaluate('window.qa.inject(' + ('1' if mode == 'auto_recovery' else '3') + ')')
            if mode == 'fallback_reload':
                page.locator('[data-testid="client-error-fallback"] button').wait_for()
                page.locator('[data-testid="client-error-fallback"] button').click()
            page.locator('[data-order-id="A1"]').wait_for()
            scan = page.locator('[data-testid="fbs-kiz-scan-input"] input')
            scan.fill('901001234')
            scan.press('Enter')
            page.locator('[data-testid="fbs-kiz-row-active"]').wait_for(timeout=5000)
            page.get_by_role('button', name='Проверить в WB').click()
            page.wait_for_function("window.qa.pending().length > 0")
            pending = page.evaluate('window.qa.pending()')
            page.evaluate('(id)=>window.qa.resolve(id,"A","accepted",false)', pending[-1])
            page.get_by_text('ЧЗ принят WB').first.wait_for(timeout=5000)
            result = {'mode':mode,'scan_active':page.locator('[data-testid="fbs-kiz-row-active"]').count()==1,'button_request_count':len([x for x in page.evaluate('window.qa.log') if x.get('path')=='markings/sync' and x.get('event')=='request']),'accepted_visible':page.get_by_text('ЧЗ принят WB').count()>0,'page_errors':errors}
            results.append(result)
            page.screenshot(path=str(output/f'after_recovery_{mode}.png'))
            page.close()
        browser.close()
finally:
    server.terminate()
    try: server.wait(timeout=10)
    except subprocess.TimeoutExpired: server.kill()
    log.close()
    (output/'after_recovery_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
assert all(x['scan_active'] and x['button_request_count']==1 and x['accepted_visible'] and not x['page_errors'] for x in results)
