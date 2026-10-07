// These cases use the same real SPA/API/DB process helpers as the original suite.
export async function registerExtended(h) {
  const {run,expect,assert,screen,scanner,qty,source,scan,state,snapshot,browser,login,open,root,evidence,writeFile,path}=h
  const workspace=(page,f)=>page.getByTestId(f.task?'fbs-assembly':'fbs-workspace')
  const tab=(page,f,name)=>workspace(page,f).getByRole('tab',{name:new RegExp(`^${name}(?: ✓)?$`)})
  const error=page=>page.getByTestId('unload-pick-error')
  async function saved(page,f,value,label) {const input=qty(page,f);await input.fill(String(value));await input.press('Tab');await state(label,f,value);await expect(input).toHaveValue(String(value))}
  async function popup(page,f) {const pending=page.waitForEvent('popup');await workspace(page,f).getByRole('button',{name:'Печать листа подбора',exact:true}).click();return await pending}
  async function readOnly(before,label) {const after=snapshot();assert.deepEqual(after,before,`${label} must not mutate stock, assignments or reservations`)}
  async function hardwareCdp(page,characters) {
    const cdp=await page.context().newCDPSession(page)
    const records=[]
    for(const entry of characters) {
      if(entry==='\x1d') {await page.keyboard.press('Control+BracketRight');records.push({key:'GS',code:'Ctrl+]'});continue}
      const record=typeof entry==='string'?{key:entry,code:/[a-z]/i.test(entry)?`Key${entry.toUpperCase()}`:/[0-9]/.test(entry)?`Digit${entry}`:'Slash',text:entry}:entry
      await cdp.send('Input.dispatchKeyEvent',{type:'keyDown',...record})
      await cdp.send('Input.dispatchKeyEvent',{type:'keyUp',key:record.key,code:record.code,modifiers:record.modifiers||0})
      records.push(record)
    }
    await page.keyboard.press('Enter');await cdp.detach();return records
  }
  await run('nested-container',async(page,f)=>{
    await expect(screen(page)).toContainText(f.sources[0].scan)
    await expect(screen(page)).toContainText(f.sources[1].scan)
    await source(page,f,0);await scan(page,f.products[0].sku)
    await expect(screen(page)).toContainText(/недостаточно|недоступ|нет/i)
    await state('nested-pallet-not-child-box',f,0,{si:0})
    await source(page,f,1);await scan(page,f.products[0].sku)
    await state('nested-exact-box',f,1,{si:1});await expect(qty(page,f,0,1)).toHaveValue('1')
  })
  await run('unlocated-container',async(page,f,{context,token})=>{
    await expect(screen(page)).toContainText(/Без ячеек|Без ячейки/)
    await expect(screen(page)).toContainText(f.sources[0].scan)
    await source(page,f);await scan(page,f.products[0].sku)
    await state('unlocated-cargo-exact-source',f,1);await expect(qty(page,f)).toHaveValue('1')
    const response=await context.request.get(`${root}/api/operations/fbs-supplies/${f.supplies[0]}/pick-options`,{headers:{Authorization:`Bearer ${token}`}});assert(response.ok())
    const options=await response.json(),item=options.find(item=>item.product_id===f.products[0].id),physical=item.locations.flatMap(l=>l.sources).find(s=>s.container_path.at(-1)?.id===f.sources[0].container_id)
    assert.equal(physical.quantity,30);assert.equal(physical.picked,1);assert(physical.available>=0&&physical.available<=29,'Already-sorting free availability excludes the assigned physical unit')
    await writeFile(path.join(evidence,'unlocated-actual-options.json'),JSON.stringify(options,null,2))
  })
  await run('foreign-reserve',async(page,f)=>{
    const before=snapshot(),foreign=before.picks.filter(p=>p.active&&p.supply===f.foreign_supply)
    assert.equal(foreign.length,1,'Other order has a real committed physical assignment')
    assert(!before.reserves.some(r=>f.orders.some(o=>o.supply===f.supplies[0]&&o.id===r.order)),'Shortage order has no phantom own reservation')
    await source(page,f);await scan(page,f.products[0].sku)
    await expect(scanner(page)).toBeEnabled();await state('foreign-reserve-denied',f,0)
    await page.getByTestId('pick-source-clear').click();await scan(page,f.products[0].sku)
    await expect(screen(page)).toContainText(/недоступ|нет|недостаточно/i)
    await state('foreign-reserve-auto-denied',f,0)
    assert.deepEqual(snapshot().picks.filter(p=>p.active&&p.supply===f.foreign_supply),foreign)
  })
  await run('foreign-location',async(page,f)=>{
    await scan(page,f.foreign_code)
    await expect(screen(page)).toContainText(/не найден|друг|не.*распознан/i)
    await expect(page.getByTestId('pick-source')).toHaveCount(0);await state('foreign-location',f,0)
    await source(page,f);await scan(page,f.products[0].sku);await state('foreign-location-recovery',f,1)
  })
  await run('modal-scanner',async(page,f)=>{
    await source(page,f)
    await page.getByTestId('fbs-supply-history-open').click()
    const modal=page.getByTestId('fbs-supply-history');await expect(modal).toBeVisible()
    await expect(screen(page)).toContainText('Сканер не слушает')
    await modal.getByRole('button',{name:'Закрыть',exact:true}).focus()
    await scan(page,f.products[0].sku,{focus:'preserve',suffix:'Tab'})
    await expect(modal).toBeVisible();await state('modal-no-picking',f,0)
    await modal.getByRole('button',{name:'Закрыть',exact:true}).click()
    await expect(screen(page)).toContainText('Сканер активен')
    await scan(page,f.products[0].sku,{focus:'blank'});await state('modal-restored',f,1)
  })
  await run('scanner-button',async(page,f)=>{
    await source(page,f)
    await workspace(page,f).getByRole('button',{name:/Далее: Упаковка/}).focus()
    await scan(page,f.products[0].sku,{focus:'preserve'})
    await state('button-no-accidental-next',f,1);await expect(screen(page)).toBeVisible()
    await expect(tab(page,f,'Подбор')).toHaveAttribute('aria-selected','true')
  })
  await run('paste-blur',async(page,f)=>{
    await source(page,f);await scanner(page).focus()
    // Clipboard paste is a real browser action. The listener gets input, not a fake React callback.
    await page.context().grantPermissions(['clipboard-read','clipboard-write'])
    await page.evaluate(code=>navigator.clipboard.writeText(code),f.products[0].sku)
    await page.keyboard.press('Control+V')
    await expect(scanner(page)).toHaveValue(f.products[0].sku)
    await page.waitForTimeout(1000)
    await state('paste-does-not-invent-suffix',f,0)
    await page.getByTestId('pick-left-qty').click();await state('paste-blur-commit',f,1)
    await scanner(page).fill(f.products[0].sku);await scanner(page).press('Enter')
    await state('pasted-enter',f,2)
  })
  await run('outside-no-suffix',async(page,f)=>{
    await source(page,f)
    await scan(page,f.products[0].sku,{focus:'blank',suffix:null})
    await page.waitForTimeout(1100);await state('outside-no-suffix-no-claimed-support',f,0)
    await scan(page,f.products[0].sku,{focus:'blank',suffix:'Tab'});await state('outside-suffix-recovers',f,1)
  })
  await run('special-barcode',async(page,f)=>{
    await source(page,f)
    await scan(page,f.products[0].special,{focus:'blank'});await state('special-ascii-code128',f,1)
    const events=await hardwareCdp(page,[...f.products[0].gs])
    await writeFile(path.join(evidence,'special-gs-events.json'),JSON.stringify(events,null,2))
    await expect(screen(page)).toContainText(/не найден|не.*распознан/i)
    await state('special-gs-safe-rejection',f,1)
    await scan(page,f.products[0].sku);await state('special-gs-queue-recovery',f,2)
  })
  await run('special-ru-layout',async(page,f)=>{
    await source(page,f);await page.getByTestId('pick-left-qty').click();await scanner(page).evaluate(e=>e.blur())
    const en='qwertyuiop[]asdfghjkl;\'zxcvbnm,.',ru='йцукенгшщзхъфывапролджэячсмитьбю'
    const characters=[...f.products[0].special].map(c=>{
      const i=en.indexOf(c.toLowerCase())
      if(/[a-z]/i.test(c)&&i>=0)return{key:c===c.toUpperCase()?ru[i].toUpperCase():ru[i],code:`Key${c.toUpperCase()}`,text:c===c.toUpperCase()?ru[i].toUpperCase():ru[i],modifiers:c===c.toUpperCase()?8:0}
      if(c==='/')return{key:'.',code:'Slash',text:'.'}
      if(c==='?')return{key:',',code:'Slash',text:',',modifiers:8}
      if(c==='&')return{key:'?',code:'Digit7',text:'?',modifiers:8}
      return c
    })
    const events=await hardwareCdp(page,characters)
    await writeFile(path.join(evidence,'special-ru-events.json'),JSON.stringify({catalogue:f.products[0].special,events},null,2))
    await state('special-ru-valid-catalogue-code',f,1)
  })
  await run('server-5xx',async(page,f)=>{
    await source(page,f)
    await page.route('**/pick/scan',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{code:'injected_503',message:'Test temporary server failure'}})}),{times:1})
    await scan(page,f.products[0].sku)
    await expect(screen(page)).toContainText('Test temporary server failure');await state('503-no-success',f,0)
    await scan(page,f.products[0].sku);await state('503-queue-recovery',f,1)
  })
  await run('group-manual',async(page,f)=>{
    await saved(page,f,4,'group-manual-four')
    let db=snapshot(),active=db.picks.filter(p=>p.active&&f.supplies.includes(p.supply))
    assert.equal(active.filter(p=>p.supply===f.supplies[0]).length,3);assert.equal(active.filter(p=>p.supply===f.supplies[1]).length,1)
    await saved(page,f,2,'group-manual-reduction')
    await saved(page,f,3,'group-manual-increment')
    await screen(page).locator('[data-testid^="pick-undo-"]').click();await state('group-manual-undo',f,2)
    await qty(page,f).fill('');await qty(page,f).press('Tab');await state('group-manual-clear',f,0)
  })
  await run('group-conflict',async(page,f,{observe})=>{
    const other=await browser.newContext({viewport:{width:1440,height:1050}});other.setDefaultTimeout(10000);other.setDefaultNavigationTimeout(30000)
    try {
      await login(other,'operator');const p2=await other.newPage();observe(p2,'operator2');await open(p2,f)
      await saved(page,f,2,'group-conflict-first')
      await qty(p2,f).fill('1');await qty(p2,f).press('Tab')
      await expect(error(p2)).toContainText(/измен|проверь|повтор/i)
      await expect(qty(p2,f)).toHaveValue('2');await state('group-conflict-preserves-first',f,2)
    }finally{await other.close()}
  })
  await run('group-partial-set',async(page,f)=>{
    await page.route(`**/fbs-supplies/${f.supplies[1]}/pick/set`,r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{code:'injected_partial',message:'Test second supply failed'}})}),{times:1})
    await qty(page,f).fill('4');await qty(page,f).press('Tab')
    await expect(error(page)).toBeVisible()
    await state('group-partial-real-first-transaction',f,3);await expect(qty(page,f)).toHaveValue('3')
    assert(!snapshot().picks.some(p=>p.active&&p.supply===f.supplies[1]))
  })
  await run('group-lost-set',async(page,f)=>{
    let first
    await page.route('**/pick/set',async r=>{
      first={url:r.request().url(),body:r.request().postDataJSON(),key:r.request().headers()['idempotency-key']}
      const real=await r.fetch();assert.equal(real.status(),200);await r.abort('failed')
    },{times:1})
    await qty(page,f).fill('1');await qty(page,f).press('Tab')
    await expect(error(page)).toBeVisible();await state('group-lost-real-commit',f,1)
    let replay
    await page.route('**/pick/set',async r=>{replay={url:r.request().url(),body:r.request().postDataJSON(),key:r.request().headers()['idempotency-key']};await r.continue()},{times:1})
    await qty(page,f).fill('2');await qty(page,f).press('Tab')
    await expect(error(page)).toContainText('Предыдущая операция сверена')
    assert.deepEqual(replay,first,'Recovery replays exactly the real unknown browser action')
    await state('group-lost-replay-no-double-move',f,1);await expect(qty(page,f)).toHaveValue('1')
    await saved(page,f,2,'group-lost-new-confirmed-target')
  })
  await run('print-fallback',async(page,f)=>{
    const before=snapshot()
    await page.route('**/pick-options',r=>r.abort('failed'),{times:1})
    const p=await popup(page,f)
    await expect(p.locator('body')).toContainText(f.products[0].name)
    await expect(p.locator('body')).toContainText(f.sources[0].code)
    await expect(workspace(page,f)).toContainText('Не удалось получить ячейки и тару')
    await p.close();await readOnly(before,'print fallback with successful production context')
  })
  await run('print-context-failure',async(page,f)=>{
    const before=snapshot()
    await page.route('**/picking-context',r=>r.abort('failed'),{times:1})
    const p=await popup(page,f)
    await expect.poll(()=>p.isClosed()).toBe(true)
    await expect(workspace(page,f)).toContainText('Не удалось получить приёмки и все места хранения — обновите лист подбора.')
    await readOnly(before,'print context failure')
  })
  await run('print-group-warehouses',async(page,f)=>{
    const before=snapshot(),p=await popup(page,f)
    for(const s of f.sources)await expect(p.locator('body')).toContainText(s.code)
    await expect(p.locator('body')).toContainText('Поставка / ячейка / короб')
    await writeFile(path.join(evidence,'print-group-warehouses.html'),await p.content())
    await p.close();await readOnly(before,'group warehouse print')
  })
  await run('print-ozon-route',async(page,f)=>{
    const before=snapshot(),routeText=await workspace(page,f).getByText('Метод доставки Ozon',{exact:true}).locator('..').innerText()
    const route=routeText.replace('Метод доставки Ozon','').trim(),p=await popup(page,f)
    await expect(p.locator('body')).toContainText('Ozon')
    await expect(p.locator('body')).toContainText(f.products[0].offer)
    await expect(p.locator('.meta')).toContainText(route)
    await p.close();await readOnly(before,'Ozon route print')
  })
  await run('exhausted-source-return',async(page,f)=>{
    await saved(page,f,3,'source-exhausted')
    await page.reload();await tab(page,f,'Подбор').click()
    await expect(qty(page,f)).toHaveValue('3')
    await expect(screen(page).locator('[data-testid^="pick-undo-"]')).toHaveCount(0)
    await state('exhausted-reloaded',f,3)
    await qty(page,f).fill('0');await qty(page,f).press('Tab');await state('exhausted-restored-origin',f,0)
    await expect(qty(page,f)).toHaveValue('0')
  })
  await run('ozon-handover',async(page,f)=>{
    const before=snapshot()
    assert(before.operations.some(operation=>operation.supply===f.supplies[0]&&operation.kind==='supply_deliver'&&operation.state==='confirmed'),'Terminal restriction is backed by a confirmed external handover operation')
    await source(page,f);await scan(page,f.products[0].barcode)
    await expect(screen(page)).toContainText('Поставка уже передана: менять подбор нельзя.')
    await state('ozon-handover-no-late-write',f,0)
    await tab(page,f,'Упаковка и маркировка').click();await tab(page,f,'Подбор').click()
    await readOnly(before,'Ozon confirmed handover protects completed external operation, navigation stays open')
  })
  await run('ozon-group-scan',async(page,f)=>{
    await source(page,f)
    await scan(page,f.products[0].barcode);await state('ozon-group-primary-scan',f,1)
    await scan(page,f.products[0].barcode);await state('ozon-group-duplicate-physical-scan',f,2)
    await expect(qty(page,f)).toHaveValue('2')
  })
  await run('full-plan-overflow',async(page,f)=>{
    await source(page,f)
    for(let i=0;i<3;i++){await scan(page,f.products[0].sku);await state(`full-plan-${i+1}`,f,i+1)}
    await expect(page.getByTestId('pick-left-qty')).toHaveText('0')
    await expect(screen(page).getByRole('progressbar')).toHaveAttribute('aria-valuenow','100')
    await scan(page,f.products[0].sku)
    await expect(screen(page)).toContainText(/уже|снят|план|не осталось/i);await state('overflow-no-extra',f,3)
    await expect(qty(page,f)).toHaveValue('3');await expect(screen(page)).toBeVisible()
  })
  await run('manual-invalid',async(page,f)=>{
    const input=qty(page,f)
    await input.fill('-1');await input.press('Tab');await expect(input).toHaveValue('0')
    await input.fill('4');await input.press('Tab');await expect(input).toHaveValue('0');await state('manual-outside-min-max',f,0)
    const failure=page.waitForResponse(r=>r.url().includes('/pick/set')&&r.request().method()==='POST')
    await input.fill('0.5');await input.press('Tab');assert.equal((await failure).status(),422)
    await expect(input).toHaveValue('0');await state('manual-fraction-rejected',f,0)
    await saved(page,f,2,'manual-valid-after-errors')
    await input.fill('');await input.press('Tab');await state('manual-empty-is-zero',f,0)
  })
  await run('tree-order-photo',async(page,f)=>{
    const table=page.getByTestId('fbs-cell-pick-table')
    for(const header of ['Ячейка / тара / товар','ШК','Размер','Остаток в коробе','Собрать','Собрано'])await expect(table.getByRole('columnheader',{name:new RegExp(header.replaceAll(' ','\\s*'))})).toBeVisible()
    const ids=await table.locator('[data-testid^="fbs-pick-item-cell:"]').evaluateAll(rows=>rows.map(r=>r.dataset.testid))
    assert.deepEqual(ids,[2,0,1].map(i=>`fbs-pick-item-cell:${f.sources[i].location_id}`),'Natural cell order A1 A2 A10')
    for(const s of f.sources)await expect(table.getByTestId(`fbs-pick-item-cell:${s.location_id}`)).toContainText('90 шт')
    const geometry=await table.locator('table').evaluate(t=>({layout:getComputedStyle(t).tableLayout,headers:[...t.querySelectorAll('thead th')].map(e=>({text:e.textContent,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,sticky:getComputedStyle(e).position})),inputs:[...t.querySelectorAll('input')].map(e=>({input:e.getBoundingClientRect().toJSON(),cell:e.closest('td').getBoundingClientRect().toJSON()}))}))
    assert.equal(geometry.layout,'fixed');assert(geometry.headers.every(e=>e.sticky==='sticky'))
    for(let i=1;i<geometry.headers.length;i++)assert(geometry.headers[i].left>=geometry.headers[i-1].right-1)
    assert(geometry.inputs.every(e=>e.input.left>=e.cell.left&&e.input.right<=e.cell.right+1),'Quantity inputs remain inside readable columns')
    await writeFile(path.join(evidence,'tree-layout.json'),JSON.stringify(geometry,null,2))
    for(const p of f.products){const row=qty(page,f,f.products.indexOf(p)).locator('xpath=ancestor::tr');await expect(row).toContainText(p.barcode);await expect(row).toContainText(`ART-${p.sku}`);await expect(row).toContainText('XL')}
    await state('tree-display-read-only',f,0)
    await source(page,f,0)
    const selected=table.locator(`[data-row-key="cell:${f.sources[0].location_id}"]`);assert((await selected.evaluate(row=>getComputedStyle(row).boxShadow)).includes('inset'),'Selected source branch is visibly marked')
    await scan(page,f.products[0].sku);await state('tree-first-source-after-scan',f,1)
    await expect(qty(page,f).locator('xpath=ancestor::tr').locator('td').nth(3)).toHaveText('29')
  })
  for(const name of ['load-detail-error','load-options-error','catalog-error'])await run(name,async(page,f)=>{
    const pattern=name==='load-detail-error'?new RegExp(`/fbs-supplies/${f.supplies[0]}(?:\\?.*)?$`):name==='load-options-error'?'**/pick-options':'**/products/linked-wb-catalog*'
    await page.route(pattern,r=>r.abort('failed'))
    await page.reload()
    if(name==='catalog-error') {
      await expect(page.getByTestId('unload-pick-error')).toBeVisible();await expect(screen(page)).toBeVisible()
      await source(page,f);await scan(page,f.products[0].sku);await state('catalog-failure-allowed-scan',f,1)
    }else{
      await expect(page.getByTestId('unload-pick-load-error')).toBeVisible();await expect(screen(page)).toHaveCount(0)
      await state(`${name}-no-demo-no-write`,f,0)
    }
    await page.unroute(pattern);await page.reload();await expect(screen(page)).toBeVisible()
  })
  await run('group-stage-persistence',async(page,f)=>{
    await saved(page,f,6,'group-full-plan')
    await tab(page,f,'Упаковка и маркировка').click();await tab(page,f,'Подбор').click()
    await page.waitForTimeout(16000)
    await expect(tab(page,f,'Подбор')).toHaveAttribute('aria-selected','true')
    await expect(qty(page,f)).toHaveValue('6')
    await workspace(page,f).getByRole('button',{name:'Закрыть',exact:true}).click()
    await page.getByTestId(`fbs-assembly-task-${f.task}`).click()
    const observedStage=await workspace(page,f).getByRole('tab').evaluateAll(tabs=>tabs.filter(tab=>tab.getAttribute('aria-selected')==='true').map(tab=>tab.textContent))
    await writeFile(path.join(evidence,'group-reopened-stage-observed.json'),JSON.stringify({observedStage,no_required_automatic_stage:true}))
    for(const name of ['Состав','Подбор','Упаковка и маркировка','Короба'])await expect(tab(page,f,name)).toBeEnabled()
    await tab(page,f,'Подбор').click();await expect(qty(page,f)).toHaveValue('6')
  })
  await run('local-slow-input',async(page,f)=>{
    await source(page,f);await scanner(page).focus();await page.keyboard.type(f.products[0].sku,{delay:120});await page.keyboard.press('Enter')
    await state('slow-local-enter',f,1)
    await scanner(page).focus();await page.keyboard.type(f.products[0].short,{delay:120});await page.keyboard.press('Enter')
    await state('short-local-enter',f,2)
  })
  await run('photo-failure',async(page,f)=>{
    const good=screen(page).locator('img').first()
    await expect(good).toBeVisible()
    const enlarge=screen(page).getByLabel('Увеличить фото товара').first()
    await enlarge.hover();await expect(page.getByTestId('product-photo-enlarged')).toBeVisible()
    await page.getByTestId('pick-left-qty').hover();await expect(page.getByTestId('product-photo-enlarged')).toHaveCount(0)
    await enlarge.focus();await expect(page.getByTestId('product-photo-enlarged')).toBeVisible()
    await scanner(page).focus();await expect(page.getByTestId('product-photo-enlarged')).toHaveCount(0)
    for(const pi of [1,2]){
      const row=qty(page,f,pi).locator('xpath=ancestor::tr')
      await expect(row.locator('img')).toHaveCount(0);await expect(row.locator('svg[data-testid="PersonIcon"]')).toHaveCount(1)
    }
    await state('photo-no-stock-write',f,0)
  })
  await run('print-picked',async(page,f)=>{
    await source(page,f);await scan(page,f.products[0].sku);await state('print-picked-before',f,1)
    const before=snapshot(),p=await popup(page,f)
    const headers=await p.locator('thead th').allTextContents()
    assert.deepEqual(headers,['№','Фото','Товар','Артикул','Цвет','Размер','Поставка / ячейка / короб','Заказы WB','Стикер','Взять','Подобрано','Маркировка'])
    await expect(p.locator('tbody')).toContainText(f.products[0].name)
    await expect(p.locator('tbody')).toContainText(/1\s*\/\s*3/)
    await expect(p.locator('body')).toContainText(f.sources[0].code)
    for(const origin of f.print_origins){await expect(p.locator('body')).toContainText(origin.title);await expect(p.locator('body')).toContainText(origin.barcode)}
    await expect(p.locator('body')).toContainText('Без привязки к документу:')
    await p.close();await readOnly(before,'print picked fresh server data')
  })
  await run('next-and-history',async(page,f)=>{
    await page.getByTestId('fbs-supply-history-open').click();await expect(page.getByTestId('fbs-supply-history')).toBeVisible()
    await page.getByTestId('fbs-supply-history').getByRole('button',{name:'Закрыть',exact:true}).click()
    await workspace(page,f).getByRole('button',{name:/Далее: Упаковка/}).click()
    await expect(tab(page,f,'Упаковка и маркировка')).toHaveAttribute('aria-selected','true')
    await tab(page,f,'Подбор').click();await source(page,f);await scan(page,f.products[0].sku);await state('next-return-picking',f,1)
  })
  await run('scanner-status-audio',async(page,f)=>{
    await expect(screen(page)).toContainText('Сканер активен — место или товар')
    await source(page,f);await expect(screen(page)).toContainText('товар, который снимаете')
    const before=await page.evaluate(()=>window.__pickToneEvents.length)
    await scan(page,'NOT-IN-SUPPLY-EXT')
    await expect(screen(page).locator('[aria-live="polite"]')).toContainText(/не найден/i)
    const bad=await page.evaluate(n=>window.__pickToneEvents.slice(n),before)
    assert.deepEqual(bad,[220,180],'Distinct error tones are actually scheduled')
    const after=await page.evaluate(()=>window.__pickToneEvents.length)
    await scan(page,f.products[0].sku);await state('scan-status-success',f,1)
    await expect(screen(page).locator('[aria-live="polite"]')).toContainText('снято 1')
    assert.deepEqual(await page.evaluate(n=>window.__pickToneEvents.slice(n),after),[1800],'Success tone is actually scheduled')
  })
  await run('loading-busy',async(page,f,{registerCleanup})=>{
    let releaseOptions,optionsSeen
    const seen=new Promise(resolve=>optionsSeen=resolve),gate=new Promise(resolve=>releaseOptions=resolve)
    registerCleanup(()=>{optionsSeen();releaseOptions()})
    await page.route('**/pick-options',async r=>{optionsSeen();await gate;await r.continue()},{times:1})
    const navigation=page.reload();await seen
    await expect(page.getByText('Загружаем подбор',{exact:true})).toBeVisible()
    await expect(page.getByText('Получаем состав отгрузки и места хранения.',{exact:true})).toBeVisible()
    releaseOptions();await navigation;await expect(screen(page)).toBeVisible();await source(page,f)
    let releaseScan,scanSeen
    const waiting=new Promise(resolve=>scanSeen=resolve),scanGate=new Promise(resolve=>releaseScan=resolve)
    registerCleanup(()=>{scanSeen();releaseScan()})
    await page.route('**/pick/scan',async r=>{scanSeen();await scanGate;await r.continue()},{times:1})
    await scan(page,f.products[0].sku);await waiting
    await expect(scanner(page)).toBeDisabled();await expect(screen(page)).toContainText('Ищем…')
    await scan(page,f.products[0].sku,{focus:'blank'})
    releaseScan();await state('busy-queue-two',f,2);await expect(scanner(page)).toBeEnabled()
  })
  await run('date-controls',async(page,f)=>{
    const input=page.getByTestId('cal-02-fbs-shipment-date'),save=page.getByTestId('cal-02-fbs-shipment-date-save')
    await expect(save).toBeDisabled();await input.fill('2026-12-15');await expect(save).toBeEnabled();await save.click()
    await expect(save).toBeDisabled();await expect(page.getByTestId('cal-02-fbs-shipment-date-clear')).toBeVisible()
    await page.reload();await expect(input).toHaveValue('2026-12-15')
    assert.equal(snapshot().supplies.find(s=>s.id===f.supplies[0]).planned_shipment_date,'2026-12-15')
    await page.getByTestId('cal-02-fbs-shipment-date-clear').click();await expect(input).toHaveValue('')
    await expect(page.getByTestId('cal-02-fbs-shipment-date-clear')).toHaveCount(0)
    await page.reload();await expect(input).toHaveValue('');await state('date-read-only-stock',f,0)
    assert.equal(snapshot().supplies.find(s=>s.id===f.supplies[0]).planned_shipment_date,null)
  })
  await run('operator-denied',async(page,f)=>{
    const other=await browser.newContext();other.setDefaultTimeout(10000)
    try {
      const token=await login(other,'operator_no_packaging'),p=await other.newPage();await p.goto(`${root}/app/ff/fbs`)
      await expect(p.getByTestId('fbs-orders-screen')).toHaveCount(0)
      await expect(p.getByTestId('ff-access-denied')).toBeVisible()
      await expect(p.getByRole('heading',{name:'Нет доступа',exact:true})).toBeVisible()
      const r=await other.request.get(`${root}/api/operations/fbs-supplies/${f.supplies[0]}/pick-options`,{headers:{Authorization:`Bearer ${token}`}})
      assert.equal(r.status(),403);await state('operator-no-packaging-access',f,0)
    }finally{await other.close()}
  })
  await run('multi-source-undo',async(page,f)=>{
    await source(page,f,0);await scan(page,f.products[0].sku);await state('multi-source-first',f,1)
    await source(page,f,1);await scan(page,f.products[0].sku)
    await state('multi-source-second',f,2,{distribution:{0:1,1:1}})
    const undo=screen(page).locator('[data-testid^="pick-undo-"]');await expect(undo).toHaveCount(1)
    assert((await undo.getAttribute('data-testid')).includes(f.sources[1].location_id),'Undo belongs to the last source only')
    await undo.click();await state('multi-source-last-undo',f,1,{distribution:{0:1,1:0}})
  })
  await run('wb-source-banner',async(page,f)=>{
    await expect(workspace(page,f)).toContainText('Поставка создана в кабинете WB.')
    for(const label of ['Склад WMS','Маршрут','Дата отгрузки'])await expect(workspace(page,f).getByText(label,{exact:true}).first()).toBeVisible()
    await expect(workspace(page,f)).toContainText('Сдать в Wildberries до')
    await source(page,f);await scan(page,f.products[0].sku);await state('wb-source-actual-pick',f,1)
  })
  await run('source-undo-history',async(page,f)=>{
    await source(page,f);await scan(page,f.products[0].sku);await state('undo-source-first',f,1)
    const undo=screen(page).locator('[data-testid^="pick-undo-"]');await expect(undo).toHaveCount(1)
    await undo.click();await state('undo-source-return',f,0)
    await scan(page,f.products[0].sku);await state('undo-before-refresh',f,1)
    await page.reload();await expect(undo).toHaveCount(0);await expect(qty(page,f)).toHaveValue('1')
    await qty(page,f).fill('0');await qty(page,f).press('Tab');await state('manual-return-without-undo-history',f,0)
  })
}
