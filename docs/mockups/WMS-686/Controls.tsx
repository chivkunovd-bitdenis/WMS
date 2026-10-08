// WMS-686 · элементы макета, которые сборка (demoTransform.ts) встраивает в
// настоящие экраны WMS. Это демонстрация поведения R1–R27, не продуктовый код:
// данные — вымышленные (fboModel.ts), запросы — в локальный mockApi.ts,
// печать — только предпросмотр, на принтер и в WMS Print ничего не уходит.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import {
  Alert, Box, Button, Chip, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Menu, MenuItem,
  Paper, Snackbar, Stack, Table, TableBody, TableCell, TableRow, TextField, Tooltip, Typography, alpha,
} from '@mui/material'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { FbsScanPrintToggles } from '../../../frontend/src/screens/v2/FbsScanPrintToggles'
import { normalizeFbsChzCopies, type FbsScanPrintPreferences } from '../../../frontend/src/screens/v2/fbsScanAutoPrint'
import { LabelSizeSelect } from '../../../frontend/src/components/LabelSizeSelect'
import { useScanIntake } from '../../../frontend/src/hooks/useScanIntake'
import { playScanError, playScanSuccess } from '../../../frontend/src/utils/scanFeedback'
import { loadLabelSizeId, resolveLabelSize, type LabelSize } from '../../../frontend/src/utils/labelSize'
import { buildProductThermalLabelDocument } from '../../../frontend/src/utils/printProductThermalLabel'
import { renderBarcodeDataUrl } from '../../../frontend/src/utils/renderBarcodeDataUrl'
import { buildCzLabelHtml, buildTapePageCss, renderDataMatrixDataUrl } from '../../../frontend/src/utils/printMarkingCodeLabel'
import {
  activeShipmentId, getFbo, isBaseline, products, resetFbo, subscribeFbo,
} from './mockApi'
import { boxedQty, cells, isKizScan, kizFor, pickSourcesOf, productByBarcode, productById, returnSourceFor, sourceById, sources, type FboBox } from './fboModel'

// ─── состояние экрана макета (что подсвечено, что раскрыто, журнал демо-печати) ───

type PrintJob = { key: string; kind: 'barcode' | 'kiz'; title: string; productId: string; cis?: string; copy: number }
type Ui = {
  newKiz: string | null
  packLastProduct: string | null
  packExpanded: Record<string, boolean>
  currentBox: Record<string, string>
  printLog: PrintJob[]
  printNotice: { text: string; job: PrintJob } | null
  printError: { text: string; jobs: PrintJob[] } | null
  printDown: boolean
  packUndo: Array<{ kind: 'unit'; shipmentId: string; boxId: string; productId: string } | { kind: 'kiz'; shipmentId: string; cis: string }>
  nativePrintBlocked: number
}
let ui: Ui = {
  newKiz: null, packLastProduct: null, packExpanded: {}, currentBox: {}, printLog: [], printNotice: null,
  printError: null, printDown: false, packUndo: [], nativePrintBlocked: 0,
}
const uiListeners = new Set<() => void>()
function setUi(patch: Partial<Ui> | ((current: Ui) => Partial<Ui>)) {
  ui = { ...ui, ...(typeof patch === 'function' ? patch(ui) : patch) }
  uiListeners.forEach((listener) => listener())
}
const subscribeUi = (listener: () => void) => {
  uiListeners.add(listener)
  return () => uiListeners.delete(listener)
}
export const useUi = () => useSyncExternalStore(subscribeUi, () => ui)
export const useFbo = () => useSyncExternalStore(subscribeFbo, getFbo)

if (typeof window !== 'undefined') {
  window.addEventListener('wms686-print-blocked', () => setUi((current) => ({ nativePrintBlocked: current.nativePrintBlocked + 1 })))
}

const authHeaders = { Authorization: 'Bearer fictional-demo-token', 'Content-Type': 'application/json' }
const base = (shipmentId: string) => `/api/operations/marketplace-unload-requests/${shipmentId}`
async function api(path: string, init: RequestInit = {}): Promise<{ ok: boolean; status: number; data: Record<string, unknown> }> {
  const response = await fetch(path, { ...init, headers: { ...authHeaders, ...(init.headers ?? {}) } })
  const data = await response.json().catch(() => ({})) as Record<string, unknown>
  return { ok: response.ok, status: response.status, data }
}
const changed = () => window.dispatchEvent(new Event('wms686-change'))
const errorText = (data: Record<string, unknown>) => typeof data.detail === 'string' ? data.detail : 'Не удалось выполнить действие'
const newKey = () => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `k${Date.now()}${Math.random()}`)

const kizRowSx = (isNew: boolean) => isNew ? {
  backgroundColor: (theme: { palette: { success: { main: string } } }) => alpha(theme.palette.success.main, 0.16),
  boxShadow: (theme: { palette: { success: { main: string } } }) => `inset 0 0 0 1px ${alpha(theme.palette.success.main, 0.6)}`,
} : {}
const shortCis = (cis: string) => cis.length > 26 ? `${cis.slice(0, 18)}…${cis.slice(-6)}` : cis

// ─── «Подбор»: строки КИЗ под товаром в строке источника (R3, R9, R20) ───

