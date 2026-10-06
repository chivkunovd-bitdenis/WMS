import { chromium } from 'playwright'
import fs from 'node:fs'
assertRemote()
function assertRemote() { if (process.env.GITHUB_ACTIONS !== 'true') throw Error('GitHub only') }
const out = process.env.C19_OUTPUT
fs.mkdirSync(out, {recursive:true})
const browser = await chromium.launch({headless:true})
const page = await browser.newPage({viewport:{width:1440,height:1100}})
const facts = {http:[], errors:[], screens:[]}
page.on('pageerror', e => facts.errors.push(e.message))
page.on('response', async r => {
 if(r.url().includes('/api/')) {
  let body; try {body=await r.json()} catch {body=await r.text()}
  facts.http.push({url:r.url(),status:r.status(),body})
 }
})
try {
 const fixture = await (await page.request.get('http://127.0.0.1:8000/fixture')).json()
 const url=`http://127.0.0.1:5173/c19.html?supply=${fixture.supply_id}`
 for(const phase of ['partial','full']) {
  const response=await page.request.post(`http://127.0.0.1:8000/fixture/${phase}`)
  const raw=await response.text()
  let body; try {body=JSON.parse(raw)} catch {body={raw}}
  facts[phase]=body
  if(response.status()!==200) throw Error(JSON.stringify(body))
  await Promise.all([
   page.waitForResponse(r => r.url().endsWith('/workspace') && r.status()===200),
   page.goto(url),
  ])
  await page.getByRole('tab',{name:/^Состав/}).click()
  await page.getByText('Состав поставки',{exact:true}).waitFor()
  await page.screenshot({path:`${out}/${phase}-composition.png`,fullPage:true})
  facts.screens.push({name:`${phase}-composition`,text:await page.locator('body').innerText()})
  for(const label of ['Подбор','Упаковка и маркировка','Короба']) {
   const tab=page.getByRole('tab',{name:new RegExp(`^${label}`)})
   if(await tab.isEnabled()) {
    await tab.click()
    await page.screenshot({path:`${out}/${phase}-${label}.png`,fullPage:true})
    facts.screens.push({name:`${phase}-${label}`,text:await page.locator('body').innerText()})
   }
  }
  await page.getByRole('tab',{name:/^Состав/}).click()
  await page.getByTestId('fbs-supply-history-open').click()
  await page.getByTestId('fbs-supply-history-timeline').waitFor()
  await page.screenshot({path:`${out}/${phase}-history.png`,fullPage:true})
  facts.screens.push({name:`${phase}-history`,text:await page.locator('body').innerText()})
  await page.getByTestId('fbs-supply-history').getByRole('button',{name:'Закрыть',exact:true}).first().click()
  await page.getByRole('button',{name:'Закрыть',exact:true}).click()
  await page.getByTestId('fixture-reopen').click()
  await page.getByText('Состав поставки',{exact:true}).waitFor()
  await page.screenshot({path:`${out}/${phase}-reopen.png`,fullPage:true})
  facts.screens.push({name:`${phase}-reopen`,text:await page.locator('body').innerText()})
  await page.reload()
  await page.getByText('Состав поставки',{exact:true}).waitFor()
  await page.screenshot({path:`${out}/${phase}-refresh.png`,fullPage:true})
  facts.screens.push({name:`${phase}-refresh`,text:await page.locator('body').innerText()})
 }
} finally {
 await page.screenshot({path:`${out}/last-state.png`,fullPage:true}).catch(()=>{})
 facts.lastText=await page.locator('body').innerText().catch(()=>'')
 fs.writeFileSync(`${out}/facts.json`,JSON.stringify(facts,null,2))
 await browser.close()
}
