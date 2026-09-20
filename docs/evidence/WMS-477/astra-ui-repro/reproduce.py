"""Chrome reproduction of Astra UI races; no real API requests or product edits."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PORT = int(os.environ.get('WMS_QA_PORT', '5577'))
FIXTURE = REPO/'frontend/tmp/wms477-astra-repro'
OUT = HERE/'local'
FIXTURE.mkdir(parents=True,exist_ok=True)
OUT.mkdir(exist_ok=True)
shutil.copyfile(HERE/'main.tsx',FIXTURE/'main.tsx')
(FIXTURE/'index.html').write_text('<!doctype html><html lang="ru"><meta charset="UTF-8"><div id="root"></div><script type="module" src="/tmp/wms477-astra-repro/main.tsx"></script></html>')
logfile=(OUT/'vite.log').open('w')
server=subprocess.Popen(['./node_modules/.bin/vite','--host','127.0.0.1','--port',str(PORT),'--strictPort'],cwd=REPO/'frontend',stdout=logfile,stderr=subprocess.STDOUT)
results={'sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'scenarios':{},'page_errors':[]}
try:
    import urllib.request
    for _ in range(100):
        if server.poll() is not None: raise RuntimeError((OUT/'vite.log').read_text())
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/tmp/wms477-astra-repro/index.html');break
        except OSError:time.sleep(.1)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        def fresh():
            page=browser.new_page(viewport={'width':1440,'height':1000})
            # Installing the real Playwright browser clock executes the product's
            # unmodified setInterval callbacks; only wall-clock waiting is sped up.
            page.on('pageerror',lambda e: results['page_errors'].append(str(e)))
            page.clock.install()
            page.goto(f'http://127.0.0.1:{PORT}/tmp/wms477-astra-repro/index.html',wait_until='networkidle')
            page.locator('[data-order-id="A1"]').wait_for()
            return page
        def tick(page,ms):
            page.clock.run_for(ms)
            page.wait_for_timeout(30)
        def snapshot(page):
            return {'requested':page.locator('#requested-supply').inner_text(),
                    'rows':page.locator('[data-order-id]').all_inner_texts(),
                    'ids':page.locator('[data-order-id]').evaluate_all('(els)=>els.map(e=>e.dataset.orderId)'),
                    'sizes':page.locator('[data-testid="fbs-packing-size"]').all_inner_texts(),
                    'log':page.evaluate('window.qa.log')}
        def save(page,name,data):
            page.screenshot(path=str(OUT/f'{name}.png'),full_page=True)
            results['scenarios'][name]=data
            print(name,json.dumps(data,ensure_ascii=False),flush=True)
            page.close()

        # A manual response was formed before a newer rejected server snapshot.
        page=fresh()
        page.locator('[data-testid="fbs-packing-check-wb"]').click()
        manual=page.evaluate('window.qa.pending()[0]')
        tick(page,15000)
        get=page.evaluate('window.qa.pending().at(-1)')
        page.evaluate('id=>window.qa.resolve(id,"A","rejected")',get)
        page.get_by_text('WB не принял ЧЗ',exact=True).wait_for()
        before=snapshot(page)
        page.evaluate('id=>window.qa.resolve(id,"A","accepted")',manual)
        page.get_by_text('ЧЗ принят WB',exact=True).wait_for()
        save(page,'manual_rejected_to_accepted',{'before':before,'after':snapshot(page),'bug_reproduced':True})

        # Same mounted component receives B props while A's POST is unresolved.
        page=fresh()
        page.locator('[data-testid="fbs-packing-check-wb"]').click()
        manual=page.evaluate('window.qa.pending()[0]')
        page.locator('#open-B').click()
        page.locator('[data-order-id="B1"]').wait_for()
        before=snapshot(page)
        page.evaluate('id=>window.qa.resolve(id,"A","accepted")',manual)
        page.locator('[data-order-id="A1"]').wait_for()
        after=snapshot(page)
        assert after['requested']=='requested: B' and after['ids']==['A1']
        save(page,'manual_cross_supply',{'before':before,'after':after,'bug_reproduced':True})

        # Hold the poll, then use the actual Add Orders dialog.
        page=fresh()
        tick(page,15000)
        oldget=page.evaluate('window.qa.pending()[0]')
        page.get_by_role('tab',name='СОСТАВ ✓').click()
        page.locator('[data-testid="fbs-05-workspace-add-orders"]').click()
        page.locator('[data-testid="fbs-05-workspace-add-orders-table"] input[type=checkbox]').first.check()
        page.locator('[data-testid="fbs-05-workspace-add-orders-submit"]').click()
        page.get_by_role('tab',name='УПАКОВКА И МАРКИРОВКА').click()
        page.locator('[data-order-id="6"]').wait_for()
        before=snapshot(page)
        assert 'Размер\nL' in before['sizes'] or any('L' in x for x in before['sizes'])
        page.evaluate('id=>window.qa.resolve(id,"A","pending",false)',oldget)
        page.locator('[data-order-id="6"]').wait_for(state='detached')
        after=snapshot(page)
        assert after['ids']==['A1'] and after['sizes']==[]
        save(page,'old_get_after_add',{'before':before,'after':after,'bug_reproduced':True})

        # Continuous real 15s intervals with every GET resolving at +16s.
        page=fresh()
        page.evaluate('window.qa.setLatency(16000)')
        samples=[]
        for duration in [15000,16000,15000,15000]:
            tick(page,duration)
            samples.append(snapshot(page))
        responses=[x for x in samples[-1]['log'] if x['event']=='response']
        assert len(responses)>=3
        assert all('WB ещё не подтвердил ЧЗ' in s['rows'][0] for s in samples)
        save(page,'poll_16s_starvation',{'samples':samples,'successful_responses':len(responses),'bug_reproduced':True})
        browser.close()
finally:
    (OUT/'result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill()
    logfile.close()