/** Источник подбора строки места: `cell:<id>` — россыпь ячейки, `obj:<id>` — тара. */
export function PickKizRows({ productId, placeKey, depth }: { productId: string; placeKey: string; depth: number }) {
  const fbo = useFbo()
  const state = useUi()
  const [menu, setMenu] = useState<{ anchor: HTMLElement; cis: string } | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const shipmentId = activeShipmentId()
  if (isBaseline()) return null
  const [kind, id] = [placeKey.slice(0, placeKey.indexOf(':')), placeKey.slice(placeKey.indexOf(':') + 1)]
  const rows = fbo.links.filter((link) => link.shipmentId === shipmentId && link.productId === productId
    && (kind === 'obj' ? link.sourceId === id : link.cellId === id && link.sourceId === null))
  if (!rows.length) return null
  return (
    <Stack spacing={0.25} sx={{ pl: `${depth * 24 + 46}px`, py: 0.25 }}>
      {rows.map((link) => (
        <Stack key={link.cis} direction="row" spacing={1} data-testid="pick-kiz-row"
          data-kiz-state={state.newKiz === link.cis ? 'new' : 'saved'}
          sx={{ alignItems: 'center', borderRadius: 0.5, px: 0.75, minHeight: 28, ...kizRowSx(state.newKiz === link.cis) }}>
          <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>КИЗ</Typography>
          <Typography variant="body2" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12.5, wordBreak: 'break-all', minWidth: 0 }}>
            {shortCis(link.cis)}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
            {link.intakeDoc ? `Приёмка ${link.intakeDoc}` : 'Приёмка не указана'}
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Tooltip title="Вернуть единицу с этим кодом или отвязать ошибочный код">
            <IconButton size="small" aria-label={`Действия с КИЗ ${link.cis}`} data-testid="pick-kiz-remove"
              onClick={(event) => setMenu({ anchor: event.currentTarget, cis: link.cis })}>
              <CloseOutlined fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      ))}
      <Menu anchorEl={menu?.anchor ?? null} open={Boolean(menu)} onClose={() => setMenu(null)}>
        <MenuItem data-testid="pick-kiz-return" onClick={() => {
          const cis = menu!.cis
          setMenu(null)
          void api(`${base(shipmentId)}/marking-codes/${encodeURIComponent(cis)}/return`, { method: 'POST', body: JSON.stringify({ mutation_id: newKey() }) })
            .then((result) => { setMessage(result.ok ? `Единица с КИЗ ${shortCis(cis)} возвращена в ${kind === 'obj' ? sourceById(id)?.code : 'ячейку'}; код — точно в этой таре` : errorText(result.data)); changed() })
        }}>Вернуть эту единицу в {kind === 'obj' ? sourceById(id)?.code : cells.find((cell) => cell.id === id)?.code}</MenuItem>
        <MenuItem data-testid="pick-kiz-unlink" onClick={() => {
          const cis = menu!.cis
          setMenu(null)
          void api(`${base(shipmentId)}/marking-codes/${encodeURIComponent(cis)}`, { method: 'DELETE' })
            .then(() => { setMessage(`Код ${shortCis(cis)} отвязан (ошибочный скан); единица осталась снятой`); changed() })
        }}>Только отвязать код (ошибочный скан)</MenuItem>
      </Menu>
      {message ? <Typography variant="caption" color="text.secondary" sx={{ px: 0.75 }}>{message}</Typography> : null}
    </Stack>
  )
}

/** Подсветка нового КИЗ после скана в «Подборе». */
export function markNewKiz(cis: string | null) {
  setUi({ newKiz: cis })
}

/** R1/D6: источник подбора помнится в пределах документа — ошибка, вкладка, перезагрузка его не сбрасывают. */
export function restorePickSource(documentKey: string | undefined): { source: string | null; label: string | null } {
  if (isBaseline() || !documentKey) return { source: null, label: null }
  try {
    const raw = sessionStorage.getItem(`wms686-pick-source:${documentKey}`)
    return raw ? (JSON.parse(raw) as { source: string | null; label: string | null }) : { source: null, label: null }
  } catch {
    return { source: null, label: null }
  }
}
export function savePickSource(documentKey: string | undefined, source: string | null, label: string | null) {
  if (isBaseline() || !documentKey) return
  try { sessionStorage.setItem(`wms686-pick-source:${documentKey}`, JSON.stringify({ source, label })) } catch { /* без сохранения */ }
}
/** «Отменить последнее снятие» для КИЗ: отвязать код, единица остаётся снятой (R9г). */
export async function unlinkPickKiz(cis: string) {
  await api(`${base(activeShipmentId())}/marking-codes/${encodeURIComponent(cis)}`, { method: 'DELETE' })
  changed()
}
export { isKizScan, newKey }

// ─── «Подбор»: «Забрать целиком» в строке «Снимаем с:» (R7) ───

