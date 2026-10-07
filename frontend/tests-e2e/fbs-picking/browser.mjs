// Real built SPA + API + DB. Interception is only explicit failure injection.
import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
const { chromium, expect } = await import(process.env.WMS_PLAYWRIGHT_MODULE || '@playwright/test')
const root = process.env.FBS_PICK_URL || 'http://127.0.0.1:25174'
assert(['127.0.0.1','localhost'].includes(new URL(root).hostname))
const evidence = process.env.FBS_PICK_EVIDENCE || 'artifacts/fbs-picking'
await mkdir(evidence,{recursive:true})
const seed = JSON.parse(await readFile(process.env.FBS_PICK_SEED || `${evidence}/seed.json`,'utf8'))
const project = process.env.FBS_PICK_PROJECT
assert(project?.startsWith('fbs-picking-'),'Require the runner-owned disposable compose project')
const browser = await chromium.launch({headless:true})
const results = []
const selected = process.env.FBS_PICK_CASES?.split(',').filter(Boolean)
let dbSequence = 0
function snapshot() {
  const result = spawnSync('docker',['compose','--project-name',project,'-f','docker-compose.yml','-f','docker-compose.emulator.yml','-f','frontend/tests-e2e/fbs-picking/compose.yml','exec','-T','-e','FBS_PICK_DISPOSABLE=1','api','python','-m','tests.fbs_picking_browser_verify'],{input:JSON.stringify(seed),encoding:'utf8',timeout:30000,maxBuffer:8*1024*1024})
  assert.equal(result.status,0,`DB readback unavailable: ${result.stderr}`)
  return JSON.parse(result.stdout)
}
const screen = page => page.getByTestId('unload-pick-screen')
const scanner = page => page.getByTestId('pick-scan')
const qty = (page,f,pi=0,si=0) => screen(page).locator(`input[data-testid^="pick-place-qty-${f.products[pi].id}-"][data-testid*="${f.sources[si].container_id || f.sources[si].location_id}"]`).first()
async function login(context,role='admin') {
  const r = await context.request.post(`${root}/api/auth/login`,{data:role==='admin'?seed.login:seed.role_logins[role]})
  assert(r.ok(),`dependencyblocked: login ${r.status()}`)
  const {access_token:token} = await r.json()
  await context.addInitScript(token=>localStorage.setItem('wms_token_ff',token),token)
  return token
}
async function open(page,f,si=0) {
  await page.goto(`${root}/app/ff/fbs`)
  await expect(page.getByTestId('fbs-orders-screen')).toBeVisible()
  await page.getByRole('tab',{name:'В работе',exact:true}).click()
  await page.getByTestId(f.task?`fbs-assembly-task-${f.task}`:`fbs-18-supply-${f.supplies[si]}`).click()
  const workspace = page.getByTestId(f.task?'fbs-assembly':'fbs-workspace')
  await expect(workspace).toBeVisible()
  await workspace.getByRole('tab',{name:'Подбор',exact:true}).click()
  await expect(screen(page)).toBeVisible()
  await expect(page.getByTestId('fbs-cell-pick-table')).toBeVisible()
}
async function scan(page,code,{focus='scanner',suffix='Enter'}={}) {
  if(focus==='scanner') await scanner(page).focus()
  if(focus==='blank') { await page.getByTestId('pick-left-qty').click(); await scanner(page).evaluate(e=>e.blur()) }
  await page.keyboard.type(code,{delay:2})
  if(suffix) await page.keyboard.press(suffix)
}
async function source(page,f,si=0) {
  await scan(page,f.sources[si].scan)
  await expect(page.getByTestId('pick-source')).toContainText(f.sources[si].container_id?f.sources[si].scan:f.sources[si].code)
  await expect(scanner(page)).toBeEnabled()
}
async function state(name,f,count,{pi=0,si=0}={}) {
  let db
  await expect.poll(()=> { db=snapshot(); return db.picks.filter(p=>p.active&&f.supplies.includes(p.supply)&&p.product===f.products[pi].id).length },{timeout:15000,intervals:[200,500,1000]}).toBe(count)
  await writeFile(path.join(evidence,`${name}-db-${++dbSequence}.json`),JSON.stringify(db,null,2))
  assert(db.unchanged,'Picking/undo/print must preserve total physical stock')
  assert(db.balances.every(b=>b.quantity>=0),'No negative physical source')
  const active=db.picks.filter(p=>p.active&&f.supplies.includes(p.supply)&&p.product===f.products[pi].id)
  const s=f.sources[si]
  for(const p of active) {
    assert.equal(p.location,s.location_id,'Exact source location')
    assert.equal(p.container,s.container_id,'Exact source container')
    if(p.order) assert(f.orders.some(o=>o.id===p.order&&o.product===p.product&&o.supply===p.supply),'Assignment belongs to real planned order')
    if(p.order) assert(db.reserves.some(r=>r.order===p.order&&r.product===p.product&&r.quantity===1),'Order reserve remains')
  }
  assert.equal(new Set(active.filter(p=>p.order).map(p=>p.order)).size,active.filter(p=>p.order).length,'No double active order assignment')
  const initial=s.initial[f.products[pi].id]
  const balance=db.balances.find(b=>b.product===f.products[pi].id&&b.location===s.location_id&&b.container===s.container_id)
  assert.equal(balance?.quantity??0,initial-count,'Physical source decreased by the actual active picks')
  if(count) {
    const sorting=active[0].sorting
    const sorted=db.balances.filter(b=>b.product===f.products[pi].id&&b.location===sorting).reduce((n,b)=>n+b.quantity,0)
    assert.equal(sorted,count,'Exactly the picked units are on sorting')
  }
  return db
}
async function run(name,test) {
  if(selected?.length&&!selected.includes(name)) return
  const f=seed.picking[name]
  const context=await browser.newContext({viewport:{width:1440,height:1050},acceptDownloads:true})
  await context.tracing.start({screenshots:true,snapshots:true,sources:true})
  const page=await context.newPage()
  const responses=[],errors=[]
  let phase='prepare'
  page.on('pageerror',e=>errors.push(e.message))
  page.on('response',async r=>{
    if(!r.url().includes('/api/operations/fbs'))return
    const body=await r.json().catch(()=>null)
    responses.push({url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postData(),body})
  })
  try {
    const token=await login(context)
    const catalogResponse=await context.request.get(`${root}/api/products/linked-wb-catalog`,{headers:{Authorization:`Bearer ${token}`}})
    assert(catalogResponse.ok(),`dependencyblocked: catalog ${catalogResponse.status()}`)
    const catalog=await catalogResponse.json()
    await writeFile(path.join(evidence,`${name}-catalog.json`),JSON.stringify(catalog.filter(row=>f.products.some(p=>p.id===row.id)),null,2))
    if(!name.startsWith('ozon')) for(const p of f.products){const row=catalog.find(row=>row.id===p.id);assert(row,`Fixture missing from real catalog: ${p.id}`);assert(row.wb_barcodes.includes(p.barcode),'Fixture primary barcode missing from catalog');assert(row.wb_barcodes.includes(p.alt),'Fixture extra barcode missing from catalog')}
    await open(page,f)
    phase='process'
    await test(page,f,{context,token})
    assert.deepEqual(errors,[],'Unhandled browser error')
    results.push({name,status:'passed',responses})
  } catch(e) {
    results.push({name,status:phase==='prepare'?'preparefailure':'failed',phase,error:String(e.stack||e),responses,browserErrors:errors})
  } finally {
    try { const db=snapshot();await writeFile(path.join(evidence,`${name}-final-db.json`),JSON.stringify(db,null,2));assert(db.unchanged,'Final physical stock changed');assert(db.balances.every(b=>b.quantity>=0),'Final negative source') }catch(e){results.at(-1).dbError=String(e);if(results.at(-1).status==='passed')results.at(-1).status='dependencyblocked'}
    await page.screenshot({path:path.join(evidence,`${name}.png`),fullPage:true}).catch(()=>{})
    await context.tracing.stop({path:path.join(evidence,`${name}-trace.zip`)})
    await context.close()
    await writeFile(path.join(evidence,'results.json'),JSON.stringify(results,null,2))
    console.log(`${name}: ${results.at(-1).status}`)
  }
}
await run('sources',async(page,f)=>{
  for(const title of ['Ячейка / тара / товар','ШК','Размер','Собрать','Собрано']) await expect(screen(page).getByRole('columnheader',{name:title,exact:true})).toBeVisible()
  await expect(page.getByTestId('pick-left-qty')).toHaveText('3')
  for(const s of f.sources) await expect(screen(page)).toContainText(s.container_id?s.scan:s.code)
  await source(page,f,2)
  await state('sources-selected-only',f,0,{si:2})
  await scan(page,f.products[0].barcode)
  await state('sources',f,1,{si:2})
  await expect(qty(page,f,0,2)).toHaveValue('1')
  await page.reload(); await expect(screen(page)).toBeVisible()
  await expect(qty(page,f,0,2)).toHaveValue('1')
  await expect(page.getByTestId('pick-source')).toHaveCount(0)
})
await run('auto',async(page,f)=>{
  await scan(page,f.products[0].sku)
  await state('auto',f,1)
  await expect(qty(page,f)).toHaveValue('1')
})
await run('ambiguous',async(page,f)=>{
  await scan(page,f.products[0].sku)
  await expect(screen(page)).toContainText(/лежит в .* местах|уточните место/)
  await state('ambiguous',f,0)
})
await run('wrong',async(page,f)=>{
  await source(page,f)
  await scan(page,f.products[1].sku)
  await expect(screen(page)).toContainText(/недостаточно|нет|не.*найден|недоступ/i)
  await state('wrong-source',f,0,{pi:1})
  await scan(page,'ABSENT-PICK-PRODUCT')
  await expect(scanner(page)).toBeEnabled()
  await scan(page,f.products[0].sku)
  await state('wrong-queue-recovery',f,1)
})
await run('change',async(page,f)=>{
  await source(page,f,0); await source(page,f,1)
  await scan(page,f.products[0].sku)
  await state('change',f,1,{si:1})
  await page.getByTestId('pick-source-clear').click()
  await expect(page.getByTestId('pick-source')).toHaveCount(0)
  await scan(page,f.products[0].sku)
  await expect(screen(page)).toContainText(/местах|уточните место/)
  await state('change-clear',f,1,{si:1})
})
await run('burst',async(page,f)=>{
  await expect(screen(page).locator('input[data-testid^="pick-place-qty-"]')).toHaveCount(16)
  await source(page,f)
  const start=Date.now()
  // One hardware-like stream, without waiting for HTTP/React between repetitions.
  await scanner(page).focus()
  for(let i=0;i<5;i++){await page.keyboard.type(f.products[0].barcode,{delay:1});await page.keyboard.press('Enter')}
  await state('burst',f,5)
  await expect(qty(page,f)).toHaveValue('5')
  await writeFile(path.join(evidence,'burst-observed-time.json'),JSON.stringify({elapsed_ms:Date.now()-start,scans:5,no_production_sla:true}))
})
await run('number-scan',async(page,f)=>{
  await source(page,f)
  const input=qty(page,f)
  await input.focus()
  await scan(page,f.products[0].barcode,{focus:'preserve'})
  await state('number-scan',f,1)
  await expect(input).toHaveValue('1')
  await expect(input).toBeFocused()
  await page.waitForTimeout(700)
  await state('number-scan-no-late-manual',f,1)
})
await run('layout',async(page,f)=>{
  await source(page,f)
  const en='qwertyuiop[]asdfghjkl;\'zxcvbnm,.'
  const ru='йцукенгшщзхъфывапролджэячсмитьбю'
  const translated=[...f.products[0].sku].map(c=>{const i=en.indexOf(c.toLowerCase());return i<0?c:(c===c.toUpperCase()?ru[i].toUpperCase():ru[i])}).join('')
  await page.getByTestId('pick-left-qty').click();await scanner(page).evaluate(e=>e.blur())
  const cdp=await page.context().newCDPSession(page)
  const events=[]
  for(let i=0;i<translated.length;i++) {
    const key=translated[i],physical=f.products[0].sku[i]
    const code=/[a-z]/i.test(physical)?`Key${physical.toUpperCase()}`:/[0-9]/.test(physical)?`Digit${physical}`:'Minus'
    const modifiers=/[A-Z]/.test(physical)?8:0
    const event={key,code,text:key,unmodifiedText:key.toLowerCase(),modifiers}
    await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',...event})
    await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key,code,modifiers})
    events.push(event)
  }
  await cdp.send('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9})
  await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9})
  await writeFile(path.join(evidence,'layout-cdp-events.json'),JSON.stringify(events,null,2))
  await cdp.detach()
  await state('layout-ru',f,1)
  await scan(page,f.products[0].alt,{focus:'blank',suffix:'Enter'})
  await state('layout-additional-ean',f,2)
})
await run('manual',async(page,f)=>{
  const input=qty(page,f)
  await input.fill('12');await input.press('Tab')
  await state('manual-12',f,12);await expect(input).toHaveValue('12')
  await input.fill('10');await input.press('Tab')
  await state('manual-reduce',f,10)
  await input.fill('11');await input.press('Tab');await state('manual-increase',f,11)
  await screen(page).locator('[data-testid^="pick-undo-"]').click()
  await state('manual-undo',f,10)
  await input.fill('0');await input.press('Tab');await state('manual-zero',f,0)
  await page.reload();await expect(qty(page,f)).toHaveValue('0')
})
await run('early-exit',async(page,f)=>{
  await qty(page,f).fill('12')
  // Deliberately leave before the documented 400ms debounce.
  await page.getByTestId('fbs-workspace').getByRole('button',{name:'Закрыть',exact:true}).click()
  await expect(page.getByTestId('fbs-workspace')).toHaveCount(0)
  await open(page,f)
  await state('early-exit',f,12)
  await expect(qty(page,f)).toHaveValue('12')
})
await run('replay',async(page,f,{context,token})=>{
  await source(page,f)
  let request
  const key='browser-one-physical-action-replay'
  await page.route('**/pick/scan',async route=>{
    request={url:route.request().url(),body:route.request().postDataJSON()}
    await route.continue({headers:{...route.request().headers(),'idempotency-key':key}})
  })
  await scan(page,f.products[0].sku)
  await state('replay-initial',f,1)
  await page.unroute('**/pick/scan')
  const replay=await context.request.post(request.url,{data:request.body,headers:{Authorization:`Bearer ${token}`,'Idempotency-Key':key}})
  assert(replay.ok(),`Replay ${replay.status()}`)
  await state('replay-same-operation',f,1)
  // Another identical physical scan is another action and must add a unit.
  await scan(page,f.products[0].sku)
  await state('replay-second-physical',f,2)
})
await run('lost',async(page,f)=>{
  await source(page,f)
  let realStatus
  await page.route('**/pick/scan',async route=>{
    const response=await route.fetch();realStatus=response.status()
    await route.abort('failed') // Real API transaction finished; only its response is lost.
  },{times:1})
  await scan(page,f.products[0].sku)
  await state('lost-committed-before-abort',f,1)
  assert.equal(realStatus,200)
  await page.reload();await expect(qty(page,f)).toHaveValue('1')
  await state('lost-after-reload',f,1)
})
await run('get-failure',async(page,f)=>{
  await source(page,f)
  await page.route('**/pick-options',r=>r.abort('failed'),{times:1})
  await scan(page,f.products[0].sku)
  await state('get-failure-committed',f,1)
  await expect(screen(page)).toContainText(/сохранено.*не обновлён|Обновите страницу/i)
  await page.reload();await expect(qty(page,f)).toHaveValue('1')
})
await run('network',async(page,f)=>{
  await source(page,f)
  await page.route('**/pick/scan',r=>r.abort('failed'),{times:1})
  await scan(page,f.products[0].sku)
  await expect(scanner(page)).toBeEnabled()
  await state('network-before-server',f,0)
  await scan(page,f.products[0].sku)
  await state('network-recovery',f,1)
})
await run('last-unit',async(page,f,{context})=>{
  const other=await browser.newContext({viewport:{width:1440,height:1050}})
  try {
    await login(other,'operator');const page2=await other.newPage();await open(page2,f,1)
    await source(page,f);await source(page2,f)
    await Promise.all([scan(page,f.products[0].sku),scan(page2,f.products[0].sku)])
    await state('last-unit',f,1)
    await expect(scanner(page)).toBeEnabled();await expect(scanner(page2)).toBeEnabled()
    const db=snapshot();const winners=db.picks.filter(p=>p.active&&f.supplies.includes(p.supply))
    assert.equal(winners.length,1)
    assert.equal(context.pages().length,1)
  } finally {await other.close()}
})
await run('manual-conflict',async(page,f)=>{
  const other=await browser.newContext({viewport:{width:1440,height:1050}})
  try {
    await login(other,'operator');const page2=await other.newPage();await open(page2,f)
    await qty(page,f).fill('2');await qty(page,f).press('Tab');await state('manual-conflict-first',f,2)
    // Operator 2 still sees the old zero. Their absolute 1 must not silently erase another pick.
    await qty(page2,f).fill('1');await qty(page2,f).press('Tab');await page2.waitForTimeout(900)
    await state('manual-conflict-no-silent-overwrite',f,2)
  }finally{await other.close()}
})
await run('tabs',async(page,f)=>{
  const w=page.getByTestId('fbs-workspace')
  for(const tab of ['Упаковка и маркировка','Короба','Состав','Подбор']) {await w.getByRole('tab',{name:tab,exact:true}).click()}
  await source(page,f);await scan(page,f.products[0].sku);await state('tabs',f,1)
})
await run('print',async(page,f)=>{
  const before=snapshot()
  const popupPromise=page.waitForEvent('popup')
  await page.getByRole('button',{name:'Печать листа подбора',exact:true}).click()
  const popup=await popupPromise
  await expect(popup.locator('body')).toContainText(f.products[0].name)
  await expect(popup.locator('body')).toContainText(f.sources[0].code)
  await writeFile(path.join(evidence,'print.html'),await popup.content())
  await popup.close()
  assert.deepEqual(snapshot(),before,'Read-only print must not change DB')
  await page.evaluate(()=>{window.open=()=>null})
  await page.getByRole('button',{name:'Печать листа подбора',exact:true}).click()
  await expect(page.getByTestId('fbs-workspace')).toContainText(/окно|всплывающ/i)
  assert.deepEqual(snapshot(),before)
})
await run('group',async(page,f)=>{
  await expect(page.getByTestId('fbs-assembly')).toContainText(/2 постав/)
  await expect(page.getByTestId('pick-left-qty')).toHaveText('6')
  await source(page,f)
  for(let i=0;i<4;i++){await scan(page,f.products[0].sku);await expect(scanner(page)).toBeEnabled()}
  const db=await state('group',f,4)
  const active=db.picks.filter(p=>p.active&&f.supplies.includes(p.supply))
  assert.equal(active.filter(p=>p.supply===f.supplies[0]).length,3)
  assert.equal(active.filter(p=>p.supply===f.supplies[1]).length,1)
  await page.reload();await expect(qty(page,f)).toHaveValue('4')
})
for(const name of ['ozon','ozon-group']) await run(name,async(page,f)=>{
  for(const p of f.products)await expect(screen(page)).toContainText(p.name)
  await expect(screen(page)).toContainText(f.products[0].offer)
  await source(page,f)
  await scan(page,f.products[0].barcode);await state(name,f,1)
  await scan(page,f.products[0].barcode);await state(`${name}-second`,f,2)
  await expect(qty(page,f)).toHaveValue('2')
  await scan(page,f.products[1].barcode);await state(`${name}-position-2`,f,1,{pi:1})
  await page.reload();await expect(qty(page,f)).toHaveValue('2')
})
await run('group-sellers',async(page,f)=>{
  await expect(page.getByTestId('pick-left-qty')).toHaveText('6')
  assert.equal(f.products[0].barcode,f.products[1].barcode)
  await source(page,f,0);await scan(page,f.products[0].barcode)
  await state('group-sellers-first',f,1,{pi:0,si:0})
  await source(page,f,1);await scan(page,f.products[1].barcode)
  await state('group-sellers-second',f,1,{pi:1,si:1})
  await expect(qty(page,f,0,0)).toHaveValue('1')
  await expect(qty(page,f,1,1)).toHaveValue('1')
})
await run('ozon-null',async(page,f)=>{
  await source(page,f)
  await scan(page,f.products[0].barcode)
  await state('ozon-null-server-commit',f,1)
  // A committed scan must not be presented as a failed scan inviting a duplicate.
  await expect(qty(page,f)).toHaveValue('1')
  await expect(screen(page)).not.toContainText('Сервер распознал товар, но не вернул')
  await page.reload();await expect(qty(page,f)).toHaveValue('1')
  await state('ozon-null-reload',f,1)
})
await run('empty',async(page,f)=>{
  await expect(screen(page)).toContainText('В отгрузке нет товаров')
  await expect(screen(page).locator('input[data-testid^="pick-place-qty-"]')).toHaveCount(0)
  await state('empty',f,0)
})
await run('no-stock',async(page,f)=>{
  await expect(screen(page)).toContainText('Нет на складе')
  await expect(screen(page).locator('input[data-testid^="pick-place-qty-"]')).toHaveCount(0)
  await scan(page,f.products[0].sku);await expect(scanner(page)).toBeEnabled();await state('no-stock',f,0)
})
await run('partial',async(page,f)=>{
  await source(page,f);await scan(page,f.products[0].sku);await state('partial',f,1)
  await expect(page.getByTestId('pick-left-qty')).toHaveText('2')
  await page.getByTestId('fbs-workspace').getByRole('button',{name:'Закрыть',exact:true}).click()
  await open(page,f);await expect(qty(page,f)).toHaveValue('1')
})
await run('suffix',async(page,f)=>{
  await source(page,f)
  await scan(page,f.products[0].sku,{suffix:null})
  await state('suffix-silence',f,1)
  await scanner(page).fill(f.products[0].sku);await scanner(page).press('Tab')
  await state('suffix-tab',f,2)
})
await run('focus',async(page,f)=>{
  await source(page,f)
  await scan(page,f.products[0].sku)
  await state('focus-scanner',f,1);await expect(scanner(page)).toBeFocused()
  await scan(page,f.products[0].sku,{focus:'blank'})
  await state('focus-blank',f,2)
  await expect(page.getByTestId('pick-source')).toContainText(f.sources[0].code)
  await expect(qty(page,f)).toHaveValue('2')
})
await browser.close()
console.log(JSON.stringify({cases:results.length,passed:results.filter(r=>r.status==='passed').length,failed:results.filter(r=>r.status==='failed').length,preparefailure:results.filter(r=>r.status==='preparefailure').length}))
process.exitCode=results.some(r=>r.status!=='passed')?1:0
