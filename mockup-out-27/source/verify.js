const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {JSDOM,VirtualConsole} = require('/Users/deniscivkunov/Projects/WMS/frontend/node_modules/jsdom');
const out = path.resolve(__dirname,'..');
let checked=0;
const cases=[['M / 46–48','Молочный'],['L / 50–52','Графитовый'],['Универсальный (российский 42–54)','Серо-зелёный меланж с контрастной отделкой цвета слоновой кости'],['—','Песочный'],['39–42','—'],['—','—']];
for(const form of ['fbo','outbound','receiving','inbound','packaging']) for(const variant of ['inline','columns']) for(const count of ['short','long']) {
  const file=`${variant}-${form}-${count}.html`;
  const doc=new JSDOM(fs.readFileSync(path.join(out,'documents',file),'utf8')).window.document;
  const before=new JSDOM(fs.readFileSync(path.join(out,'documents',`current-${form}-${count}.html`),'utf8')).window.document;
  assert.equal(doc.querySelector('h1').textContent,before.querySelector('h1').textContent);
  assert.equal(doc.querySelector('dl').textContent,before.querySelector('dl').textContent);
  const rows=[...doc.querySelectorAll('tbody tr')],original=[...before.querySelectorAll('tbody tr')];
  assert.equal(rows.length,count==='short'?6:36);
  rows.forEach((row,i)=>{
    assert.equal(row.dataset.sku,original[i].dataset.sku);
    assert.equal(row.cells.length,doc.querySelectorAll('thead th').length);
    const fields=variant==='columns'?[...row.querySelectorAll('.variant-size,.variant-color')].map(el=>el.textContent):[...row.querySelectorAll('.variant-attributes>div')].map(el=>el.textContent.replace(/^(Размер|Цвет): /,''));
    assert.deepEqual(fields,cases[i%6]);
    const copy=row.cloneNode(true);
    copy.querySelectorAll('.variant-attributes,.variant-size,.variant-color').forEach(el=>el.remove());
    assert.equal(copy.textContent,original[i].textContent,'original row fields remain exact');
  });
  assert.match(doc.querySelector('style:last-of-type').textContent,/overflow-wrap:anywhere/);
  assert.match(doc.querySelector('style:last-of-type').textContent,/break-inside:avoid/);
  checked++;
}
const sleep = ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  const interactions=[];
  for(const file of ['index.html','variant-inline.html','variant-columns.html']) {
    const errors=[];
    const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(e.type!=='css parsing')errors.push(e.message)});
    const dom=await JSDOM.fromFile(path.join(out,file),{resources:'usable',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc});
    await sleep(350);
    const doc=dom.window.document;
    assert.equal(errors.length,0,errors.join('\n'));
    for(const el of doc.querySelectorAll('a[href]')) assert.ok(fs.existsSync(path.resolve(out,el.getAttribute('href'))),'relative link exists');
    if(file==='index.html') assert.equal([...doc.querySelectorAll('a')].filter(el=>el.textContent.includes('Открыть вариант')).length,2);
    else {
      const tab=[...doc.querySelectorAll('[role="tab"]')].find(el=>el.textContent==='Отгрузка со склада');
      tab.click();await sleep(80);
      assert.match(doc.querySelector('iframe').getAttribute('src'),/outbound-short/);
      const current=[...doc.querySelectorAll('button')].find(el=>el.textContent==='Текущая форма');
      current.click();await sleep(80);
      assert.match(doc.querySelector('iframe').getAttribute('src'),/current-outbound/);
      [...doc.querySelectorAll('button')].find(el=>el.textContent==='Вернуться к макету').click();await sleep(80);
      assert.ok(!doc.querySelector('iframe').getAttribute('src').includes('current'));
      let printed=false;
      const frame=doc.querySelector('iframe');frame.contentWindow.focus=()=>{};frame.contentWindow.print=()=>{printed=true};
      [...doc.querySelectorAll('button')].find(el=>el.textContent.includes('Печать')).click();
      assert.ok(printed,'print targets selected document');
      interactions.push(`${file}: form switch, before/after and selected-document print`);
    }
    dom.window.close();
  }
  const report={documentChecks:checked,interactions,status:'passed',browserVisualCheck:'not performed: Chromium cannot launch in sandbox',physicalPrinting:'not performed',scope:'synthetic mockups only'};
  fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1});