export function TakeWholeButton({ containerId, onDone }: { containerId: string; onDone?: (text: string) => void }) {
  const source = sourceById(containerId)
  const [busy, setBusy] = useState(false)
  const [overPlan, setOverPlan] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (isBaseline() || !source) return null
  const take = async (allowOverPlan: boolean) => {
    setBusy(true)
    setError(null)
    const shipmentId = activeShipmentId()
    const before = getFbo().stock.filter((line) => line.sourceId === source.id).reduce((sum, line) => sum + line.qty, 0)
    const result = await api(`${base(shipmentId)}/boxes/attach`, { method: 'POST', body: JSON.stringify({ barcode: source.code, box_preset: '60_40_40', allow_over_plan: allowOverPlan }) })
    setBusy(false)
    if (!result.ok && result.data.detail === 'plan_limit_exceeded' && !allowOverPlan) {
      setOverPlan(true)
      return
    }
    if (!result.ok) {
      setError(errorText(result.data))
      playScanError()
      return
    }
    playScanSuccess()
    changed()
    onDone?.(`${source.code}: забран целиком, ${before} шт. — в отгрузке отдельным коробом со своим ШК`)
  }
  return (
    <>
      <Button size="small" variant="outlined" disabled={busy} onClick={() => void take(false)} data-testid="pick-source-take-whole">
        Забрать целиком
      </Button>
      {error ? <Typography variant="caption" color="error.main">{error}</Typography> : null}
      <Dialog open={overPlan} onClose={() => setOverPlan(false)} data-testid="pick-take-whole-over-plan">
        <DialogTitle>Больше, чем в плане</DialogTitle>
        <DialogContent>
          <Typography variant="body2">В таре {source.code} товара больше, чем осталось по плану отгрузки. Добавить всё содержимое?</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOverPlan(false)}>Отмена</Button>
          <Button variant="contained" onClick={() => { setOverPlan(false); void take(true) }}>Добавить</Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

// ─── «Упаковка»: поле скана и панель печати FBS-вида (R12–R17) ───

const FBO_PREFS_KEY = 'wms:fbo:scan-auto-print:demo'
// В FBO флаг printQr означает «Печатать ШК» (у FBO нет QR заказа FBS); хранится отдельно от FBS (D7).
const DEFAULT_PREFS: FbsScanPrintPreferences = { printQr: false, printChz: false, reprintChz: false, printChzCopies: 1, reprintChzCopies: 1 }
/** Та же панель FBS; сборка макета добавляет ей подпись первой галки (минимальная будущая правка). */
const Toggles = FbsScanPrintToggles as unknown as (props: Parameters<typeof FbsScanPrintToggles>[0] & { qrLabel?: string }) => ReactNode
function loadPrefs(): FbsScanPrintPreferences {
  try {
    const raw = localStorage.getItem(FBO_PREFS_KEY)
    return raw ? { ...DEFAULT_PREFS, ...(JSON.parse(raw) as FbsScanPrintPreferences) } : DEFAULT_PREFS
  } catch {
    return DEFAULT_PREFS
  }
}
const savePrefs = (prefs: FbsScanPrintPreferences) => {
  try { localStorage.setItem(FBO_PREFS_KEY, JSON.stringify(prefs)) } catch { /* без сохранения */ }
}

/** Текущий короб: выбранный оператором или последний созданный открытый (R15). */
export function currentBoxOf(shipmentId: string, boxes = getFbo().boxes): FboBox | null {
  const chosen = boxes.find((box) => box.shipmentId === shipmentId && box.id === ui.currentBox[shipmentId])
  if (chosen) return chosen
  const open = boxes.filter((box) => box.shipmentId === shipmentId && !box.closed)
  return open.sort((a, b) => b.createdAt - a.createdAt)[0] ?? null
}

/** Демо WMS Print: ключ на единицу и экземпляр; повтор того же ключа не печатает второй раз. */
function demoPrint(jobs: PrintJob[]): void {
  if (ui.printDown) {
    setUi({ printError: { text: 'Нет ответа WMS Print. Запустите программу. Если Chrome запросил доступ к этому компьютеру — разрешите его. Перед повтором проверьте очередь принтера.', jobs } })
    throw new Error('wms-print-down')
  }
  const known = new Set(ui.printLog.map((job) => job.key))
  const fresh = jobs.filter((job) => !known.has(job.key))
  if (!fresh.length) return
  setUi((current) => ({
    printLog: [...current.printLog, ...fresh],
    printError: null,
    printNotice: { text: `Макет: ${fresh.length > 1 ? `${fresh.length} этикетки` : 'этикетка'} «${fresh[0].title}» подготовлена для WMS Print (ключ ${fresh[0].key.slice(-12)}). На принтер ничего не отправлено.`, job: fresh[0] },
  }))
}

function copiesJobs(kind: PrintJob['kind'], key: string, count: number, base: Omit<PrintJob, 'key' | 'copy' | 'kind'>): PrintJob[] {
  return Array.from({ length: count }, (_, index) => ({ ...base, kind, copy: index + 1, key: index === 0 ? key : `${key}:c${index + 1}` }))
}

export function FboPackScanBar({ shipmentId, onBoxBarcodeScan }: { shipmentId: string; onBoxBarcodeScan?: (code: string) => void }) {
  const fbo = useFbo()
  const state = useUi()
  const [value, setValue] = useState('')
  const [prefs, setPrefs] = useState(loadPrefs)
  const [labelSizeId, setLabelSizeId] = useState(loadLabelSizeId)
  const [error, setError] = useState<ReactNode>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // D16: контекст последнего скана — единица (после ШК), израсходован (после её КИЗ), проверка (после ШК короба).
  const lastProduct = useRef<string | null>(null)
  const unitConsumed = useRef(false)
  const current = currentBoxOf(shipmentId, fbo.boxes)
  const prefsRef = useRef(prefs)
  prefsRef.current = prefs

  const createBox = async () => {
    const result = await api(`${base(shipmentId)}/boxes/batch`, { method: 'POST', body: JSON.stringify({ count: 1, box_preset: '60_40_40' }) })
    if (!result.ok) return setError(errorText(result.data))
    const created = currentBoxOf(shipmentId)
    if (created) setUi((currentUi) => ({ currentBox: { ...currentUi.currentBox, [shipmentId]: created.id } }))
    setError(null)
    setNotice(`Создан короб ${created?.code ?? ''}. Он текущий — сканируйте товар.`)
    changed()
  }

  const linkKiz = async (cis: string, boxId: string, productId: string | null, printed: boolean, mutationId: string) => {
    const result = await api(`${base(shipmentId)}/boxes/${boxId}/scan`, {
      method: 'POST', body: JSON.stringify({ barcode: cis, product_id: productId, mutation_id: mutationId, printed }),
    })
    return result
  }

  const handle = async (raw: string) => {
    const code = raw.trim()
    if (!code) return
    setValue('')
    setError(null)
    setNotice(null)
    const prefsNow = prefsRef.current
    const ownBox = getFbo().boxes.find((box) => box.shipmentId === shipmentId && box.code === code)
    if (ownBox) {
      lastProduct.current = null
      unitConsumed.current = false
      setUi((currentUi) => ({ currentBox: { ...currentUi.currentBox, [shipmentId]: ownBox.id } }))
      setNotice(ownBox.closed
        ? `Текущий короб: ${ownBox.code} (${ownBox.whole ? 'взят целиком' : 'был закрыт'}) — можно сканировать КИЗ его единиц без переупаковки, добавлять и убирать товар. Количество не изменилось.`
        : `Текущий короб: ${ownBox.code}`)
      playScanSuccess()
      return
    }
    if (/^(WHB|INB|PLT)-/i.test(code) || sources.some((source) => source.code === code)) {
      onBoxBarcodeScan?.(code)
      return
    }
    if (isKizScan(code)) {
      if (unitConsumed.current) {
        playScanError()
        return setError('Код уже есть у этой единицы: отсканируйте ШК следующей единицы или ШК короба для проверки.')
      }
      const productId = lastProduct.current
      const target = current
      if (!target) {
        playScanError()
        return setError('Нет текущего короба: отсканируйте ШК короба, в котором лежит единица с этим КИЗ.')
      }
      const mutationId = newKey()
      const result = await linkKiz(code, target.id, productId, false, mutationId)
      if (!result.ok) {
        playScanError()
        return setError(errorText(result.data))
      }
      const linkedProduct = String(result.data.product_id)
      const lastProductBefore = lastProduct.current
      if (lastProduct.current) unitConsumed.current = true
      setUi((currentUi) => ({
        newKiz: code, packLastProduct: linkedProduct, packExpanded: { ...currentUi.packExpanded, [linkedProduct]: true },
        packUndo: result.data.already_linked ? currentUi.packUndo : [...currentUi.packUndo, { kind: 'kiz', shipmentId, cis: code }],
      }))
      const sku = productById(linkedProduct)?.sku
      setNotice(result.data.confirmed_in_box
        ? `КИЗ, отсканированный при подборе, подтверждён в коробе ${target.code} · ${sku}. Количество и число кодов прежние.`
        : result.data.already_linked ? `КИЗ уже в коробе ${target.code} — новой единицы нет.`
          : `КИЗ привязан к единице ${sku} в коробе ${target.code}${lastProductBefore && lastProductBefore !== linkedProduct ? ` (последним сканировали ${productById(lastProductBefore)?.sku} — код относится к ${sku} по GTIN)` : ''}.`)
      playScanSuccess()
      if (prefsNow.reprintChz && !result.data.already_linked) {
        try {
          demoPrint(copiesJobs('kiz', `fbo:${mutationId}:copy`, normalizeFbsChzCopies(prefsNow.reprintChzCopies), { title: `КИЗ ${shortCis(code)}`, productId: linkedProduct, cis: code }))
        } catch { /* ошибка показана в панели */ }
      }
      changed()
      return
    }
    const product = productByBarcode(code)
    if (!product) {
      playScanError()
      return setError(`Штрихкод ${code} — не товар этой отгрузки и не короб`)
    }
    lastProduct.current = product.id
    unitConsumed.current = false
    setUi((currentUi) => ({ packLastProduct: product.id, packExpanded: { ...currentUi.packExpanded, [product.id]: true } }))
    if (!current) {
      playScanError()
      return setError(<>Нет открытого короба — создайте короб. <Button size="small" onClick={() => void createBox()} data-testid="fbo-pack-create-box">Создать короб</Button></>)
    }
    const mutationId = newKey()
    const result = await api(`${base(shipmentId)}/boxes/${current.id}/scan`, {
      method: 'POST', body: JSON.stringify({ barcode: code, product_id: product.id, pick_from_storage: false, mutation_id: mutationId }),
    })
    if (!result.ok) {
      playScanError()
      return setError(errorText(result.data))
    }
    setUi((currentUi) => ({ newKiz: null, packUndo: [...currentUi.packUndo, { kind: 'unit', shipmentId, boxId: current.id, productId: product.id }] }))
    setNotice(`+1 упаковано: ${product.sku} → ${current.code}`)
    playScanSuccess()
    changed()
    try {
      if (prefsNow.printQr) {
        demoPrint([{ key: `fbo:${mutationId}:barcode`, kind: 'barcode', title: `ШК ${product.barcode}`, productId: product.id, copy: 1 }])
      }
      if (prefsNow.printChz && product.honestSign) {
        const issued = await api(`${base(shipmentId)}/boxes/${current.id}/print-marking`, { method: 'POST', body: JSON.stringify({ product_id: product.id, mutation_id: `${mutationId}:chz` }) })
        if (!issued.ok) {
          setError(errorText(issued.data))
        } else {
          const cis = String(issued.data.cis_code)
          setUi((currentUi) => ({ newKiz: cis, packUndo: [...currentUi.packUndo, { kind: 'kiz', shipmentId, cis }] }))
          changed()
          demoPrint(copiesJobs('kiz', `fbo:${mutationId}:chz`, normalizeFbsChzCopies(prefsNow.printChzCopies), { title: `КИЗ ${shortCis(cis)}`, productId: product.id, cis }))
        }
      }
    } catch { /* ошибка печати показана; единица остаётся упакованной */ }
  }

  const intake = useScanIntake({ enabled: true, onScan: handle })
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape' && ui.printError) setUi({ printError: null }) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])
  const closeCurrent = async () => {
    if (!current) return
    await api(`${base(shipmentId)}/boxes/${current.id}/close`, { method: 'POST' })
    const next = getFbo().boxes.filter((box) => box.shipmentId === shipmentId && !box.closed).sort((a, b) => a.createdAt - b.createdAt)[0]
    setUi((currentUi) => ({ currentBox: { ...currentUi.currentBox, [shipmentId]: next?.id ?? '' } }))
    setNotice(next ? `Короб ${current.code} закрыт. Текущий — ${next.code}.` : `Короб ${current.code} закрыт. Открытых коробов нет — создайте короб.`)
    changed()
  }
  const undo = async () => {
    const last = ui.packUndo.at(-1)
    if (!last) return
    setUi((currentUi) => ({ packUndo: currentUi.packUndo.slice(0, -1) }))
    if (last.kind === 'kiz') await api(`${base(shipmentId)}/marking-codes/${encodeURIComponent(last.cis)}`, { method: 'DELETE' })
    else await api(`${base(shipmentId)}/boxes/${last.boxId}/unpack-last`, { method: 'POST', body: JSON.stringify({ product_id: last.productId }) })
    setNotice(last.kind === 'kiz' ? 'Отменено: КИЗ отвязан, единица осталась упакованной' : 'Отменено: единица вынута из короба и снова числится подобранной')
    changed()
  }
  const retryPrint = () => {
    const pending = ui.printError?.jobs ?? []
    const prefsNow = prefsRef.current
    // WMS-643: снятая после сбоя галка больше не печатает.
    const allowed = pending.filter((job) => (job.kind === 'barcode' ? prefsNow.printQr : (prefsNow.printChz || prefsNow.reprintChz)))
    setUi({ printError: null })
    try { demoPrint(allowed) } catch { /* снова недоступен */ }
  }
  if (isBaseline()) return null
  return (
    <Box ref={intake.bindRoot} data-testid="fbo-pack-scan"
      sx={{ px: 2, py: 1.5, border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'action.hover' }}>
      <Stack direction="row" spacing={1.5} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <TextField size="small" value={value} autoComplete="off" placeholder="Сканируйте ШК товара или ЧЗ"
          onChange={(event) => setValue(event.target.value)} sx={{ flex: '1 1 260px', minWidth: 220 }}
          onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); intake.submit(value); setValue('') } }}
          slotProps={{ htmlInput: { 'data-testid': 'fbo-pack-scan-input' } }} />
        <Toggles value={prefs} qrLabel="Печатать ШК" onChange={(next) => { setPrefs(next); savePrefs(next) }}
          undo={{ disabled: state.packUndo.length === 0, onClick: () => void undo() }} />
        <LabelSizeSelect value={labelSizeId} onChange={(size) => setLabelSizeId(size.id)} />
        <Typography variant="body2" sx={{ minWidth: 150 }} data-testid="fbo-pack-current-box">
          {current ? <>Короб: <strong>{current.code}</strong>{current.closed ? ' (закрыт)' : ''}</> : 'Нет открытого короба'}
        </Typography>
        {current && !current.closed ? <Button size="small" variant="outlined" onClick={() => void closeCurrent()} data-testid="fbo-pack-close-box">Закрыть короб</Button> : null}
        {!current ? <Button size="small" variant="outlined" onClick={() => void createBox()}>Создать короб</Button> : null}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
        {intake.listening ? 'Сканер активен: ШК товара — +1 в текущий короб; следующий ЧЗ — к этой единице (необязательно); ШК короба — сменить текущий.' : 'Сканер на паузе: открыто окно.'}
      </Typography>
      {notice ? <Alert severity="success" sx={{ mt: 1 }} data-testid="fbo-pack-scan-notice">{notice}</Alert> : null}
      {error ? <Alert severity="error" sx={{ mt: 1 }} data-testid="fbo-pack-scan-error">{error}</Alert> : null}
      {state.printError ? (
        <Alert severity="error" sx={{ mt: 1 }} data-testid="fbo-pack-print-error"
          action={<Button color="inherit" size="small" onClick={retryPrint}>Повторить печать</Button>}>
          {state.printError.text} Единица остаётся упакованной. Esc — снять задание.
        </Alert>
      ) : null}
      {state.printNotice ? (
        <Alert severity="info" icon={<PrintOutlined fontSize="inherit" />} sx={{ mt: 1 }} data-testid="fbo-pack-print-notice"
          action={<LabelPreviewButton job={state.printNotice.job} size={resolveLabelSize(labelSizeId)} />}>
          {state.printNotice.text}
        </Alert>
      ) : null}
    </Box>
  )
}

