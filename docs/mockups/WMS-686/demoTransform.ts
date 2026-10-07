import type { Plugin } from 'vite'
import { fileURLToPath } from 'node:url'

// WMS-686 · сборка макета встраивает предложение R1–R27 в НАСТОЯЩИЕ экраны WMS.
// frontend/src не редактируется: точечные подмены выполняются только при сборке
// макета. Каждая подмена ищет исходный фрагмент ровно один раз — если исходник
// изменился, сборка падает, а не показывает тихо устаревший макет.

const controls = JSON.stringify(fileURLToPath(new URL('./Controls.tsx', import.meta.url)))
const api = JSON.stringify(fileURLToPath(new URL('./mockApi.ts', import.meta.url)))

function replaceOnce(code: string, target: string, replacement: string, id: string): string {
  if (code.split(target).length !== 2) throw new Error(`WMS-686: исходный фрагмент изменился: ${id}\n${target}`)
  return code.replace(target, () => replacement)
}

type Edit = [target: string, replacement: string]
function apply(code: string, id: string, imports: string, edits: Edit[]): string {
  let next = imports + code
  for (const [target, replacement] of edits) next = replaceOnce(next, target, replacement, id)
  return next
}

export function demoTransform(): Plugin {
  return {
    name: 'wms686-fbo-design',
    enforce: 'pre',
    transform(code, id) {
      // Нативная печать браузера в макете не открывается (R27, C33).
      if (/\/frontend\/src\/utils\/print[^/]+\.ts$/.test(id)) {
        return code.replace(/\b[A-Za-z_$][\w$]*\.print\(\)/g, "window.dispatchEvent(new Event('wms686-print-blocked'))")
      }

      // Та же панель FBS; минимальная будущая правка — подпись первой галки (R12: «Печатать ШК» вместо QR).
      if (id.endsWith('/screens/v2/FbsScanPrintToggles.tsx')) {
        return apply(code, id, '', [
          ['qrDisabled = false }: {', 'qrDisabled = false, qrLabel }: {\n  qrLabel?: string'],
          ['      label="Печатать QR"', "      label={qrLabel ?? 'Печатать QR'}"],
        ])
      }

      // «Подбор»: строки КИЗ во вложенности места под товаром (R3, R20).
      if (id.endsWith('/unload-pick/PickPlacesTree.tsx')) {
        return apply(code, id, `import { PickKizRows } from ${controls};\n`, [
          ['        ) : (\n          <Indent depth={node.depth}>\n            <Box sx={{ width: 24, flexShrink: 0 }} />',
            '        ) : (<>\n          <Indent depth={node.depth}>\n            <Box sx={{ width: 24, flexShrink: 0 }} />'],
          ["          </Indent>\n        ),\n    },\n    {\n      key: 'barcode',",
            "          </Indent>\n          <PickKizRows productId={row.product.id} placeKey={node.place.key} depth={node.depth} />\n        </>),\n    },\n    {\n      key: 'barcode',"],
        ])
      }

      // «Подбор»: КИЗ после товара, «Забрать целиком», устойчивый источник (R1, R3, R7, R9г).
      if (id.endsWith('/unload-pick/UnloadPickScreen.tsx')) {
        return apply(code, id, `import { SourceKizInfo, TakeWholeButton, markNewKiz, restorePickSource, savePickSource, unlinkPickKiz } from ${controls};\n`, [
          ['  const [source, setSource] = useState<string | null>(null)\n  const [sourceLabel, setSourceLabel] = useState<string | null>(null)',
            '  const [source, setSource] = useState<string | null>(() => restorePickSource(documentProp).source)\n'
            + '  const [sourceLabel, setSourceLabel] = useState<string | null>(() => restorePickSource(documentProp).label)\n'
            + '  useEffect(() => { savePickSource(documentProp, source, sourceLabel) }, [documentProp, source, sourceLabel])'],
          ["  const [scanValue, setScanValue] = useState('')",
            "  useEffect(() => { setPicked({ ...(initialPicked ?? {}) }) }, [initialPicked])\n  const [scanValue, setScanValue] = useState('')"],
          ['      const result = await onScan({ barcode: code, sourceKey: source })\n',
            `      const result = await onScan({ barcode: code, sourceKey: source })
      if ((result as { kind: string }).kind === 'marking') {
        const marking = result as unknown as { productId: string; cis: string; already: boolean }
        const kizRow = rows.find((one) => one.product.id === marking.productId)
        if (kizRow) expandRow(kizRow.key)
        markNewKiz(marking.cis)
        if (!marking.already) setHistory((current) => [...current, { productId: marking.productId, placeKey: source ?? '', qty: 0, kiz: marking.cis } as PickOp])
        setScanError(null)
        setScanNotice(marking.already ? 'КИЗ уже привязан — новой единицы нет' : \`\${kizRow?.product.sku ?? 'Товар'}: КИЗ привязан к снятой единице\${sourceText ? \` — \${sourceText}\` : ''}. Количество не изменилось\`)
        playScanSuccess()
        return true
      }
`],
          ['      expandRow(row.key)\n      setScanError(null)\n      setScanNotice(`${result.sku}: снято ${added || 1} шт — ${place.label}`)',
            '      expandRow(row.key)\n      markNewKiz(null)\n      setScanError(null)\n      setScanNotice(`${result.sku}: снято ${added || 1} шт — ${place.label}`)'],
          ['              <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid="pick-source">\n                {sourceText}\n              </Typography>',
            '              <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid="pick-source">\n                {sourceText}\n              </Typography>\n'
            + "              {source?.startsWith('obj:') ? <TakeWholeButton containerId={source.slice(4)} onDone={(text) => { setScanError(null); setScanNotice(text) }} /> : null}\n"
            + "              {source?.startsWith('obj:') ? <SourceKizInfo containerId={source.slice(4)} /> : null}"],
          ["expects={source ? 'товар, который снимаете' : 'место или товар'}", "expects={source ? 'товар или его КИЗ' : 'место, товар или КИЗ'}"],
          ['    const operation = history[index]\n    const key = pickKey(operation.productId, operation.placeKey)',
            `    const operation = history[index]
    if ((operation as { kiz?: string }).kiz) {
      const cis = (operation as unknown as { kiz: string }).kiz
      void unlinkPickKiz(cis)
      setHistory((current) => current.filter((_, position) => position !== index))
      setScanNotice('КИЗ отвязан — единица осталась снятой')
      return
    }
    const key = pickKey(operation.productId, operation.placeKey)`],
        ])
      }

      // Подбор ↔ сервер: ключ операции на скан (R10), КИЗ с целевым товаром (R3), без перемонтирования (R1/K3).
      if (id.endsWith('/unload-pick/FfUnloadPickPage.tsx')) {
        return apply(code, id, `import { isKizScan as wms686IsKiz, newKey as wms686NewKey } from ${controls};\n`, [
          ['        key={`${requestId}-${version}`}', '        key={requestId}'],
          ['  const scannedContainers = useRef<\n    Map<string, { locationId: string; containerKind: ObjKind; containerId: string }>\n  >(new Map())',
            '  const scannedContainers = useRef<\n    Map<string, { locationId: string; containerKind: ObjKind; containerId: string }>\n  >(new Map())\n'
            + "  // D16: контекст последнего скана — единица (после ШК), израсходован (после её КИЗ), проверка (после источника).\n"
            + "  const wms686Ctx = useRef<{ kind: 'unit' | 'consumed' | 'verify'; productId: string | null }>({ kind: 'verify', productId: null })"],
          ['  const scan = useCallback(',
            "  useEffect(() => {\n    const refresh = () => { void updateOption() }\n    window.addEventListener('wms686-change', refresh)\n    return () => window.removeEventListener('wms686-change', refresh)\n  }, [updateOption])\n\n  const scan = useCallback("],
          ['      setBusy(true)\n      setError(null)\n      try {\n        const res = await fetch(apiUrl(`${BASE}/${requestId}/pick/scan`), {',
            "      if (wms686IsKiz(barcode) && wms686Ctx.current.kind === 'consumed') {\n        throw new Error('Код уже есть у этой единицы: отсканируйте ШК следующей единицы.')\n      }\n"
            + '      setBusy(true)\n      setError(null)\n      try {\n        const res = await fetch(apiUrl(`${BASE}/${requestId}/pick/scan`), {'],
          ['            barcode,\n            ...(matchedProduct ? { product_id: matchedProduct.id } : {}),',
            '            barcode,\n            mutation_id: wms686NewKey(),\n'
            + "            ...(matchedProduct ? { product_id: matchedProduct.id } : wms686IsKiz(barcode) && wms686Ctx.current.kind === 'unit' && wms686Ctx.current.productId ? { product_id: wms686Ctx.current.productId } : {}),"],
          ['        const result = (await res.json()) as ApiScanResult\n',
            `        const result = (await res.json()) as ApiScanResult
        if ((result.kind as string) === 'marking') {
          const marking = result as unknown as { product_id: string; cis_code: string; already_linked: boolean }
          if (wms686Ctx.current.kind === 'unit') wms686Ctx.current = { kind: 'consumed', productId: marking.product_id }
          void updateOption()
          return { kind: 'marking', productId: marking.product_id, cis: marking.cis_code, already: marking.already_linked } as unknown as UnloadPickScanResult
        }
`],
          ["          return {\n            kind: 'location',", "          wms686Ctx.current = { kind: 'verify', productId: null }\n          return {\n            kind: 'location',"],
          ["          return {\n            kind: 'container',", "          wms686Ctx.current = { kind: 'verify', productId: null }\n          return {\n            kind: 'container',"],
          ['        if (result.storage_location_id || containerSource) {', "        wms686Ctx.current = { kind: 'unit', productId: result.product_id }\n        if (result.storage_location_id || containerSource) {"],
        ])
      }

      // «Упаковка»: поле скана FBS-вида, вложенность КИЗ под товаром, ЧЗ = напечатано + отсканировано (R12–R18).
      if (id.endsWith('/screens/ff/FfPackagingPage.tsx')) {
        return apply(code, id, `import { Fragment as Wms686Fragment } from 'react';\nimport { FboPackExpand, FboPackNested, FboPackScanBar, fboPackRowSx } from ${controls};\n`, [
          ["      {isMpUnloadTask ? (\n        <Stack direction=\"row\" sx={{ justifyContent: 'flex-end' }}>",
            "      {isMpUnloadTask && task.marketplace_unload_request_id ? <FboPackScanBar shipmentId={task.marketplace_unload_request_id} onBoxBarcodeScan={onBoxBarcodeScan} /> : null}\n"
            + "      {isMpUnloadTask ? (\n        <Stack direction=\"row\" sx={{ justifyContent: 'flex-end' }}>"],
          ["                return (\n                  <TableRow\n                    key={ln.id}\n                    data-testid={markingProgressIncomplete ? 'ff-packaging-line-marking-incomplete' : 'ff-packaging-line'}\n                    selected={focusedLineId === ln.id}\n                  >",
            "                return (<Wms686Fragment key={ln.id}>\n                  <TableRow\n                    data-testid={markingProgressIncomplete ? 'ff-packaging-line-marking-incomplete' : 'ff-packaging-line'}\n                    selected={focusedLineId === ln.id}\n                    sx={fboPackRowSx(ln)}\n                  >"],
          ['                      {renderLineActions?.(ln)}\n                    </TableCell>\n                  </TableRow>\n                )\n              })}\n            </TableBody>',
            '                      {renderLineActions?.(ln)}\n                    </TableCell>\n                  </TableRow>\n                  <FboPackNested line={ln} colSpan={8} />\n                </Wms686Fragment>)\n              })}\n            </TableBody>'],
          ["                      <Stack direction=\"row\" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>\n                        <ProductPhotoThumb\n                          src={displayMeta.wb_primary_image_url}",
            "                      <Stack direction=\"row\" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>\n                        <FboPackExpand line={ln} />\n                        <ProductPhotoThumb\n                          src={displayMeta.wb_primary_image_url}"],
          ['label={`${ln.qty_marking_printed}/${ln.qty_need_pack}`}', 'label={`${ln.qty_marking_printed + (ln.qty_marking_external ?? 0)}/${ln.qty_need_pack}`}'],
        ])
      }

      // Документ отгрузки: сканер вкладки «Упаковка» отдаёт поле скана FBO, текущий короб, пропуск у XLSX (R15, R25).
      if (id.endsWith('/screens/ff/FfSuppliesShipmentsPage.tsx')) {
        return apply(code, id, `import { isBaseline as wms686Baseline } from ${api};\nimport { CurrentBoxChip, FboBoxLineRemove, FboPassField } from ${controls};\n`, [
          ["      mpUnloadTab === 'packaging' &&\n      mpExecutionPhase &&", "      mpUnloadTab === 'packaging' &&\n      wms686Baseline() &&\n      mpExecutionPhase &&"],
          ['  useEffect(() => {\n    void loadPackagingTask()\n  }, [loadPackagingTask])',
            "  useEffect(() => {\n    void loadPackagingTask()\n  }, [loadPackagingTask])\n"
            + "  useEffect(() => {\n    const refresh = () => { void loadDocDetail(); void loadPackagingTask() }\n    window.addEventListener('wms686-change', refresh)\n    return () => window.removeEventListener('wms686-change', refresh)\n  }, [loadDocDetail, loadPackagingTask])"],
          ["    mpTabInitForRef.current = docModalId\n    setMpUnloadTab('plan')",
            "    mpTabInitForRef.current = docModalId\n    setMpUnloadTab(((tab) => (tab === 'pick' || tab === 'packaging' ? tab : 'plan'))(new URLSearchParams(window.location.search).get('tab')))"],
          ['                      <TableCell align="right">{ln.quantity}</TableCell>\n                      {canUseMpBoxDestructiveControls ? (',
            '                      <TableCell align="right">{ln.quantity}{canUseMpBoxOperationalControls ? <FboBoxLineRemove boxId={box.id} line={ln} /> : null}</TableCell>\n                      {canUseMpBoxDestructiveControls ? ('],
          ['              {boxLabel}\n            </Typography>', '              {boxLabel}\n              <CurrentBoxChip boxId={box.id} />\n            </Typography>'],
          ['                              Скачать XLSX для WB\n                            </Button>', '                              Скачать XLSX для WB\n                            </Button>\n                            <FboPassField shipmentId={unloadDetail.id} />'],
        ])
      }
      return undefined
    },
  }
}
