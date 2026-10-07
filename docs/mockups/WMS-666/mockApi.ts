import { workspace as makeWorkspace } from './fixtureBase.mjs'
import type { FbsWorkspace } from '../../../reference-frontend/src/screens/v2/fbsApi'
import { emit, log } from './state'
export const ids=['demo-supply-a','demo-supply-b']
let current: Record<string,FbsWorkspace>={}
export function reset(marketplace:'wb'|'ozon'='wb') {
  current=Object.fromEntries(ids.map((id,index)=>{
    const ws=makeWorkspace(id,marketplace) as FbsWorkspace
    const base=ws.orders[0]
    ws.supply.name=index?'Осенняя поставка · заказы селлера с очень длинным названием для проверки переносов и читаемости':'Основная поставка · утренняя смена'
    ws.supply.seller={id:`demo-seller-${index+1}`,name:index?'Селлер Бета':'Селлер Альфа'}
    ws.orders=Array.from({length:3},(_,n)=>{
      const order=structuredClone(base)
      order.seller={...ws.supply.seller}
      order.id=`${id}-order-${n+1}`;order.wb_order_id=731001+index*100+n
      order.external_order_id=marketplace==='ozon'?`OZON-DEMO-${index+1}-${n+1}`:null
      order.sticker.code=marketplace==='wb'?`${order.wb_order_id} ${String(n+1).padStart(4,'0')}`:order.external_order_id
      order.product.id=`${id}-product-${n+1}`;order.product.name=n===2?'Футболка хлопковая с удлинённым названием, размер Универсальный, индивидуальная комплектация':'Футболка хлопковая'
      order.product.sku=`DEMO-SKU-${index+1}-${n+1}`;order.product.barcode=`DEMO-${index+1}-${n+1}`;order.product.seller_article=`ART-${index+1}-${n+1}`
      order.product.size=n===2?'Универсальный':'M';order.product.marketplace_bindings=[{marketplace,external_barcodes:[order.product.barcode!]}]
      order.metadata.required=['sgtin'];order.metadata.delivery_allowed=n===0
      order.metadata.states=n===0?[{id:`mark-${order.id}`,kind:'sgtin',status:'accepted',value_tail:`…DEMO-${index+1}-${n+1}`,source:'operator',reason:null}]:[]
      if(n===0){order.sticker.applied_at='2026-10-07T10:00:00Z';order.sticker.status='applied';order.pack.status='packed'}
      if(marketplace==='ozon') order.positions=[{...order.positions[0],id:`pos-${order.id}`,product_id:order.product.id,name:order.product.name,sku:order.product.sku,seller_article:order.product.seller_article,barcode:order.product.barcode,marketplace_bindings:order.product.marketplace_bindings,quantity:1,picked_quantity:1}]
      return order
    })
    ws.progress={...ws.progress,total:3,picked:3,packed:1,metadata_ready:1,stickers_ready:3}
    ws.stage='packing';return[id,ws]
  }))
  emit()
}
export function getWorkspace(id:string) {const ws=current[id];if(!ws)throw Error('Неизвестная демонстрационная поставка '+id);return structuredClone(ws)}
export function setPacked(id:string,orderIds:string[]) {
  const ws=current[id];for(const order of ws.orders)if(orderIds.includes(order.id))order.pack.status='packed'
  ws.progress.packed=ws.orders.filter(order=>order.pack.status==='packed').length;emit()
}
export function markPrinted(id:string,orderIds:string[],labels:string[]) {
  const ws=current[id];for(const order of ws.orders)if(orderIds.includes(order.id)){
    if(labels.includes('QR')){order.sticker.status='applied';order.sticker.applied_at=new Date().toISOString()}
    if(ws.supply.marketplace==='wb'&&labels.includes('ЧЗ')&&!order.metadata.states.length)order.metadata.states=[{id:`mark-${order.id}`,kind:'sgtin',status:'accepted',source:'pool',value_tail:`…POOL-${order.id.slice(-1)}`,reason:null}]
    order.metadata.delivery_allowed=Boolean(ws.supply.honest_sign_skipped)||order.metadata.states.some(state=>state.status==='accepted')
  }
  log('Демонстрация печати · физической печати нет',{supply:id,seller:ws.supply.seller.name,orders:orderIds,labels});emit()
}
export function bindDemoKiz(id:string,orderId:string,raw:string) {
  const ws=current[id],order=ws.orders.find(order=>order.id===orderId)
  if(!order)throw Error('Заказ другой поставки')
  order.metadata.states=[{id:`mark-${order.id}`,kind:'sgtin',status:'accepted',source:'operator',value_tail:raw.slice(-8),reason:null}]
  order.metadata.delivery_allowed=true
  log('Демонстрационная привязка входного КИЗ',{supply:id,seller:ws.supply.seller.name,order:orderId,kiz:raw});emit()
}
function task(id:string) {
  const ws=current[id]
  return {id:ws.supply.packaging_task_id,status:'in_progress',document_number:'666',display_number:'666',seller_id:ws.supply.seller.id,warehouse_id:ws.supply.wms_warehouse.id,is_complete:false,events:[],lines:ws.orders.map((order,n)=>({
    id:`line-${order.id}`,product_id:order.product.id,sku_code:order.product.sku,product_name:order.product.name,seller_id:ws.supply.seller.id,seller_name:ws.supply.seller.name,
    packaging_instructions:'Проверить размер и артикул. Сложить, упаковать в прозрачный пакет, наклеить этикетку.',requires_honest_sign:!ws.supply.honest_sign_skipped,qty_total:1,qty_need_pack:1,qty_done:order.pack.status==='packed'?1:0,qty_packed_in_task:order.pack.status==='packed'?1:0,qty_confirmed_packed:order.pack.status==='packed'?1:0,qty_suggested_packed:0,qty_marking_printed:n===0?1:0,qty_marking_external:n===0?1:0,qty_product_label_printed:n===0?1:0,marking_available_count:n===2?0:2,is_complete:order.pack.status==='packed'
  }))}
}
const json=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}})
export function installMockApi(){
 reset()
 globalThis.fetch=async(input,init)=>{
  const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,location.origin)
  const method=(init?.method??(input instanceof Request?input.method:'GET')).toUpperCase()
  const path=url.pathname.replace(/^\/api/,'')
  if(url.origin!==location.origin){log('Заблокирован внешний запрос',{url:url.origin+url.pathname});return json({detail:'Внешние запросы запрещены в макете'},403)}
  const body=init?.body?JSON.parse(String(init.body)):{}
  const match=path.match(/^\/operations\/fbs-supplies\/([^/]+)\/(.+)$/)
  if(match&&current[match[1]]){
    const[,id,action]=match
    if(method==='POST'&&action==='print-assets'){
      const chosen=current[id].orders.filter(order=>body.order_ids?.includes(order.id))
      log('Открыт штатный предпросмотр QR',{supply:id,seller:current[id].supply.seller.name,orders:chosen.map(order=>order.id),labels:['QR']})
      return json({requested:chosen.length,ready:chosen.length,missing:0,failed:0,order_errors:[],assets:chosen.map(order=>({id:`qr-${order.id}`,kind:'order_sticker',status:'ready',content_type:'image/svg+xml',width_mm:58,height_mm:40,preview_url:`/demo-assets/${order.id}.svg`,download_url:null,checksum:null,applied_at:order.sticker.applied_at,error:null}))})
    }
    if(method==='GET'&&action==='workspace')return json(getWorkspace(id))
    if(method==='POST'&&action==='markings/sync'){log('Проверить в WB · только указанная поставка',{supply:id,seller:current[id].supply.seller.name,orders:current[id].orders.map(order=>order.id)});return json(getWorkspace(id))}
    if(method==='POST'&&action==='honest-sign-skip'){current[id].supply.honest_sign_skipped=true;log('Сдать без Честного знака · вся поставка',{supply:id,seller:current[id].supply.seller.name,orders:current[id].orders.map(order=>order.id)});return json(getWorkspace(id))}
    if(method==='POST'&&action==='start-work')return json(getWorkspace(id))
    if(method==='POST'&&action==='transfer-orders'){
      const target=body.target_supply_id
      if(!target||!current[target]||target===id||current[target].supply.seller.id!==current[id].supply.seller.id)return json({detail:'В макете выберите вторую демонстрационную поставку; новая поставка не создаётся'},400)
      const moved=current[id].orders.filter(order=>body.order_ids?.includes(order.id))
      if(moved.length!==body.order_ids?.length)return json({detail:'Выбран заказ другой исходной поставки'},400)
      current[id].orders=current[id].orders.filter(order=>!body.order_ids.includes(order.id))
      current[target].orders.push(...moved.map(order=>({...order,supply_id:target})))
      for(const changedId of [id,target]){current[changedId].progress.total=current[changedId].orders.length;current[changedId].progress.picked=current[changedId].orders.length;current[changedId].progress.packed=current[changedId].orders.filter(order=>order.pack.status==='packed').length}
      log('Перенести выбранные · одна исходная поставка',{source:id,seller:current[id].supply.seller.name,target,orders:body.order_ids});window.dispatchEvent(new Event('wms666-refresh'))
      return json({target_supply_id:target,target_supply_name:current[target].supply.name,target_wb_supply_id:current[target].supply.wb_supply_id,target_created:false,transferred_order_ids:body.order_ids,pending_order_ids:[],failed_order_ids:[],state:'confirmed',message:'Демонстрационный перенос сохранён в памяти.'})
    }
    if(method==='GET'&&action==='transfer-targets')return json(ids.filter(other=>other!==id&&current[other].supply.seller.id===current[id].supply.seller.id).map(other=>({id:other,supply_id:other,name:current[other].supply.name,wb_supply_id:current[other].supply.wb_supply_id,status:'assembling',created_at:'2026-10-07T08:00:00Z'})))
    if(method==='POST'&&action==='order-print-tape'){
      const chosen=current[id].orders.filter(order=>body.order_ids?.includes(order.id));if(chosen.length!==body.order_ids?.length)return json({detail:'Запрещена печать заказа другой поставки'},400)
      const labels=[...(body.include_order_qr?['QR']:[]),...(body.layout_json?.units?.some((unit:{block:string;copies:number})=>unit.block==='cz'&&unit.copies>0)?['ЧЗ']:[]),...(body.layout_json?.units?.some((unit:{block:string;copies:number})=>unit.block==='label'&&unit.copies>0)?['ШК']:[])];log('Ручной transport: точная область запроса',{supply:id,seller:current[id].supply.seller.name,orders:body.order_ids,includeOrderQr:body.include_order_qr,reprint:body.reprint,exactMarkingIds:body.reprint_marking_ids});markPrinted(id,body.order_ids,labels)
      return json({orders:[],codes:[],printed_codes:[],qr_assets:[],order_errors:[],shortage:0,printed_count:chosen.length,requires_honest_sign:true,layout:body.layout_json})
    }
  }
  const tm=path.match(/^\/operations\/packaging-tasks\/task-(demo-supply-[ab])(?:\/(.+))?$/)
  if(tm&&current[tm[1]]){
    const id=tm[1];if(method==='GET')return json(task(id))
    if(tm[2]==='pack-all-and-complete'){setPacked(id,current[id].orders.map(order=>order.id));log('Всё упаковано · вся поставка',{supply:id,seller:current[id].supply.seller.name,orders:current[id].orders.map(order=>order.id)});return json({packaging_task:task(id),warnings:[]})}
  }
  const applied=path.match(/^\/operations\/fbs-print-assets\/qr-(.+)\/applied$/)
  if(applied&&method==='POST'){
    const owner=ids.find(id=>current[id].orders.some(order=>order.id===applied[1]))
    if(!owner)return json({detail:'Демонстрационная этикетка не найдена'},404)
    markPrinted(owner,[applied[1]],['QR']);return json({applied:true})
  }
  const clear=path.match(/^\/operations\/fbs-orders\/(.+)\/kiz$/)
  if(clear&&method==='DELETE'){
    const owner=ids.find(id=>current[id].orders.some(order=>order.id===clear[1]))
    if(!owner)return json({detail:'Демонстрационный заказ не найден'},404)
    const order=current[owner].orders.find(order=>order.id===clear[1])!;order.metadata.states=[];order.metadata.delivery_allowed=false
    log('Очистить ЧЗ выбранного заказа',{supply:owner,seller:current[owner].supply.seller.name,order:order.id});return json({deleted:true})
  }
  if(path==='/products/linked-wb-catalog')return json(Object.values(current).flatMap(ws=>ws.orders.map(order=>({id:order.product.id,name:order.product.name,sku_code:order.product.sku,wb_primary_barcode:order.product.barcode,wb_barcodes:[order.product.barcode],wb_vendor_code:order.product.seller_article,wb_size:order.product.size,wb_nm_id:null,wb_primary_image_url:null,marketplace_bindings:order.product.marketplace_bindings}))))
  if(path.startsWith('/demo-assets/')){
    const label=path.split('/').pop()?.replace('.svg','')??'DEMO'
    return new Response(`<svg xmlns="http://www.w3.org/2000/svg" width="580" height="400"><rect width="580" height="400" fill="white"/><path d="M40 40h110v110H40zM180 40h110v110H180zM40 180h110v110H40z" fill="black"/><text x="330" y="85" font-size="26">DEMO QR</text><text x="30" y="355" font-size="18">${label}</text></svg>`,{headers:{'Content-Type':'image/svg+xml'}})
  }
  if(path.includes('/print-templates')&&method==='GET')return json({id:null,name:'Демо: ЧЗ + ШК',seller_id:null,product_id:null,user_id:null,is_default:true,is_system:true,layout:{units:[{block:'cz',copies:1},{block:'label',copies:1}]}})
  if(path==='/auth/me')return json({separate_marking_print_enabled:false})
  if(path.includes('separate-marking'))return json({enabled:false})
  if(path.includes('/marking-codes/packaging-task-lines/')&&path.endsWith('/printed-codes'))return json([])
  log('Нереализованный запрос заблокирован',{method,path});return json({detail:'Это локальный макет; действие ещё не моделируется'},400)
 }
 window.print=()=>log('Физическая печать заблокирована')
 window.open=()=>{log('Внешнее окно/печать заблокированы');return null}
}
export function demoQr(id:string,orderIds:string[]) {markPrinted(id,orderIds,['QR']);window.dispatchEvent(new Event('wms666-refresh'))}