function LabelPreviewButton({ job, size }: { job: PrintJob; size: LabelSize }) {
  const [html, setHtml] = useState<string | null>(null)
  const open = async () => {
    const product = productById(job.productId)!
    if (job.kind === 'barcode') {
      setHtml(buildProductThermalLabelDocument({
        product_name: product.name, sku_code: product.sku, wb_vendor_code: product.vendorCode, wb_size: product.size,
        wb_color: product.color, seller_name: 'Демо селлер', barcode: product.barcode,
      }, 1, renderBarcodeDataUrl(product.barcode, { variant: 'thermal58' }), undefined, size))
      return
    }
    const cis = job.cis ?? ''
    setHtml(`<!doctype html><html><head><meta charset="utf-8"><style>${buildTapePageCss(size)}</style></head><body>${buildCzLabelHtml(cis, await renderDataMatrixDataUrl(cis))}</body></html>`)
  }
  return (
    <>
      <Button color="inherit" size="small" onClick={() => void open()} data-testid="fbo-pack-print-preview">Предпросмотр</Button>
      <Dialog open={html !== null} onClose={() => setHtml(null)} maxWidth="sm">
        <DialogTitle>Предпросмотр этикетки · макет</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Та же разметка, что печатает WMS. В макете задание в WMS Print не создаётся.
          </Typography>
          {html ? <iframe title="Этикетка" srcDoc={html} style={{ width: `${size.widthMm * 4}px`, height: `${size.heightMm * 4 + 20}px`, border: '1px solid #ccc', background: '#fff' }} /> : null}
        </DialogContent>
        <DialogActions><Button onClick={() => setHtml(null)}>Закрыть</Button></DialogActions>
      </Dialog>
    </>
  )
}

