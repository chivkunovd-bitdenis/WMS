import type { Plugin } from 'vite'
import { fileURLToPath } from 'node:url'
const local=(name:string)=>JSON.stringify(fileURLToPath(new URL(name,import.meta.url)))
function once(code:string,needle:string,replacement:string){if(code.split(needle).length!==2)throw Error('WMS666 demo source anchor changed: '+needle.slice(0,90));return code.replace(needle,replacement)}
export function demoTransform():Plugin{return{name:'wms666-isolated-controls',enforce:'pre',transform(code,id){
 if(id.endsWith('/FfFbsSupplyWorkspace.tsx')){
   code=`import {PackingToolbar} from ${local('./Controls.tsx')};\nimport {proposal,register,unregister} from ${local('./state.ts')};\nimport {makeDemoController} from ${local('./demoScanner.ts')};\n`+code
   const start=code.indexOf('    const controller = createPackingScanController(makePackingScanDeps(')
   const end=code.indexOf('    ))\n    return {',start)
   if(start<0||end<0)throw Error('WMS666 scanner anchor changed')
   code=code.slice(0,start)+`    const controller = makeDemoController(()=>sequentialWorkspaceRef.current!,()=>{setSequentialScanVersion(v=>v+1);sequentialFrameRef.current?.onScanChange?.()},()=>sequentialRefreshRef.current(),token,id=>{setRecentlyScannedOrderId(id);sequentialFrameRef.current?.onPromotePackingOrder?.(supplyId!,id)})\n`+code.slice(end+7)
   // Existing Ozon view/controls stay; its demo controller uses no external transports.
   code=once(code,"    if (!isOzonSupply || !supplyId) return null\n    let startPromise", "    if (!isOzonSupply || !supplyId) return null\n    return makeDemoController(()=>sequentialWorkspaceRef.current!,()=>{setSequentialScanVersion(v=>v+1);sequentialFrameRef.current?.onScanChange?.()},()=>sequentialRefreshRef.current(),token,id=>setRecentlyScannedOrderId(id))\n    let startPromise")
   const first=code.indexOf("                  <Box sx={{ px: 2, py: 1.75, borderBottom: 1, borderColor: 'divider' }}>")
   const last=code.indexOf('                  {workspace.marking_pool',first)
   if(first<0||last<0)throw Error('WMS666 toolbar anchor changed')
   const original=code.slice(first,last)
   code=code.slice(0,first)+`                  {proposal ? (!assemblyFrame ? <PackingToolbar supplyIds={[workspace.supply.id]}/> : null) : (<>${original}</>)}\n`+code.slice(last)
   code=once(code,'          {isOzonSupply ? (\n            <Box sx={{ px: 2, py: 1, display:', '          {isOzonSupply && !proposal ? (\n            <Box sx={{ px: 2, py: 1, display:')
   code=once(code,'  const packingPanel = workspace ? (',`  useEffect(() => {if(!workspace)return;register({id:workspace.supply.id,title:workspace.supply.name,seller:workspace.supply.seller.name,busy,editable:packagingEditable,codes:packingOrdersWithCode,clearable:clearableSelectedCount,honestSignSkipped:Boolean(workspace.supply.honest_sign_skipped),skipBusy:skipHonestSignBusy,packAllDisabled:!packagingEditable||busy||(assemblyWbPacking&&!packagingTask),marketplace:workspace.supply.marketplace,orders:fullTapeOrders,selected:packingSelectedIds,printed:printedOrdersCount,packed:workspace.progress.packed,select:setPackingSelectedIds,print:orders=>openBulkOrderMarkingPrint(orders,orders.every(orderPrintDone)),verify:checkMarkingsInWb,packAll:()=>void packEverything(),skip:()=>setSkipHonestSignOpen(true),transfer:()=>setTransferDialogOpen(true),clear:()=>setClearMarkingOrders([...selectedPackingOrders])})})\n  useEffect(()=>()=>{if(supplyId)unregister(supplyId)},[supplyId])\n  useEffect(()=>{const refresh=()=>void load(true);window.addEventListener('wms666-refresh',refresh);return()=>window.removeEventListener('wms666-refresh',refresh)},[load])\n  const packingPanel = workspace ? (`)
   code=once(code,"      data-testid=\"fbs-workspace\"\n","      data-testid=\"fbs-workspace\"\n")
   const marker=code.lastIndexOf('data-testid="fbs-workspace"')
   const opening=code.indexOf('>',marker)
   code=code.slice(0,opening+1)+'<Box id="demo-service-host" />'+code.slice(opening+1)
   return code
 }
 if(id.endsWith('/FfFbsSupplyAssembly.tsx')){
   code=`import {PackingToolbar} from ${local('./Controls.tsx')};\nimport {proposal} from ${local('./state.ts')};\n`+code
   code=once(code,'                <Box ref={setPackingHost}', '                {proposal ? <PackingToolbar supplyIds={supplyIds}/> : null}\n                <Box ref={setPackingHost}')
   const marker=code.indexOf('data-testid="fbs-assembly"')
   const opening=code.indexOf('>',marker)
   return code.slice(0,opening+1)+'<Box id="demo-service-host" />'+code.slice(opening+1)
 }
 if(id.endsWith('/useMarkingCodePrint.tsx')){
   code=`import {log,advancePrint,cancelPrintQueue} from ${local('./state.ts')};\n`+code
   code="import {useRef as useDemoPrintRef} from 'react';\n"+code
   code=once(code,'export function useMarkingCodePrint() {','export function useMarkingCodePrint() {\n const demoPrinted=useDemoPrintRef(false)')
   code=once(code,'    setCtx(args)',"    log('Открыто штатное окно печати',{document:args.documentNumber,orders:args.fbsTape?.orders.map(o=>o.orderId),includeOrderQr:args.fbsTape?.includeOrderQr,reprint:opts?.reprint,exactMarking:args.fbsTape});\n    demoPrinted.current=false;\n    setCtx({...args,onPrinted:()=>{demoPrinted.current=true;args.onPrinted()}})")
   code=once(code,'    setCtx(null)',"    setCtx(null)\n    if(demoPrinted.current)setTimeout(advancePrint,0);else cancelPrintQueue()")
   return code
 }
 if(id.endsWith('/FbsPrintPreviewDialog.tsx')){
   code=`import {log} from ${local('./state.ts')};\n`+code
   return once(code,'  const print = (items: Preview[]) => {',"  const print = (items: Preview[]) => {\n    log('Штатный предпросмотр QR · демонстрация печати',{assets:items.map(item=>item.asset.id),copies});appliedCopies.current=copies;return;")
 }
 if(id.endsWith('/MarkingPrintDialog.tsx')){
   code=once(code,"    if (result.shortage > 0 && !allowPartial) {","    if (result.shortage === 0) { ctx.onPrinted(); if(closeAfter)onClose(); return true }\n    if (result.shortage > 0 && !allowPartial) {")
   return code
 }
 if(/\/src\/utils\/.*print.*\.[tj]sx?$/i.test(id)||id.endsWith('/MarkingPrintDialog.tsx')){
   if(/\.print\(/.test(code))return code.replace(/\b[A-Za-z_$][\w$]*\.print\(\)/g,"window.dispatchEvent(new Event('wms666-print-blocked'))")
 }
}}}
