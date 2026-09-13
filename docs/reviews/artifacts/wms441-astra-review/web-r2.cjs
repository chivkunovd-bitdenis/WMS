// Actual React screen, private ephemeral Vite, intercepted synthetic HTTP only.
const path = require('node:path');
const fs = require('node:fs');
const { createRequire } = require('node:module');
const { chromium } = require('playwright');
const frontend = path.resolve(__dirname, '../../../..', 'frontend');
const localRequire = createRequire(path.join(frontend, 'package.json'));

(async () => {
  const { createServer } = await import(localRequire.resolve('vite'));
  const react = (await import(localRequire.resolve('@vitejs/plugin-react'))).default;
  const entry = `import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {MemoryRouter} from 'react-router-dom';
    import {FfSortingObjectsPage} from '/src/screens/ff/sorting-objects/FfSortingObjectsPage.tsx';
    const token='x.'+btoa(JSON.stringify({sub:'review441'}))+'.x';
    createRoot(document.getElementById('root')).render(React.createElement(MemoryRouter,null,
      React.createElement(FfSortingObjectsPage,{token, warehouses:[{id:'W',name:'Review'}],embedded:true,inboundRequestId:'D'})));`;
  const server = await createServer({root:frontend,configFile:false,server:{host:'127.0.0.1',port:0},
    plugins:[react(),{name:'review-harness',resolveId(id){if(id==='/review-entry')return '\0review-entry';},
      load(id){if(id==='\0review-entry')return entry;},
      configureServer(s){s.middlewares.use(async(req,res,next)=>{if(req.url?.split('?')[0]!=='/review441')return next();
        const html=await s.transformIndexHtml('/review441','<div id="root"></div><script type="module" src="/review-entry"></script>');
        res.setHeader('Content-Type','text/html');res.end(html);});}}]});
  await server.listen();
  const port=server.httpServer.address().port;
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  try {
    const page=await browser.newPage({viewport:{width:1400,height:1000}});
    let committed=false, failedGet=false; const posts=[];
    const fixture=()=>({objects:[{id:'cargo',kind:'cargo_place',code:'C1',barcode:'CARGO',holder:null}],
      lines:[{id:'balance',productId:'P',qty:committed?2:3,holder:'obj:cargo'},
        ...(committed?[{id:'placed',productId:'P',qty:1,holder:'cell:A'}]:[])],
      products:[{id:'P',name:'Review product',sku:'P1',seller:'Review seller',barcode:'123',photo:'',size:null,alreadyAt:[]}],
      cells:[{id:'A',code:'Review A',barcode:'AAA'}]});
    await page.route('**/api/**',async(route)=>{
      if(route.request().method()==='POST'){
        posts.push(route.request().postDataJSON());committed=true;failedGet=true;
        await route.abort('failed');return;
      }
      if(failedGet){await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"review failed GET"}'});return;}
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixture())});
    });
    await page.goto(`http://127.0.0.1:${port}/review441`);
    await page.getByText('Review product',{exact:true}).waitFor();
    const out=page.locator('[data-testid^="objects-tree-out-"]').last();
    await out.click();
    const target=page.getByTestId('objects-target');
    await target.selectOption('cell:A');
    await page.getByTestId('objects-qty-input').fill('1');
    await page.getByTestId('objects-qty-confirm').click();
    await page.getByTestId('sorting-objects-error').waitFor();
    await page.getByText('Загружаем склад',{exact:true}).waitFor();
    const failedState={postCount:posts.length,body:posts[0],
      error:await page.getByTestId('sorting-objects-error').innerText(),
      workTreeCount:await page.getByTestId('objects-tree').count(),
      pendingKeys:await page.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('wms:sorting-placement:')))};
    await page.screenshot({path:path.join(__dirname,'web-r2-failed-get.png'),fullPage:true});
    failedGet=false;
    await page.reload();
    await page.getByText('Review product',{exact:true}).waitFor();
    const recovered={postCount:posts.length,workTree:await page.getByTestId('objects-tree').innerText()};
    await page.screenshot({path:path.join(__dirname,'web-r2-recovered.png'),fullPage:true});
    if(posts.length!==1||failedState.pendingKeys.length!==0||failedState.workTreeCount!==0)throw Error('Unexpected replay or stale actionable data');
    fs.writeFileSync(path.join(__dirname,'web-r2-result.json'),JSON.stringify({failedState,recovered},null,2));
    console.log(JSON.stringify({postCount:posts.length,failedGetHidesWorkingRows:true,pendingKeys:failedState.pendingKeys,reloadRestoresQty:2}));
  } finally {await browser.close();await server.close();}
})().catch(err=>{console.error(err);process.exitCode=1;});