// ─── «Упаковка»: вложенность КИЗ под строкой товара (R14, R17, R20) ───

type TaskLineLike = { product_id: string; qty_total: number; qty_done: number; sku_code: string }

export function FboPackExpand({ line }: { line: TaskLineLike }) {
  const state = useUi()
  if (isBaseline()) return null
  const open = Boolean(state.packExpanded[line.product_id])
  return (
    <IconButton size="small" aria-label={`КИЗ: ${line.sku_code}`} aria-expanded={open} data-testid="fbo-pack-kiz-expand"
      onClick={() => setUi((current) => ({ packExpanded: { ...current.packExpanded, [line.product_id]: !open } }))}>
      <ExpandMoreOutlined fontSize="small" sx={{ transform: open ? 'rotate(180deg)' : undefined }} />
    </IconButton>
  )
}

export const fboPackRowSx = (line: TaskLineLike) => (!isBaseline() && ui.packLastProduct === line.product_id ? {
  backgroundColor: (theme: { palette: { success: { main: string } } }) => alpha(theme.palette.success.main, 0.16),
  boxShadow: (theme: { palette: { success: { main: string } } }) => `inset 0 0 0 1px ${alpha(theme.palette.success.main, 0.6)}`,
} : {})

export function FboPackNested({ line, colSpan }: { line: TaskLineLike; colSpan: number }) {
  const fbo = useFbo()
  const state = useUi()
  const [prefs] = useState(loadPrefs)
  if (isBaseline()) return null
  const shipmentId = activeShipmentId()
  const links = fbo.links.filter((link) => link.shipmentId === shipmentId && link.productId === line.product_id).sort((a, b) => a.at - b.at)
  const boxed = boxedQty(fbo, shipmentId, line.product_id)
  const open = Boolean(state.packExpanded[line.product_id])
  const boxCode = (boxId: string | null) => fbo.boxes.find((box) => box.id === boxId)?.code
  const reprint = (cis: string) => {
    try {
      demoPrint(copiesJobs('kiz', `fbo:reprint:${cis}:${newKey()}`, normalizeFbsChzCopies(loadPrefs().reprintChzCopies ?? prefs.reprintChzCopies), { title: `КИЗ ${shortCis(cis)}`, productId: line.product_id, cis }))
    } catch { /* показано в панели */ }
  }
  return (
    <TableRow>
      <TableCell colSpan={colSpan} sx={{ py: '0 !important', borderBottom: open ? undefined : 'none' }}>
        <Collapse in={open} unmountOnExit>
          <Box sx={{ py: 1, pl: 5 }} data-testid={`fbo-pack-nested-${line.product_id}`}>
            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
              Упаковано {boxed} из {line.qty_total} · с КИЗ {links.length}
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>КИЗ необязателен</Typography>
            </Typography>
            {links.length ? (
              <Table size="small" aria-label={`КИЗ: ${line.sku_code}`}>
                <TableBody>
                  {links.map((link) => {
                    const isNew = state.newKiz === link.cis
                    const source = sourceById(link.sourceId)
                    const cell = cells.find((one) => one.id === link.cellId)
                    return (
                      <TableRow key={link.cis} data-testid="fbo-pack-kiz-row" data-kiz-state={isNew ? 'new' : 'saved'} sx={kizRowSx(isNew)}>
                        <TableCell sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12.5, wordBreak: 'break-all' }}>{link.cis}</TableCell>
                        <TableCell sx={{ width: 170, whiteSpace: 'nowrap' }}>{boxCode(link.boxId) ? `Короб ${boxCode(link.boxId)}` : 'Короб не указан'}</TableCell>
                        <TableCell sx={{ width: 190, color: 'text.secondary' }}>
                          {source ? `Подбор: ${source.code}` : cell ? `Подбор: ${cell.code}` : link.printed ? 'Напечатан при упаковке' : 'Отсканирован при упаковке'}
                        </TableCell>
                        <TableCell sx={{ width: 150, color: 'text.secondary', whiteSpace: 'nowrap' }}>{link.intakeDoc ? `Приёмка ${link.intakeDoc}` : 'Приёмка не указана'}</TableCell>
                        <TableCell align="right" sx={{ width: 170, whiteSpace: 'nowrap' }}>
                          <Button size="small" startIcon={<PrintOutlined fontSize="small" />} onClick={() => reprint(link.cis)} data-testid="fbo-pack-kiz-reprint">Перепечатать</Button>
                          <Tooltip title="Убрать КИЗ (единица остаётся упакованной)">
                            <IconButton size="small" aria-label={`Убрать КИЗ ${link.cis}`} data-testid="fbo-pack-kiz-remove"
                              onClick={() => { void api(`${base(shipmentId)}/marking-codes/${encodeURIComponent(link.cis)}`, { method: 'DELETE' }).then(changed) }}>
                              <CloseOutlined fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            ) : (
              <Typography variant="caption" color="text.secondary">КИЗ пока не сканировали — после ШК можно отсканировать ЧЗ этой единицы.</Typography>
            )}
          </Box>
        </Collapse>
      </TableCell>
    </TableRow>
  )
}

/** Где лежит/вернётся единица: тара или ячейка источника подбора. */
function placeText(cellId: string | null, sourceId: string | null): string {
  const source = sourceById(sourceId)
  if (source) return `${source.kind === 'pallet' ? 'Палету' : 'Короб'} ${source.code}`
  return cells.find((cell) => cell.id === cellId)?.code ? `ячейку ${cells.find((cell) => cell.id === cellId)!.code}` : 'источник подбора'
}

/** R28: «Убрать» у строки товара в карточке короба — конкретная единица и место возврата. */
export function FboBoxLineRemove({ boxId, line }: { boxId: string; line: { id: string; product_id: string; quantity: number } }) {
  const fbo = useFbo()
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  if (isBaseline()) return null
  const shipmentId = activeShipmentId()
  const links = fbo.links.filter((link) => link.shipmentId === shipmentId && link.productId === line.product_id && link.boxId === boxId)
  const plain = line.quantity - links.length
  const plainSource = returnSourceFor(fbo, shipmentId, line.product_id)
  const places = pickSourcesOf(fbo, shipmentId, line.product_id)
  const remove = async (cis: string | null, place: { cellId: string; sourceId: string | null } | null) => {
    setAnchor(null)
    const result = await api(`${base(shipmentId)}/boxes/${boxId}/lines/${encodeURIComponent(line.id)}/remove`, {
      method: 'POST', body: JSON.stringify({ quantity: 1, marking_code_id: cis, mutation_id: newKey(),
        ...(place ? { return_to: { storage_location_id: place.cellId, container_id: place.sourceId } } : {}) }),
    })
    if (!result.ok) return setMessage(errorText(result.data))
    const to = result.data.returned_to as { storage_location_id: string; container_id: string | null }
    setMessage(`Убрано 1 шт.${cis ? ` (КИЗ ${shortCis(cis)} свободен)` : ''} — возвращено в ${placeText(to.storage_location_id, to.container_id)}${result.data.source_known ? ' (источник известен)' : ' (место выбрано оператором)'}`)
    changed()
  }
  return (
    <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', ml: 1, gap: 0.5 }}>
      <Button size="small" onClick={(event) => setAnchor(event.currentTarget)} data-testid={`fbo-box-line-remove-${line.id}`}>Убрать</Button>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        {links.flatMap((link) => link.cellId ? [(
          <MenuItem key={link.cis} onClick={() => void remove(link.cis, null)}>
            КИЗ {shortCis(link.cis)} → вернуть в {placeText(link.cellId, link.sourceId)} (источник известен)
          </MenuItem>
        )] : places.map((place) => (
          <MenuItem key={`${link.cis}-${place.cellId}-${place.sourceId}`} onClick={() => void remove(link.cis, place)}>
            КИЗ {shortCis(link.cis)} — источник неизвестен → вернуть в {placeText(place.cellId, place.sourceId)}
          </MenuItem>
        )))}
        {plain > 0 ? places.map((place) => {
          const suggested = plainSource && plainSource.cellId === place.cellId && plainSource.sourceId === place.sourceId
          return (
            <MenuItem key={`plain-${place.cellId}-${place.sourceId}`} onClick={() => void remove(null, place)}>
              Без КИЗ → вернуть в {placeText(place.cellId, place.sourceId)}{suggested ? ' (предложено)' : ''}
            </MenuItem>
          )
        }) : null}
      </Menu>
      {message ? <Typography variant="caption" color="text.secondary" data-testid="fbo-box-line-remove-result">{message}</Typography> : null}
    </Box>
  )
}

/** R30: известен ли состав КИЗ тары источника подбора. */
export function SourceKizInfo({ containerId }: { containerId: string }) {
  const fbo = useFbo()
  if (isBaseline()) return null
  const entries = Object.entries(fbo.known).filter(([, entry]) => entry.sourceId === containerId)
  const certain = entries.filter(([, entry]) => entry.certain).map(([cis]) => cis)
  const maybe = entries.filter(([, entry]) => !entry.certain).map(([cis]) => cis)
  return (
    <Tooltip title={entries.length
      ? `Точно: ${certain.join(', ') || '—'}. Возможно (после снятия без кода): ${maybe.join(', ') || '—'}. Остальные единицы — коды неизвестны.`
      : 'Приёмка хранит КИЗ без короба, поэтому коды в этой таре WMS не известны. Видны только коды, отсканированные при снятии.'}>
      <Typography variant="caption" color="text.secondary" data-testid="pick-source-kiz-known">
        {entries.length ? `КИЗ в таре: точно ${certain.length}, возможно ${maybe.length}` : 'состав КИЗ тары неизвестен'}
      </Typography>
    </Tooltip>
  )
}

/** Отметка текущего короба в существующем блоке «Короба». */
export function CurrentBoxChip({ boxId }: { boxId: string }) {
  const fbo = useFbo()
  useUi()
  if (isBaseline()) return null
  const box = fbo.boxes.find((one) => one.id === boxId)
  if (!box) return null
  if (box.whole) return <Chip size="small" variant="outlined" label="Взят целиком" sx={{ ml: 1 }} />
  return currentBoxOf(box.shipmentId, fbo.boxes)?.id === boxId ? <Chip size="small" color="success" label="Текущий" sx={{ ml: 1 }} data-testid="fbo-pack-current-chip" /> : null
}

// ─── Пропуск рядом с «Скачать XLSX для WB» (R25) ───

export function FboPassField({ shipmentId }: { shipmentId: string }) {
  const fbo = useFbo()
  const input = useRef<HTMLInputElement | null>(null)
  const [error, setError] = useState<string | null>(null)
  if (isBaseline()) return null
  const pass = fbo.passes.find((one) => one.shipmentId === shipmentId)
  const upload = async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch(`${base(shipmentId)}/pass`, { method: 'PUT', body: form, headers: { Authorization: authHeaders.Authorization } })
    setError(response.ok ? null : 'Не удалось прикрепить пропуск')
  }
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }} data-testid="fbo-pass">
      <Typography variant="body2" color="text.secondary">Пропуск:</Typography>
      {pass ? (
        <Button size="small" component="a" href={pass.dataUrl} download={pass.filename} data-testid="fbo-pass-download">{pass.filename}</Button>
      ) : <Typography variant="body2" color="text.secondary">не прикреплён</Typography>}
      <Button size="small" variant="outlined" onClick={() => input.current?.click()} data-testid="fbo-pass-upload">{pass ? 'Заменить' : 'Прикрепить'}</Button>
      <input ref={input} type="file" accept="application/pdf,image/*" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = '' }} />
      <Typography variant="caption" color="text.secondary">не блокирует «Завершить»; виден селлеру</Typography>
      {error ? <Typography variant="caption" color="error.main">{error}</Typography> : null}
    </Stack>
  )
}

