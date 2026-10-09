const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = path.resolve(__dirname, '../..');
const out = path.resolve(__dirname, '..');
const deps = '/Users/deniscivkunov/Projects/WMS/frontend/node_modules';
const esbuild = require(path.join(deps, 'esbuild'));
const { JSDOM } = require(path.join(deps, 'jsdom'));
const readTs = (relative) => {
  const filename = path.join(root, relative);
  const result = esbuild.buildSync({entryPoints:[filename], bundle:true, platform:'node', format:'cjs', write:false, nodePaths:[deps]});
  const mod = new Module(filename); mod.paths = [deps]; mod._compile(result.outputFiles[0].text, filename);
  return mod.exports;
};
const waybill = readTs('frontend/src/utils/printShipmentWaybill.ts');
const receiving = readTs('frontend/src/utils/printInboundReceivingSheet.ts');
const packaging = readTs('frontend/src/utils/printShipmentPackagingSheet.ts');
const items = [
  {sku_code:'DEMO-100101', vendor_code:'DEMO-TEE-01', product_name:'Футболка базовая из хлопка', size:'M / 46–48', color:'Молочный', quantity:24},
  {sku_code:'DEMO-100102', vendor_code:'DEMO-TEE-01', product_name:'Футболка базовая из хлопка', size:'L / 50–52', color:'Графитовый', quantity:18},
  {sku_code:'DEMO-100103', vendor_code:'DEMO-CARD-02', product_name:'Кардиган свободного кроя с удлинёнными рукавами и контрастной отделкой', size:'Универсальный (российский 42–54)', color:'Серо-зелёный меланж с контрастной отделкой цвета слоновой кости', quantity:12},
  {sku_code:'DEMO-100104', vendor_code:'DEMO-BAG-03', product_name:'Сумка тканевая с внутренним карманом', size:null, color:'Песочный', quantity:10},
  {sku_code:'DEMO-100105', vendor_code:'DEMO-SOCK-04', product_name:'Носки хлопковые, комплект из трёх пар', size:'39–42', color:null, quantity:8},
  {sku_code:'DEMO-100106', vendor_code:'DEMO-BOX-05', product_name:'Органайзер для хранения вещей', size:null, color:null, quantity:20},
].map((row,i)=>({...row, barcode:`20000000000${String(i+1).padStart(2,'0')}`, wb_nm_id:900000001+i, photo_url:null, instructions:i===2?'Сложить аккуратно. Упаковать в прозрачный пакет, не перекрывать этикетку.':'Упаковать в прозрачный пакет.', expected_qty:row.quantity, shipped_qty:row.quantity, received_qty:row.quantity, storage_location_code:`A-01-0${i+1}`}));
const forms = [
  {id:'fbo', label:'FBO · Wildberries', kind:'marketplace_unload'},
  {id:'outbound', label:'Отгрузка со склада', kind:'operational_outbound'},
  {id:'receiving', label:'Приёмка · лист', kind:'receiving'},
  {id:'inbound', label:'Приёмка · накладная', kind:'inbound_intake'},
  {id:'packaging', label:'Упаковка · лист отгрузки', kind:'packaging'},
];
fs.mkdirSync(path.join(out,'documents'),{recursive:true});
function baseline(form, lines) {
  const common = {warehouseName:'Учебный склад (DEMO)', sellerName:'Демо-селлер «Образец»', plannedDate:'06.10.2026', createdAt:'06.10.2026 09:30'};
  if(form.kind==='receiving') return receiving.buildInboundReceivingSheetHtml({...common,documentNumber:'ДЕМО-ПР-0027',items:lines});
  if(form.kind==='packaging') return packaging.buildShipmentPackagingSheetHtml({...common,documentNumber:'ДЕМО-ОТ-0027',documentType:'Отгрузка FBO · Wildberries',shipmentDate:'06.10.2026',marketplaceWarehouseName:'Учебный склад WB',items:lines});
  global.window = {__WMS_CAPTURE_PRINT_HTML__:true};
  global.document = {createElement:()=>({setAttribute(){},style:{}}),body:{appendChild(){}}};
  waybill.printShipmentWaybill({...common, docKind:form.kind, documentId:'00000027-0000-4000-8000-000000000027',documentNumber:'ДЕМО-ПР-0027',waybillNumber:'ДЕМО-НК-0027',documentTypeLabel:'Поставка',statusLabel:'Собрана',wbWarehouseLabel:'Учебный склад WB',plannedBoxCount:4,actualBoxCount:4,lines});
  return global.window.__WMS_LAST_PRINT_HTML__;
}
function decorate(html, form, variant, lines) {
  const document = new JSDOM(html).window.document;
  const table = document.querySelector('table');
  table.classList.add('invoice-table');
  const head = table.tHead.rows[0];
  const isPhoto = ['receiving','packaging'].includes(form.kind);
  const productIndex = isPhoto?1:form.kind==='inbound_intake'?0:2;
  const rows = [...table.tBodies[0].rows];
  const text = v => v?.trim() || '—';
  if(variant==='current') {
    rows.forEach((row,i)=>{row.dataset.sku=lines[i].sku_code});
    const screen=document.createElement('style');
    screen.textContent=`@media screen { * { box-sizing:border-box; } html { background:#e8ecf4; } body { width:210mm; min-height:297mm; margin:12px auto; padding:${isPhoto?'7mm 8mm 8mm':'12mm'}; background:white; box-shadow:0 2px 8px #0f172a18; } }`;
    document.head.append(screen);
    return '<!doctype html>\n'+document.documentElement.outerHTML;
  }
  if(variant==='columns') {
    for(const [offset,label] of ['Размер','Цвет'].entries()) {
      const cell = document.createElement('th'); cell.textContent=label; cell.className=offset?'variant-color':'variant-size';
      head.insertBefore(cell,head.children[productIndex+1+offset]);
    }
  }
  rows.forEach((row,i)=>{
    row.dataset.sku=lines[i].sku_code;
    if(variant==='inline') {
      const attributes=document.createElement('div'); attributes.className='variant-attributes';
      for(const [label,value] of [['Размер',lines[i].size],['Цвет',lines[i].color]]) {
        const field=document.createElement('div'); const caption=document.createElement('span');
        caption.className='attribute-label';caption.textContent=`${label}: `;
        field.append(caption,document.createTextNode(text(value)));attributes.append(field);
      }
      row.cells[productIndex].append(attributes);
    } else if(variant==='columns') {
      for(const [offset,value] of [lines[i].size,lines[i].color].entries()) {
        const cell=document.createElement('td');cell.textContent=text(value);cell.className=offset?'variant-color':'variant-size';
        row.insertBefore(cell,row.children[productIndex+1+offset]);
      }
    }
  });
  // Keep the original fields and grid; distribute new columns only inside the prototype.
  const widths = variant==='columns'
    ? isPhoto ? form.kind==='packaging'?[9,22,12,15,14,6,16,6]:[10,27,13,19,17,7,7]
      :form.kind==='operational_outbound'?[4,15,23,12,17,12,8,9]
      :form.kind==='inbound_intake'?[34,14,22,9,9,12]:[4,18,32,14,22,10]
    :isPhoto ? form.kind==='packaging'?[12,33,15,7,24,9]:[13,46,21,10,10]
      :form.kind==='operational_outbound'?[4,18,40,18,10,10]
      :form.kind==='inbound_intake'?[58,12,12,18]:[4,20,64,12];
  const colgroup=document.createElement('colgroup');
  widths.forEach(width=>{const col=document.createElement('col');col.style.width=`${width}%`;colgroup.append(col)});
  table.prepend(colgroup);
  const style=document.createElement('style');
  style.textContent=`
    @page { size: A4; margin: ${isPhoto?'7mm 8mm 8mm':'12mm'}; }
    * { box-sizing: border-box; }
    body { margin:0; line-height:1.4; font-variant-numeric:tabular-nums; }
    @media screen { html { background:#e8ecf4; } body { width:210mm; min-height:297mm; padding:${isPhoto?'7mm 8mm 8mm':'12mm'}; margin:12px auto; background:white; box-shadow:0 2px 8px #0f172a18; } }
    .invoice-table { table-layout:fixed; }
    .invoice-table th,.invoice-table td { width:auto; vertical-align:top; overflow-wrap:anywhere; white-space:normal; }
    .invoice-table th { line-height:1.3; }
    thead { display:table-header-group; }
    tr { break-inside:avoid; page-break-inside:avoid; }
    .variant-attributes { margin-top:6px; line-height:1.45; }
    .attribute-label { font-weight:600; }
    .variant-size,.variant-color { font-size:inherit; line-height:1.45; }
    .rs-photo,.pk-photo { max-width:100%; height:19mm; }
    .rs-meta,.pk-meta { font-size:9px; }
    @media print { html,body { width:auto; min-height:0; padding:0; margin:0; background:#fff; box-shadow:none; } }
  `;
  document.head.append(style);
  document.title=`${document.title} · ${variant==='columns'?'Размер и цвет в колонках':variant==='inline'?'Размер и цвет под товаром':'Текущая форма'} · Демо`;
  return '<!doctype html>\n'+document.documentElement.outerHTML;
}
for(const form of forms) for(const variant of ['current','inline','columns']) for(const count of ['short','long']) {
  const lines=count==='long'?Array.from({length:36},(_,i)=>({...items[i%6],sku_code:`DEMO-${100101+i}`})):items;
  fs.writeFileSync(path.join(out,'documents',`${variant}-${form.id}-${count}.html`),decorate(baseline(form,lines),form,variant,lines).replace(/[ \t]+$/gm,'')+'\n');
}
fs.writeFileSync(path.join(__dirname,'forms.json'),JSON.stringify(forms,null,2));
esbuild.buildSync({entryPoints:[path.join(__dirname,'app.js')],outfile:path.join(out,'assets','app.js'),bundle:true,minify:true,format:'iife',jsx:'automatic',loader:{'.js':'jsx'},nodePaths:[deps],define:{'process.env.NODE_ENV':'"production"','import.meta.env.DEV':'false'},legalComments:'none'});
console.log('Built two variants, five existing document forms, short and multipage samples.');
