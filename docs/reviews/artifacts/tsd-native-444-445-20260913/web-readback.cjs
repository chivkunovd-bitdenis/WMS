const {chromium}=require('/Users/deniscivkunov/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');const path=require('path');
(async()=>{
const browser=await chromium.launch({headless:true,channel:"chrome"});const context=await browser.newContext({viewport:{width:1440,height:1100}});
const response=await context.request.post('http://127.0.0.1:5197/api/auth/login-by-name',{data:{full_name:'Final Astra 5da311',organization:'final-review-5da311',password:process.env.WMS_FINAL_PASSWORD}});
if(!response.ok())throw Error('synthetic login HTTP '+response.status());const {access_token}=await response.json();
await context.addInitScript(token=>localStorage.setItem('wms_token_ff',token),access_token);
const page=await context.newPage();const evidence=[];page.on('response',async r=>{if(/\/api\/billing\//.test(r.url())){try{evidence.push({url:r.url(),status:r.status(),body:await r.json()})}catch{}}});
await page.goto('http://127.0.0.1:5197/app/ff/billing');await page.waitForLoadState('networkidle');
await page.getByRole('row').filter({hasText:'Final seller 5da311'}).waitFor();
await page.screenshot({path:path.join(__dirname,'web-billing.png'),fullPage:true});fs.writeFileSync(path.join(__dirname,'web-billing.txt'),await page.locator('body').innerText());
await page.getByTestId('billing-seller-summary-expand-1c4c9d08-2fba-435d-86f6-2c1261230f37').click();
await page.getByTestId('billing-seller-details-1c4c9d08-2fba-435d-86f6-2c1261230f37').waitFor(); await page.getByText('Принято', {exact:true}).last().waitFor();
await page.screenshot({path:path.join(__dirname,'web-details.png'),fullPage:true}); fs.writeFileSync(path.join(__dirname,'web-details.txt'),await page.locator('body').innerText()); console.log((await page.locator('body').innerText()).slice(-5000));
fs.writeFileSync(path.join(__dirname,'web-responses.json'),JSON.stringify(evidence,null,2));await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