// ─── Справочник демонстрационных кодов: сами коды нужно сканировать сканером ───

type DemoScanCode = { title: string; code: string; kind: 'barcode' | 'datamatrix'; detail?: string }

const cellScanCodes: DemoScanCode[] = [
  { title: 'Ячейка А-1-1', code: 'LOC-A11', kind: 'barcode', detail: 'Короба INB-DEMO-001 и INB-DEMO-002' },
  { title: 'Ячейка А-1-2', code: 'LOC-A12', kind: 'barcode', detail: 'Палета PLT-DEMO-01' },
]
const sourceScanCodes: DemoScanCode[] = [
  { title: 'Короб приёмки 1', code: 'INB-DEMO-001', kind: 'barcode', detail: 'Футболки, размеры 48 и 50' },
  { title: 'Короб приёмки 2', code: 'INB-DEMO-002', kind: 'barcode', detail: 'Футболка 48 и носки' },
  { title: 'Палета', code: 'PLT-DEMO-01', kind: 'barcode', detail: 'Ячейка А-1-2 · футболка 50' },
]
const productScanCodes: DemoScanCode[] = products.map((product) => ({
  title: `${product.sku} · размер ${product.size}`,
  code: product.barcode,
  kind: 'barcode',
  detail: product.honestSign ? 'КИЗ можно отсканировать отдельно' : 'Без обязательного ЧЗ',
}))
const markingScanCodes: DemoScanCode[] = [
  { title: 'КИЗ футболки 48 · приёмка 000041', code: kizFor(products[0], 'P1A0001'), kind: 'datamatrix' },
  { title: 'КИЗ футболки 48 · отдельный', code: kizFor(products[0], 'P1X0001'), kind: 'datamatrix' },
  { title: 'КИЗ футболки 50 · приёмка 000041', code: kizFor(products[1], 'P2A0001'), kind: 'datamatrix' },
]

