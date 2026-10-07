import type { PackingScanController } from '../../../reference-frontend/src/screens/v2/fbsSequentialPacking'
import type { FbsKizLookup, FbsWorkspace } from '../../../reference-frontend/src/screens/v2/fbsApi'
import { loadFbsScanPrintPreferences, type FbsScanPrintPreferences } from '../../../reference-frontend/src/screens/v2/fbsScanAutoPrint'
import { bindDemoKiz, getWorkspace, markPrinted, setPacked } from './mockApi'
import { log } from './state'
type DemoPending = {order:FbsWorkspace['orders'][number];explicit:boolean;preferences:FbsScanPrintPreferences}
export function makeDemoController(read:()=>FbsWorkspace, changed:()=>void, refresh:()=>void, token:string, selected:(id:string)=>void): PackingScanController {
 let pending:DemoPending|null=null
 const boundCodes=new Map<string,string>()
 const finish=async(order:FbsWorkspace['orders'][number],explicit:boolean,prefs:FbsScanPrintPreferences,rawKiz?:string)=>{
   const ws=getWorkspace(read().supply.id)
   const pool=ws.supply.marketplace==='wb'&&!explicit&&!rawKiz&&prefs.printChz&&!ws.supply.honest_sign_skipped
   if(pool&&order.id.endsWith('-3')&&!order.metadata.states.length)throw Error('В этой демонстрационной строке нет доступного КИЗ из пула')
   if(rawKiz){bindDemoKiz(ws.supply.id,order.id,rawKiz);boundCodes.set(rawKiz,order.id)}
   const labels=[...(prefs.printQr&&ws.supply.marketplace==='wb'?['QR']:[]),...(pool?['ЧЗ из пула']:[]),...(ws.supply.marketplace==='wb'&&prefs.reprintChz&&rawKiz?['Точная копия КИЗ']:[])]
   log('Скан · демонстрационные действия',{supply:ws.supply.id,seller:ws.supply.seller.name,order:order.id,source:explicit?'стикер / конкретная строка':'штрихкод товара',kiz:rawKiz??null,labels,pack:1})
   // Binding and an exact copy use the operator code; only a WB product scan
   // may allocate a demo pool code. Ozon never allocates that pool.
   markPrinted(ws.supply.id,[order.id],labels.map(label=>label==='ЧЗ из пула'?'ЧЗ':label))
   setPacked(ws.supply.id,[order.id]);pending=null;selected(order.id);changed();refresh()
 }
 const pick=async(raw:string)=>{
   const ws=getWorkspace(read().supply.id),prefs=loadFbsScanPrintPreferences(token)
   if(pending){
     if(!raw.startsWith('01'))throw Error('Для выбранного заказа введите демонстрационный КИЗ, начинающийся с 01')
     await finish(pending.order,pending.explicit,pending.preferences,raw);return
   }
   if(ws.supply.marketplace==='wb'&&raw.startsWith('01')&&prefs.reprintChz){
     const orderId=boundCodes.get(raw)
     if(!orderId)throw Error('Точная копия в демо доступна только для КИЗ, ранее внесённого здесь; используйте штатную перепечатку в строке')
     log('Точная перепечать сохранённого входного КИЗ',{supply:ws.supply.id,seller:ws.supply.seller.name,order:orderId,kiz:raw,labels:['ЧЗ']});return
   }
   const explicit=ws.orders.find(order=>order.sticker.code===raw||String(order.wb_order_id)===raw||order.external_order_id===raw)
   const product=ws.orders.find(order=>order.pack.status!=='packed'&&order.product.barcode===raw)
   if(ws.supply.marketplace==='wb'&&!explicit&&product&&!(prefs.printQr||prefs.printChz||prefs.reprintChz)){
     log('Скан товара пропущен: все флажки выключены',{supply:ws.supply.id,seller:ws.supply.seller.name,barcode:raw});return
   }
   const order=explicit??product
   if(!order)throw Error('В демонстрационной поставке нет подходящего заказа с таким кодом')
   selected(order.id)
   const needs=!ws.supply.honest_sign_skipped&&!order.metadata.states.some(state=>state.status==='accepted')
   const mayUsePool=ws.supply.marketplace==='wb'&&!explicit&&prefs.printChz
   if(needs&&!mayUsePool){pending={order,explicit:Boolean(explicit),preferences:prefs};log('Выбран заказ · ожидается КИЗ оператора',{supply:ws.supply.id,seller:ws.supply.seller.name,order:order.id,source:explicit?'стикер':'товар'});changed();return}
   await finish(order,Boolean(explicit),prefs)
 }
 return {
   matches:raw=>read().orders.some(order=>order.product.barcode===raw||order.sticker.code===raw||String(order.wb_order_id)===raw||order.external_order_id===raw),
   scan:pick,
   scanOrder:async(id,raw)=>{
     const order=getWorkspace(read().supply.id).orders.find(order=>order.id===id)
     if(!order)throw Error('Заказ другой поставки')
     pending={order,explicit:true,preferences:loadFbsScanPrintPreferences(token)};await pick(raw)
   },
   hasPending:()=>Boolean(pending),hasSavedAttempt:()=>false,
   view:()=>pending?{orderId:pending.order.id,name:pending.order.product.name,needsKiz:true,target:{order_id:pending.order.id,wb_order_id:pending.order.wb_order_id,product:pending.order.product,current_kiz:null,needs_confirmation:false,can_bind:true,block_reason:null} as FbsKizLookup}:null,
   // A partial imitation of undo would claim a warehouse reversal that never
   // happened. The demo disables Back and states this in its service panel.
   lastStep:()=>null,canCancel:()=>Boolean(pending),cancel:async()=>{pending=null;changed();return true},
 }
}
