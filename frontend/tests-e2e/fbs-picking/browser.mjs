// Real built SPA + API + DB. Interception is only explicit failure injection.
import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile, appendFile } from 'node:fs/promises'
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
assert(seed.picking && Object.keys(seed.picking).length>0,'Seed must contain at least one browser case')
const requestedCases=process.env.FBS_PICK_CASES || ''
const suite=process.env.FBS_PICK_SUITE || 'all'
assert(['all','base','extended','targeted'].includes(suite),`Unknown suite: ${suite}`)
assert(suite!=='targeted'||requestedCases,'Targeted suite requires explicit case names')
const selected=requestedCases ? requestedCases.split(',').map(name=>name.trim()).filter(Boolean) : suite==='all' ? null : seed.case_suites?.[suite]
assert(suite==='all'||Array.isArray(selected),`Seed lacks suite ${suite}`)
if(selected) {
  assert(selected.length>0,'Case selection must not be empty')
  assert.equal(new Set(selected).size,selected.length,'Case selection must not contain duplicates')
  for(const name of selected) assert(Object.hasOwn(seed.picking,name),`Unknown selected case: ${name}`)
}
const browser = await chromium.launch({headless:true})
const results = []
let dbSequence = 0
let currentCheckpoints=[]
function snapshot() {
  const result = spawnSync('docker',['compose','--project-name',project,'-f','docker-compose.yml','-f','docker-compose.emulator.yml','-f','frontend/tests-e2e/fbs-picking/compose.yml','exec','-T','-e','FBS_PICK_DISPOSABLE=1','api','python','-m','tests.fbs_picking_browser_verify'],{input:JSON.stringify(seed),encoding:'utf8',timeout:30000,maxBuffer:8*1024*1024})
  assert.equal(result.status,0,`DB readback unavailable: ${result.stderr}`)
  return JSON.parse(result.stdout)
}
const screen = page => page.getByTestId('unload-pick-screen')
const scanner = page => page.getByTestId('pick-scan')
const qty = (page,f,pi=0,si=0) => screen(page).locator(`input[data-testid^="pick-place-qty-${f.products[pi].id}-"][data-testid*="${f.sources[si].container_id || f.sources[si].location_id}"]`).first()
async function login(context,role='admin') {
  const r = await context.request.post(`${root}/api/auth/login`,{data:role==='admin'?seed.login:seed.role_logins[role],timeout:10000})
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
  await workspace.getByRole('tab',{name:/^Подбор(?: ✓)?$/}).click()
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
async function state(name,f,count,{pi=0,si=0,distribution=null}={}) {
  const checkpoint={name,expected_count:count,product:f.products[pi].id,status:'started'}
  currentCheckpoints.push(checkpoint)
  let db
  await expect.poll(()=> { db=snapshot(); const actual=db.picks.filter(p=>p.active&&f.supplies.includes(p.supply)&&p.product===f.products[pi].id).length;checkpoint.actual_count=actual;return actual },{timeout:15000,intervals:[200,500,1000]}).toBe(count)
  await writeFile(path.join(evidence,`${name}-db-${++dbSequence}.json`),JSON.stringify(db,null,2))
  assert(db.unchanged,'Picking/undo/print must preserve total physical stock')
  assert(db.balances.every(b=>b.quantity>=0),'No negative physical source')
  const active=db.picks.filter(p=>p.active&&f.supplies.includes(p.supply)&&p.product===f.products[pi].id)
  const s=f.sources[si]
  const expectedSources=distribution ? Object.entries(distribution).map(([index,quantity])=>({source:f.sources[Number(index)],quantity})) : [{source:s,quantity:count}]
  for(const p of active) {
    const expected=expectedSources.find(one=>one.source.location_id===p.location&&one.source.container_id===p.container)
    assert(expected,'Exact source location and container belong to the expected physical operations')
    if(p.order) assert(f.orders.some(o=>o.id===p.order&&o.product===p.product&&o.supply===p.supply),'Assignment belongs to real planned order')
    if(p.order) assert(db.reserves.some(r=>r.order===p.order&&r.product===p.product&&r.quantity===1),'Order reserve remains')
    if(p.position) {
      const planned=f.positions.find(position=>position.id===p.position)
      assert(planned,'Ozon pick names an exact planned position')
      assert.equal(planned.product,p.product)
      assert.equal(planned.supply,p.supply)
      const position=db.positions.find(position=>position.id===p.position)
      for(const key of ['id','order','product','supply','warehouse','quantity']) assert.equal(position?.[key],planned[key],`Ozon position ${key}`)
      const reserve=db.position_reserves.find(r=>r.position===p.position)
      assert(reserve,'Persisted Ozon per-position reserve exists')
      assert.equal(reserve.product,planned.product)
      assert.equal(reserve.warehouse,planned.warehouse)
      assert.equal(reserve.quantity,planned.quantity,'Picking preserves the whole per-position reserve')
      assert.equal(position.reserved_quantity,planned.quantity)
      assert.equal(position.picked_quantity,db.picks.filter(one=>one.active&&one.position===p.position).length,'Position picked counter equals its actual unit assignments')
    }

  }
  assert.equal(new Set(active.filter(p=>p.order).map(p=>p.order)).size,active.filter(p=>p.order).length,'No double active order assignment')
  for(const {source:expectedSource,quantity:sourceCount} of expectedSources) {
    assert.equal(active.filter(p=>p.location===expectedSource.location_id&&p.container===expectedSource.container_id).length,sourceCount,'Exact number of assignments from this source')
    const initial=expectedSource.initial[f.products[pi].id]
    const balance=db.balances.find(b=>b.product===f.products[pi].id&&b.location===expectedSource.location_id&&b.container===expectedSource.container_id)
    assert.equal(balance?.quantity??0,expectedSource.sortingAlready ? initial : initial-sourceCount,'Source physical balance: transfer or assignment already on sorting')
    if(expectedSource.sortingAlready)assert(active.filter(p=>p.location===expectedSource.location_id).every(p=>p.movement===null),'Already-sorting assignment must not invent a physical transfer')
  }
  if(count) {
    const sorting=active[0].sorting
    const sorted=db.balances.filter(b=>b.product===f.products[pi].id&&b.location===sorting).reduce((n,b)=>n+b.quantity,0)
    const alreadyOnSorting=s.sortingAlready ? f.sources.filter(source=>source.sortingAlready).reduce((n,source)=>n+(source.initial[f.products[pi].id]||0),0) : 0
    assert.equal(sorted,alreadyOnSorting||count,'Exactly the physical picked/sorting units remain accounted for')
  }
  checkpoint.status='verified'
  return db
}
async function run(name,test) {
  if(selected?.length&&!selected.includes(name)) return
  const f=seed.picking[name]
  currentCheckpoints=[]
  const context=await browser.newContext({viewport:{width:1440,height:1050},acceptDownloads:true})
  context.setDefaultTimeout(10000)
  context.setDefaultNavigationTimeout(30000)
  await context.tracing.start({screenshots:true,snapshots:true,sources:true})
  const page=await context.newPage()
  const responses=[],errors=[]
  let phase='prepare'
  let caseTimer
  const cleanups=[]
  const registerCleanup=callback=>cleanups.push(callback)
  const releaseGates=()=>{for(const callback of cleanups.splice(0))callback()}
  let testPromise
  let deadlineExceeded=false
  await writeFile(path.join(evidence,`${name}-progress.json`),JSON.stringify({name,status:'running',phase,started_at:new Date().toISOString()}))
  const deadline=new Promise((_,reject)=>{caseTimer=setTimeout(()=>{deadlineExceeded=true;releaseGates();reject(new Error('Case budget exceeded: 60000ms'))},60000)})
  const observe=(observedPage,label='operator1')=>{
    observedPage.on('pageerror',e=>errors.push(`${label}: ${e.message}`))
    observedPage.on('requestfailed',request=>{
      if(request.url().includes('/api/operations/fbs'))responses.push({url:request.url(),method:request.method(),status:'network-failed',request:request.postData(),failure:request.failure(),operator:label})
    })
    observedPage.on('response',async r=>{
      if(!r.url().includes('/api/operations/fbs'))return
      const raw=await r.json().catch(()=>null)
      const body=Array.isArray(raw) ? raw.filter(row=>f.products.some(p=>p.id===row.product_id)).map(row=>({product_id:row.product_id,sku_code:row.sku_code,seller_article:row.seller_article,barcode:row.barcode,planned_qty:row.planned_qty,picked_qty:row.picked_qty,locations:row.locations}))
        : raw?.supply&&raw?.orders ? {supply:{id:raw.supply.id,marketplace:raw.supply.marketplace,status:raw.supply.status,planned_shipment_date:raw.supply.planned_shipment_date},orders:raw.orders.map(order=>({id:order.id,pick:order.pick,positions:order.positions}))}
        : raw?.items ? {total:raw.total,ids:raw.items.map(item=>item.id)} : raw
      const observed={url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postData(),body,operator:label}
      responses.push(observed)
      await appendFile(path.join(evidence,`${name}-api.jsonl`),JSON.stringify({...observed,body:raw})+'\n').catch(()=>{})
    })
  }
  observe(page)
  try {
    testPromise=(async()=>{
    const token=await login(context)
    if(['tree-order-photo','photo-failure'].includes(name)) {
      await page.route('**/fixture-photo.svg',r=>r.fulfill({status:200,contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="purple"/></svg>'}))
      await page.route('**/missing-test-photo.png',r=>r.fulfill({status:404,body:''}))
    }
    if(name==='scanner-status-audio')await context.addInitScript(()=>{
      window.__pickToneEvents=[]
      const prototype=window.AudioContext?.prototype
      if(!prototype)return
      const create=prototype.createOscillator
      prototype.createOscillator=function(...args){const oscillator=create.apply(this,args);const start=oscillator.start;oscillator.start=function(...values){window.__pickToneEvents.push(oscillator.frequency.value);return start.apply(this,values)};return oscillator}
    })
    const catalogResponse=await context.request.get(`${root}/api/products/linked-wb-catalog`,{headers:{Authorization:`Bearer ${token}`},timeout:10000})
    assert(catalogResponse.ok(),`dependencyblocked: catalog ${catalogResponse.status()}`)
    const catalog=await catalogResponse.json()
    await writeFile(path.join(evidence,`${name}-catalog.json`),JSON.stringify(catalog.filter(row=>f.products.some(p=>p.id===row.id)),null,2))
    for(const p of f.products){
      const row=catalog.find(row=>row.id===p.id);assert(row,`Fixture missing from real catalog: ${p.id}`)
      if(f.marketplace==='ozon') {
        const binding=row.marketplace_bindings.find(binding=>binding.marketplace==='ozon')
        if(!f.allow_null_sku){assert(binding,'Ozon fixture has a genuine marketplace link');assert(binding.external_barcodes.includes(p.barcode),'Ozon primary barcode exists in the actual link');assert.equal(binding.external_offer_id,p.offer)}
      }else {assert(row.wb_barcodes.includes(p.barcode),'Fixture primary barcode missing from catalog');assert(row.wb_barcodes.includes(p.alt),'Fixture extra barcode missing from catalog')}
    }
    await open(page,f)
    phase='process'
    await page.screenshot({path:path.join(evidence,`${name}-opened.png`),fullPage:true})
    await writeFile(path.join(evidence,`${name}-progress.json`),JSON.stringify({name,status:'running',phase,at:new Date().toISOString()}))
    await test(page,f,{context,token,observe,registerCleanup})
    assert.deepEqual(errors,[],'Unhandled browser error')
    })()
    await Promise.race([deadline,testPromise])
    results.push({name,checkpoints:currentCheckpoints,status:'passed',responses})
  } catch(e) {
    results.push({name,checkpoints:currentCheckpoints,status:phase==='prepare'?'preparefailure':'failed',phase,error:String(e.stack||e),responses,browserErrors:errors})
    if(deadlineExceeded) {
      await context.tracing.stop({path:path.join(evidence,`${name}-trace.zip`)}).catch(()=>{})
      await context.close({reason:'Case deadline exceeded: cancel outstanding browser actions'})
      // Wait for the losing branch, including secondary-context cleanup, before the next case.
      await Promise.allSettled([testPromise])
    }
  } finally {
    clearTimeout(caseTimer)
    releaseGates()
    try { const db=snapshot();results.at(-1).dbSummary={unchanged:db.unchanged,balances:db.balances.filter(b=>f.products.some(p=>p.id===b.product)),picks:db.picks.filter(p=>f.products.some(product=>product.id===p.product)),reserves:db.reserves.filter(r=>f.products.some(p=>p.id===r.product)),positions:db.positions.filter(r=>f.products.some(p=>p.id===r.product)),position_reserves:db.position_reserves.filter(r=>f.products.some(p=>p.id===r.product))};await writeFile(path.join(evidence,`${name}-final-db.json`),JSON.stringify(db,null,2));assert(db.unchanged,'Final physical stock changed');assert(db.balances.every(b=>b.quantity>=0),'Final negative source') }catch(e){results.at(-1).dbError=String(e);if(results.at(-1).status==='passed')results.at(-1).status='dependencyblocked'}
    await page.screenshot({path:path.join(evidence,`${name}.png`),fullPage:true,timeout:10000}).catch(()=>{})
    await context.tracing.stop({path:path.join(evidence,`${name}-trace.zip`)}).catch(error=>{results.at(-1).traceError=String(error)})
    await context.close()
    await writeFile(path.join(evidence,`${name}-progress.json`),JSON.stringify({name,status:results.at(-1).status,phase,at:new Date().toISOString()}))
    await writeFile(path.join(evidence,'results.json'),JSON.stringify(results,null,2))
    await writeFile(path.join(evidence,'results-summary.json'),JSON.stringify({suite,expected_cases:selected||Object.keys(seed.picking),test_sha:process.env.TEST_SHA||null,app_sha:process.env.APP_SHA||null,counts:{executed:results.length,passed:results.filter(r=>r.status==='passed').length,failed:results.filter(r=>r.status==='failed').length,blocked:results.filter(r=>!['passed','failed'].includes(r.status)).length},cases:results.map(r=>({...r,responses:r.responses.filter(response=>response.method==='POST'||response.status!=='network-failed'&&response.status>=400||response.status==='network-failed')}))},null,2))
    console.log(`${name}: ${results.at(-1).status}`)
  }
}
await run('packing-flag',async(page,f)=>{
  const before=snapshot()
  const physical=before.balances.find(b=>b.product===f.products[0].id&&b.location===f.sources[0].location_id)
  assert.equal(physical.quantity,30);assert.equal(physical.packed,30);assert.equal(physical.unpacked,0)
  assert.equal(before.picks.filter(p=>p.active&&p.product===f.products[0].id).length,0)
  await source(page,f);await scan(page,f.products[0].sku)
  await state('packing-flag',f,1)
  await expect(qty(page,f)).toHaveValue('1')
})
await run('sources',async(page,f)=>{
  for(const title of ['Ячейка / тара / товар','ШК','Размер','План','Осталось подобрать','Собрано']) await expect(screen(page).getByRole('columnheader',{name:title,exact:true})).toBeVisible()
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
  await expect(page.getByTestId('unload-pick-error')).toBeVisible()
  await expect(page.getByTestId('unload-pick-error')).toHaveText('Снятие сохранено, список не обновлён. Обновите страницу.')
  await page.reload();await expect(qty(page,f)).toHaveValue('1')
  await state('get-failure-reloaded-no-duplicate',f,1)
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
  other.setDefaultTimeout(10000);other.setDefaultNavigationTimeout(30000)
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
await run('manual-conflict',async(page,f,{observe})=>{
  const other=await browser.newContext({viewport:{width:1440,height:1050}})
  other.setDefaultTimeout(10000);other.setDefaultNavigationTimeout(30000)
  try {
    await login(other,'operator');const page2=await other.newPage();observe(page2,'operator2');await open(page2,f)
    await qty(page,f).fill('2');await qty(page,f).press('Tab');await state('manual-conflict-first',f,2)
    // Operator 2 still sees the old zero. Their absolute 1 must not silently erase another pick.
    await qty(page2,f).fill('1');await qty(page2,f).press('Tab');await page2.waitForTimeout(900)
    await state('manual-conflict-no-silent-overwrite',f,2)
  }finally{await other.close()}
})
await run('tabs',async(page,f)=>{
  const w=page.getByTestId('fbs-workspace')
  for(const tab of ['Упаковка и маркировка','Короба','Состав','Подбор']) {await w.getByRole('tab',{name:new RegExp(`^${tab}(?: ✓)?$`)}).click()}
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
  assert.deepEqual(f.supplies.map(id=>active.filter(p=>p.supply===id).length).sort((a,b)=>a-b),[1,3],'Task order may differ from fixture insertion order; each supply keeps its plan')
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
const {registerExtended}=await import('./extended.mjs')
await registerExtended({run,expect,assert,screen,scanner,qty,source,scan,state,snapshot,browser,login,open,root,evidence,writeFile,path})
await browser.close()
assert.equal(results.length,selected ? selected.length : Object.keys(seed.picking).length,'Every selected/seeded case must produce a result')
console.log(JSON.stringify({cases:results.length,passed:results.filter(r=>r.status==='passed').length,failed:results.filter(r=>r.status==='failed').length,preparefailure:results.filter(r=>r.status==='preparefailure').length}))
process.exitCode=results.some(r=>r.status!=='passed')?1:0