function DemoScanCodeCard({ item }: { item: DemoScanCode }) {
  const [image, setImage] = useState<string | null>(null)
  useEffect(() => {
    let current = true
    try {
      if (item.kind === 'barcode') setImage(renderBarcodeDataUrl(item.code, { variant: 'storageCell' }))
      else void renderDataMatrixDataUrl(item.code).then((url) => { if (current) setImage(url) })
        .catch(() => { if (current) setImage(null) })
    } catch {
      setImage(null)
    }
    return () => { current = false }
  }, [item.code, item.kind])
  return (
    <Box sx={{ minWidth: 0, border: 1, borderColor: 'divider', borderRadius: 1, p: 0.75, bgcolor: 'background.paper' }}>
      <Typography variant="caption" sx={{ display: 'block', fontWeight: 700, lineHeight: 1.25 }}>{item.title}</Typography>
      {image ? (
        <Box component="img" src={image} alt={`Штрихкод: ${item.title}`} sx={{ display: 'block', width: item.kind === 'datamatrix' ? 88 : '100%', height: item.kind === 'datamatrix' ? 88 : 40, objectFit: 'contain', mx: item.kind === 'datamatrix' ? 'auto' : 0, my: 0.25, imageRendering: 'pixelated' }} />
      ) : <Box sx={{ height: 40 }} />}
      <Typography variant="caption" component="div" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 10.5, lineHeight: 1.25, overflowWrap: 'anywhere' }}>{item.code}</Typography>
      {item.detail ? <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.25, lineHeight: 1.2 }}>{item.detail}</Typography> : null}
    </Box>
  )
}

