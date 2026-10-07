import type { Plugin } from 'vite';
import { fileURLToPath } from 'node:url';
const controls = fileURLToPath(new URL('./Controls.tsx', import.meta.url));
const api = fileURLToPath(new URL('./mockApi.ts', import.meta.url));
function replaceOnce(code: string, target: string, replacement: string, id: string) {
  if (code.split(target).length !== 2) throw new Error('WMS686: исходный фрагмент изменился: ' + id);
  return code.replace(target, replacement);
}
export function demoTransform(): Plugin {
  return {
    name: 'wms686-isolated-design', enforce: 'pre',
    transform(code, id) {
      if (/\/frontend\/src\/utils\/print[^/]+\.ts$/.test(id)) {
        return code.replace(/\b[A-Za-z_$][\w$]*\.print\(\)/g, "window.dispatchEvent(new Event('wms686-print-blocked'))");
      }
      if (id.endsWith('/UnloadPickScreen.tsx')) {
        code = `import {useKizPicking,PickScanMode} from ${JSON.stringify(controls)};\n` + code;
        code = replaceOnce(code, "  const [scanValue, setScanValue] = useState('')", "  const kizPicking = useKizPicking()\n  useEffect(() => {setPicked({...initialPicked})},[initialPicked])\n  const [scanValue, setScanValue] = useState('')", id);
        code = replaceOnce(code, "    setScanValue('')\n    if (await handleServerScan(code)) return", `    setScanValue('')
    const step = kizPicking.receive(code,source)
    if (step.handled) {
      if (step.productCode) {
        await handleServerScan(step.productCode)
      } else {
        setScanError(step.error ?? null)
        setScanNotice(step.notice ?? null)
      }
      return
    }
    if (await handleServerScan(code)) return`, id);
        code = replaceOnce(code, '        <Stack spacing={1.5}>\n          <ScannerField', '        <Stack spacing={1.5}>\n          <PickScanMode picking={kizPicking} />\n          <ScannerField', id);
        code = replaceOnce(code, "expects={source ? 'товар, который снимаете' : 'место или товар'}", "expects={kizPicking.mode === 'kiz' ? 'ячейка / короб / товар / КИЗ' : kizPicking.mode === 'box' ? 'ячейка / целый короб' : source ? 'товар, который снимаете' : 'место или товар'}", id);
        code = replaceOnce(code, "setScanNotice(`${result.sku}: снято ${added || 1} шт — ${place.label}`)", "setScanNotice(`${result.sku}: снято ${added || 1} шт — ${place.label}${result.kiz ? ` · ${result.kiz}` : ''}`)", id);
        return code;
      }
      if (id.endsWith('/FfUnloadPickPage.tsx')) {
        code = replaceOnce(code, "  // WMS-575: места подбора перечитываются", "  useEffect(() => { const refresh=()=>{void updateOption()}; window.addEventListener('wms686-change',refresh); return ()=>window.removeEventListener('wms686-change',refresh) },[requestId])\n\n  // WMS-575: места подбора перечитываются", id);
        code = replaceOnce(code, '          allocationQuantity: result.allocation_quantity,', '          allocationQuantity: result.allocation_quantity,\n          kiz: result.kiz,', id);
        return code;
      }
      if (!id.endsWith('/FfSuppliesShipmentsPage.tsx')) return;
      code = `import {isBaseline} from ${JSON.stringify(api)};\n` + code;
      code = replaceOnce(code, '  useEffect(() => {\n    void loadPackagingTask()\n  }, [loadPackagingTask])', `  useEffect(() => {\n    void loadPackagingTask()\n  }, [loadPackagingTask])\n  useEffect(() => {const refresh=()=>{void loadDocDetail();void loadPackagingTask()};window.addEventListener('wms686-change',refresh);return ()=>window.removeEventListener('wms686-change',refresh)},[loadDocDetail,loadPackagingTask])`, id);
      code = replaceOnce(code, '  const [unloadDetail, setUnloadDetail] = useState<MarketplaceUnloadDetail | null>(null)', `  const [unloadDetail, setUnloadDetail] = useState<MarketplaceUnloadDetail | null>(null)\n  useEffect(() => {if(!unloadDetail) return;const tab=new URLSearchParams(location.search).get('tab');if(tab==='pick'||tab==='packaging')setMpUnloadTab(tab)},[unloadDetail?.id])`, id);
      return code;
    },
  };
}
