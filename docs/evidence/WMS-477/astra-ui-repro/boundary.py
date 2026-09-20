"""C23: real Chrome, real FBS ErrorBoundary, artificial errors and external DOM edits."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
PORT=int(os.environ.get('WMS_QA_PORT','5577'))
FIXTURE=REPO/'frontend/tmp/wms477-astra-repro'
OUT=HERE/'local-boundary'
FIXTURE.mkdir(parents=True,exist_ok=True);OUT.mkdir(exist_ok=True)
shutil.copyfile(HERE/'main.tsx',FIXTURE/'main.tsx')
(FIXTURE/'index.html').write_text('<!doctype html><html lang="ru"><meta charset="UTF-8"><div id="root"></div><script type="module" src="/tmp/wms477-astra-repro/main.tsx"></script></html>')
logfile=(OUT/'vite.log').open('w')
server=subprocess.Popen(['./node_modules/.bin/vite','--host','127.0.0.1','--port',str(PORT),'--strictPort'],cwd=REPO/'frontend',stdout=logfile,stderr=subprocess.STDOUT)
result={'product_sha':'69b3f2ccc119e7a9ec67eeb629d4e96e69a6b414','scenarios':{}}
try:
    for _ in range(100):
        if server.poll() is not None: raise RuntimeError((OUT/'vite.log').read_text())
        try: urllib.request.urlopen(f'http://127.0.0.1:{PORT}/tmp/wms477-astra-repro/index.html');break
        except OSError:time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        def fresh():
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.clock.install()
            # Synthetic token only; report transport is the fixture's mock fetch.
            page.add_init_script("localStorage.setItem('wms_token_ff','qa-synthetic-only')")
            page.goto(f'http://127.0.0.1:{PORT}/tmp/wms477-astra-repro/index.html',wait_until='networkidle')
            page.locator('[data-order-id="A1"]').wait_for()
            return page
        def scan(page):return page.locator('[data-testid="fbs-kiz-scan-input"] input')
        def state(page):
            return {'scan':scan(page).input_value() if scan(page).count() else None,
                    'selected':page.locator('[data-order-id="A1"] input[type="checkbox"]:checked').count(),
                    'active':page.locator('[data-testid="fbs-kiz-row-active"]').count(),
                    'focused':scan(page).evaluate('(e)=>document.activeElement===e') if scan(page).count() else False,
                    'fallback':page.locator('[data-testid="client-error-fallback"]').count(),
                    'host_visible':page.locator('#requested-supply').is_visible(),
                    'rows':page.locator('[data-order-id]').all_inner_texts()}
        def enter_work(page):
            page.locator('[data-order-id="A1"] input[type="checkbox"]').check()
            scan(page).fill('901001234');scan(page).press('Enter')
            page.locator('[data-testid="fbs-kiz-row-active"]').wait_for()
            scan(page).fill('010460PARTIAL')
        def poll(page,verdict='accepted',added=False):
            page.clock.run_for(15000)
            page.wait_for_timeout(50)
            pending=page.evaluate('window.qa.pending()')
            assert pending,pending
            page.evaluate('(x)=>window.qa.resolve(x.id,"A",x.verdict,x.added)',{'id':pending[-1],'verdict':verdict,'added':added})
            page.wait_for_timeout(100)
        def check_poll_preserves(page):
            enter_work(page)
            before=state(page)
            poll(page)
            after=state(page)
            assert after['scan']==before['scan']=='010460PARTIAL'
            assert after['selected']==before['selected']==1
            assert after['active']==before['active']==1
            assert after['focused'] and after['fallback']==0
            return {'before':before,'after':after}
        def reports(page):return page.evaluate('window.qa.log.filter(x=>x.event==="client-error").map(x=>JSON.parse(x.body))')
        def save(page,name,data):
            result['scenarios'][name]=data
            page.screenshot(path=str(OUT/f'{name}.png'),full_page=True)
            print(name,json.dumps(data,ensure_ascii=False),flush=True)
            page.close()

        page=fresh()
        healthy=check_poll_preserves(page)
        before=state(page)
        page.evaluate('window.qa.inject(1)')
        page.wait_for_timeout(300)
        page.locator('[data-order-id="A1"]').wait_for()
        recovered=state(page)
        assert recovered['host_visible'] and recovered['fallback']==0
        client_reports=reports(page)
        assert any('artificial FBS child exception' in x['message'] and x['component']=='FfFbsSupplyWorkspace' for x in client_reports)
        post_poll=check_poll_preserves(page)
        save(page,'single_exception_recovery',{'healthy_poll':healthy,'before_error':before,'recovered':recovered,'reports':client_reports,'post_recovery_poll':post_poll})

        page=fresh()
        enter_work(page)
        before=state(page)
        page.evaluate('window.qa.inject(3)')
        page.clock.run_for(2000)
        page.locator('[data-testid="client-error-fallback"]').wait_for()
        fallback=page.locator('[data-testid="client-error-fallback"]').inner_text()
        assert 'Не удалось показать этот раздел' in fallback
        assert page.locator('#requested-supply').is_visible()
        assert 'Unexpected Application Error' not in page.locator('body').inner_text()
        captured=reports(page)
        page.screenshot(path=str(OUT/'persistent-fallback.png'),full_page=True)
        page.locator('[data-testid="client-error-fallback"] button').click()
        page.locator('[data-order-id="A1"]').wait_for()
        post_poll=check_poll_preserves(page)
        save(page,'persistent_exception_reload',{'before_error':before,'fallback':fallback,'host_survived':True,'reports':captured,'post_reload_poll':post_poll})

        # Delete an actual React-owned child, then ask React to remove that same
        # conditional size cell. No monkeypatch of DOM methods or product code.
        page=fresh()
        poll(page,added=True)
        page.locator('[data-order-id="A1"] [data-testid="fbs-packing-size"]').wait_for()
        enter_work(page)
        before=state(page)
        removed=page.locator('[data-order-id="A1"] [data-testid="fbs-packing-size"]').evaluate('(el)=>{const html=el.outerHTML;el.remove();return html}')
        poll(page,added=False)
        page.clock.run_for(2000)
        page.locator('[data-order-id="A1"]').wait_for()
        recovered=state(page)
        client_reports=reports(page)
        assert any('removeChild' in x['message'] for x in client_reports),client_reports
        assert recovered['host_visible'] and recovered['fallback']==0
        post_poll=check_poll_preserves(page)
        save(page,'external_dom_removal',{'removed_dom':removed,'before_error':before,'recovered':recovered,'reports':client_reports,'post_recovery_poll':post_poll})
        browser.close()
finally:
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill()
    logfile.close()