function DemoScanCodeGroup({ title, items }: { title: string; items: DemoScanCode[] }) {
  if (!items.length) return null
  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontWeight: 700 }}>{title}</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 0.5 }}>
        {items.map((item) => <DemoScanCodeCard key={item.code} item={item} />)}
      </Box>
    </Box>
  )
}

export function DemoScanCodes() {
  const fbo = useFbo()
  const state = useUi()
  const [open, setOpen] = useState(true)
  const ownBoxes = useMemo(() => fbo.boxes.filter((box) => box.shipmentId === activeShipmentId() && !box.whole), [fbo.boxes])
  if (isBaseline()) return null
  const boxCodes: DemoScanCode[] = ownBoxes.map((box) => ({ title: `Короб отгрузки ${box.closed ? '· закрыт' : ''}`, code: box.code, kind: 'barcode' }))
  return (
    <>
      <Paper elevation={6} sx={{ position: 'fixed', right: 12, bottom: 76, zIndex: 2000, width: open ? 420 : 'auto', maxWidth: 'calc(100vw - 24px)', p: 1.25, opacity: 0.98 }} data-testid="demo-scan-codes">
        <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle2">Коды для сканера</Typography>
          <Button size="small" onClick={() => setOpen(!open)}>{open ? 'Свернуть' : 'Показать коды'}</Button>
        </Stack>
        {open ? (
          <Box sx={{ maxHeight: '68vh', overflowY: 'auto', pr: 0.25 }}>
            <Alert severity="info" icon={false} sx={{ mt: 0.5, py: 0, '& .MuiAlert-message': { py: 0.5 } }}>
              Учебные данные. Сканируйте изображения ниже: состояние хранится отдельно в каждом браузере.
            </Alert>
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.75 }}>
              Подбор: ячейка → короб или палета → ШК товара → при желании КИЗ. Для целого короба используйте кнопку рядом с выбранным источником.
            </Typography>
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 0.35 }}>
              Упаковка: создайте короб на вкладке «Упаковка», затем сканируйте ШК товара и при желании его КИЗ; ШК короба отгрузки выбирает текущий короб.
            </Typography>
            <DemoScanCodeGroup title="Ячейки" items={cellScanCodes} />
            <DemoScanCodeGroup title="Короба и палета в ячейках" items={sourceScanCodes} />
            <DemoScanCodeGroup title="Товары · ШК" items={productScanCodes} />
            <DemoScanCodeGroup title="Честный знак · КИЗ необязателен" items={markingScanCodes} />
            <DemoScanCodeGroup title="Короба отгрузки · создайте на вкладке «Упаковка»" items={boxCodes} />
            <Stack direction="row" spacing={0.5} sx={{ mt: 0.75, alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="caption" color="text.secondary">
                {products.map((product) => `${product.sku}: ${fbo.stockTotal[product.id]}`).join(' · ')} шт.
              </Typography>
              <Button size="small" onClick={() => {
                resetFbo()
                setUi({ newKiz: null, packLastProduct: null, packExpanded: {}, currentBox: {}, printLog: [], printNotice: null, printError: null, packUndo: [] })
                changed()
              }} data-testid="demo-reset">Сбросить данные этого браузера</Button>
            </Stack>
          </Box>
        ) : null}
      </Paper>
      <Snackbar open={state.nativePrintBlocked > 0} autoHideDuration={3500} onClose={() => setUi({ nativePrintBlocked: 0 })}
        message="Макет: печать перехвачена, на принтер ничего не отправлено" />
    </>
  )
}
