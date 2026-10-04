import { Box, IconButton, LinearProgress, Paper, Stack, Tooltip, Typography } from '@mui/material'
import UndoOutlinedIcon from '@mui/icons-material/UndoOutlined'
import { useEffect, useRef, useState } from 'react'
import { RejectedScan, createSortingScanner, emptyScanContext, type ScanContext, type UndoOutcome } from './sortingScan'
import {
  ActionGroup,
  AppDialog,
  NumberInput,
  PrimaryAction,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  SelectInput,
} from '../../../ui-kit'
import { CreateCellDialog } from '../warehouse-map/WarehouseMapToolbar'
import type { LabelSize } from '../../../utils/labelSize'
import { BoxLabelPrintDialog } from '../../../components/BoxLabelPrintDialog'
import { randomId } from '../../../utils/randomId'
import { ObjectsTree } from './ObjectsTree'
import { PlacedByCells } from './PlacedByCells'
import {
  CELLS,
  INITIAL_LINES,
  INITIAL_OBJECTS,
  PRODUCTS,
  KIND_TITLE,
  cellRef,
  objRef,
  productById,
  type Cell,
  type GoodsLine,
  type Holder,
  type Product,
  whereIs,
  type ObjKind,
  type WarehouseObject,
} from './objectsStub'
import {
  canPut,
  destinationsFor,
  objectTitle,
  unplacedRows,
  type Carried,
  type ObjectRow,
} from './objectsRows'
import { placementFailureMessage } from './pendingPlacement'
import { RejectedUndo, readUndoHistory, undoRefusalText, writeUndoHistory, type UndoEntry } from './sortingUndo'

// Раскладка объектами.
//
// Порядок работы обратный привычному: сначала собираем объект — товар в короб,
// короб на палету, — и только готовый объект ставим на полку. Где лежит товар,
// отдельно не хранится: это вычисляется по цепочке держателей, поэтому «что в
// коробе» и «где короб» не могут разъехаться. Это одно знание.
//
// WMS-650 (утверждённый макет): в основном списке слева только неразложенное —
// поставленное из него уходит; справа, в панели «Ячейки склада», под каждой
// ячейкой видно, что на ней стоит. Рядом с полем сканера — стрелка «назад»,
// отменяющая последнее подтверждённое действие раскладки. Открытая ячейка,
// открытая тара и строка последнего действия подсвечены.

/** Что сервер ответил на скан товара — экран пишет итог и подсвечивает строку. */
export type ProductScanOutcome = {
  productId: string | null
  /** Строка, куда легла штука. */
  targetLineId: string | null
  /** Строка, откуда её взяли: вернётся после «назад». */
  sourceLineId: string | null
  /** Сколько этого товара осталось россыпью в документе. */
  looseLeft: number
}

/**
 * Экран работает и от сервера, и от заглушки.
 *
 * Данные приходят пропсами, без них берутся выдуманные: превью макета обязано
 * открываться без сервера, иначе посмотреть на экран можно будет только после
 * готового бэка, а смотреть надо раньше.
 */
type SortingScreenProps = {
  onNote: (note: string) => void
  initialObjects?: WarehouseObject[]
  initialLines?: GoodsLine[]
  products?: Product[]
  initialCells?: Cell[]
  /** Подпись под заголовком: что за документ раскладываем. */
  purpose?: string
  /** Имя склада для диалога создания ячейки. */
  warehouseName?: string
  /** Завести ячейку на сервере. Без него экран заводит её только у себя. */
  onCreateCell?: (code: string) => void
  /** Напечатать штрихкод. Без него печать остаётся заглушкой превью. */
  onPrint?: (title: string, barcode: string, size: LabelSize) => void
  /** Уйти с экрана. Без него «Закрыть» остаётся заглушкой превью. */
  onClose?: () => void
  /** Завести тару на сервере. Без него тара появляется только в превью. */
  onCreateObject?: (kind: ObjKind) => void
  /**
   * Каждая постановка на полку уходит на сервер сразу.
   *
   * Тогда «Сохранить» и «Завершить» сохранять нечего: они бы только делали вид.
   * Экран честно говорит об этом вместо того, чтобы показывать живую кнопку,
   * которая ничего не делает.
   */
  savedImmediately?: boolean
  scanStorageKey?: string
  onProductScan?: (barcode: string, context: ScanContext, operationId: string) => Promise<ProductScanOutcome | string | void>
  onScanIdle?: () => void
  /**
   * Поставить объект или товар. Без него экран двигает только себя.
   * Отдаёт operation_id, с которым сервер подтвердил действие.
   */
  onPlace?: (payload: {
    kind: ObjKind | 'product'
    id: string
    cellId: string | null
    toId: string | null
    qty: number
    /** Holder before the move; only loose stock may be replayed after a lost reply. */
    sourceHolder: Holder
    operationId?: string
  }) => Promise<string | void>
  /** «Назад»: отменить подтверждённое действие. Без него стрелка не активна. */
  onUndo?: (targetOperationId: string, undoOperationId: string) => Promise<void>
  /** Где вкладка хранит историю «назад» (документ + сотрудник, решение Д1). */
  undoStorageKey?: string
}

/** Цепочка тар от строки вверх — чтобы раскрыть путь к ней. */
function chainTo(holder: Holder, objects: WarehouseObject[]): string[] {
  const ids: string[] = []
  let cursor = holder
  for (let step = 0; cursor && cursor.startsWith('obj:') && step < 20; step += 1) {
    const id = cursor.slice(4)
    ids.push(id)
    cursor = objects.find((one) => one.id === id)?.holder ?? null
  }
  return ids
}

/** Строка товара по месту: после перечитывания склада у неё другой id. */
const goodsFocus = (productId: string, holder: Holder) => `g:${productId}|${holder ?? ''}`

function resolveFocus(focus: string | null, lines: GoodsLine[]): string | null {
  if (!focus || !focus.startsWith('g:')) return focus
  const [productId, holder] = focus.slice(2).split('|')
  const line = lines.find((one) => one.productId === productId && (one.holder ?? '') === holder)
  return line ? `l-${line.id}` : null
}

/** Род для подписи: «Короб положен», «Палета положена», «Грузоместо положено». */
function verb(kind: ObjKind, masculine: string, feminine: string, neuter: string): string {
  return kind === 'pallet' ? feminine : kind === 'cargo_place' ? neuter : masculine
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : placementFailureMessage(error)
}

export function SortingObjectsScreen({
  onNote,
  initialObjects,
  initialLines,
  products: productsProp,
  initialCells,
  onPlace,
  purpose,
  warehouseName,
  onCreateCell,
  onPrint,
  onClose,
  onCreateObject,
  savedImmediately,
  scanStorageKey,
  onProductScan,
  onScanIdle,
  onUndo,
  undoStorageKey,
}: SortingScreenProps) {
  const products = productsProp ?? PRODUCTS
  const [objects, setObjects] = useState<WarehouseObject[]>(initialObjects ?? INITIAL_OBJECTS)
  const [lines, setLines] = useState<GoodsLine[]>(initialLines ?? INITIAL_LINES)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [placedOpen, setPlacedOpen] = useState<Set<string>>(new Set())
  const [carried, setCarried] = useState<Carried | null>(null)
  const [scanContext, setScanContext] = useState<ScanContext>(() => {
    try {
      const stored = scanStorageKey ? sessionStorage.getItem(scanStorageKey) : null
      if (stored) {
        const parsed = JSON.parse(stored) as ScanContext
        if (initialCells?.some((one) => one.id === parsed.cellId)) {
          return { cellId: parsed.cellId, objectId: initialObjects?.some((one) => one.id === parsed.objectId && whereIs(one.holder, initialObjects, initialCells).cell?.id === parsed.cellId) ? parsed.objectId : null }
        }
      }
    } catch { /* Selection persistence is optional; stock writes are not. */ }
    return emptyScanContext
  })
  const activeCellId = scanContext.cellId
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [pendingScans, setPendingScans] = useState({ count: 0, paused: false })
  const [history, setHistory] = useState<UndoEntry[]>(() => readUndoHistory(undoStorageKey))
  const [focus, setFocus] = useState<string | null>(null)
  const [inflightCount, setInflightCount] = useState(0)
  const [undoing, setUndoing] = useState(false)
  /** Каждый новый отказ — повод вернуть поле сканера в окно, даже с тем же текстом. */
  const [errorTick, setErrorTick] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const field = useRef<HTMLDivElement>(null)
  const panelScroll = useRef<HTMLDivElement>(null)
  const dialogWasOpen = useRef(false)
  const [asking, setAsking] = useState<Carried | null>(null)
  const [askTarget, setAskTarget] = useState('')
  const [askQty, setAskQty] = useState<number | null>(null)
  const [created, setCreated] = useState(0)
  // Держим не только подпись, но и штрихкод самой строки: у товара его негде
  // взять поиском по таре и ячейкам, а печать ШК товара из сортировки нужна.
  const [printing, setPrinting] = useState<{ title: string; barcode: string } | null>(null)
  const [cellDialogOpen, setCellDialogOpen] = useState(false)
  const [extraCells, setExtraCells] = useState<typeof CELLS>([])

  const cells = [...(initialCells ?? CELLS), ...extraCells]
  const activeCell = cells.find((one) => one.id === activeCellId) ?? null
  const activeObject = objects.find((one) => one.id === scanContext.objectId) ?? null
  useEffect(() => { if (initialObjects) setObjects(initialObjects) }, [initialObjects])
  useEffect(() => { if (initialLines) setLines(initialLines) }, [initialLines])

  // Сканер и действия экрана читают одни и те же свежие данные: следующий скан
  // из очереди может прийти раньше, чем React перерисует подтверждённую постановку.
  const live = useRef({ objects, lines, cells, products, onPlace, onProductScan, onScanIdle, onUndo })
  live.current = { objects, lines, cells, products, onPlace, onProductScan, onScanIdle, onUndo }
  const ctxRef = useRef<ScanContext>(scanContext)
  const historyRef = useRef<UndoEntry[]>(history)
  /** Действия «+»/перетаскивания, ещё не подтверждённые сервером. */
  const inflight = useRef(new Set<Promise<unknown>>())
  /** Строки, по которым запрос уже ушёл: двойной клик не шлёт второй (R17). */
  const busy = useRef(new Set<string>())
  const undoBusy = useRef(false)
  const confirming = useRef(false)

  function saveHistory(next: UndoEntry[]) {
    historyRef.current = next
    setHistory(next)
    writeUndoHistory(undoStorageKey, next)
  }
  function remember(entry: UndoEntry) {
    saveHistory([...historyRef.current, entry].slice(-200))
  }
  function forget(operationId: string) {
    saveHistory(historyRef.current.filter((one) => one.operationId !== operationId))
  }

  function placeLabel(target: Holder): string {
    if (!target) return 'россыпь'
    if (target.startsWith('cell:')) {
      const cell = live.current.cells.find((one) => cellRef(one.id) === target)
      return cell ? `ячейку ${cell.code}` : 'ячейку'
    }
    const object = live.current.objects.find((one) => objRef(one.id) === target)
    return object ? objectTitle(object) : 'объект'
  }

  async function undoLast(): Promise<UndoOutcome | null> {
    try {
      // «Назад» не обгоняет «+», ушедший раньше него: сначала его ответ.
      await Promise.allSettled([...inflight.current])
      let entry = historyRef.current[historyRef.current.length - 1]
      const send = live.current.onUndo
      if (!entry || !send) return null
      if (!entry.undoOperationId) {
        entry = { ...entry, undoOperationId: randomId() }
        saveHistory([...historyRef.current.slice(0, -1), entry])
      }
      try {
        await send(entry.operationId, entry.undoOperationId!)
      } catch (error) {
        if (error instanceof RejectedUndo) {
          // Отменить это уже нельзя: причина под полем, шаг снят (Д4).
          forget(entry.operationId)
          setFocus(null)
          throw new RejectedScan(undoRefusalText(entry, error.detail, error.message))
        }
        // Сбой сети или сервера: шаг остаётся, повтор пойдёт с тем же id.
        throw new RejectedScan(`Отменить не удалось: ${errorText(error)} Нажмите «назад» ещё раз.`)
      }
      forget(entry.operationId)
      setFocus(entry.focus)
      return { context: entry.before, notice: `Отменено: ${entry.label}` }
    } finally {
      undoBusy.current = false
      setUndoing(false)
    }
  }

  const scannerRef = useRef<ReturnType<typeof createSortingScanner> | null>(null)
  if (!scannerRef.current) {
    scannerRef.current = createSortingScanner(scanContext, {
      data: () => live.current,
      storage: scanStorageKey ? { storage: localStorage, key: `${scanStorageKey}:queue` } : undefined,
      pending: (count, paused) => setPendingScans({ count, paused }),
      idle: () => live.current.onScanIdle?.(),
      place: async (object, cellId, operationId, before) => {
        const title = objectTitle(object)
        const from = whereIs(object.holder, live.current.objects, live.current.cells).cell
        const to = live.current.cells.find((one) => one.id === cellId)
        const send = live.current.onPlace
        if (send) {
          try {
            await send({ kind: object.kind, id: object.id, qty: 1, sourceHolder: object.holder, cellId, toId: null, operationId })
          } catch (error) {
            // Отказ — под полем с названием тары; строка остаётся на месте и подсвечена.
            setFocus(`o-${object.id}`)
            const message = `${title}: ${errorText(error)}`
            throw error instanceof RejectedScan ? new RejectedScan(message) : new Error(message)
          }
        }
        const placed = live.current.objects.map((one) => one.id === object.id ? { ...one, holder: cellRef(cellId) } : one)
        // The next queued scan can run before React renders the confirmed move.
        live.current = { ...live.current, objects: placed }
        setObjects(placed)
        const label = from
          ? `${title} ${verb(object.kind, 'перенесён', 'перенесена', 'перенесено')} с ${from.code} на ${to?.code ?? ''}`
          : `${title} ${verb(object.kind, 'положен', 'положена', 'положено')} на ячейку ${to?.code ?? ''}`
        if (send) remember({ operationId, label, subject: title, before, focus: `o-${object.id}` })
        setFocus(null)
        return label
      },
      product: async (barcode, context, operationId) => {
        const send = live.current.onProductScan
        if (!send) throw new Error('Скан товара доступен в документе приёмки')
        const outcome = await send(barcode, context, operationId)
        if (!outcome || typeof outcome === 'string') return outcome
        const { cells: knownCells, objects: knownObjects, products: knownProducts } = live.current
        const product = knownProducts.find((one) => one.id === outcome.productId)
          ?? knownProducts.find((one) => one.barcode && one.barcode.toLowerCase() === barcode.toLowerCase())
        const name = product?.name ?? 'Товар'
        const tara = context.objectId ? knownObjects.find((one) => one.id === context.objectId) : undefined
        const where = tara ? objectTitle(tara) : `ячейку ${knownCells.find((one) => one.id === context.cellId)?.code ?? ''}`
        remember({
          operationId,
          label: `${name}, 1 шт → ${where}`,
          subject: name,
          before: context,
          focus: outcome.sourceLineId ? `l-${outcome.sourceLineId}` : product ? goodsFocus(product.id, null) : null,
        })
        setFocus(outcome.targetLineId ? `l-${outcome.targetLineId}` : null)
        return `${name}: +1 шт → ${where}. Россыпью осталось ${outcome.looseLeft}`
      },
      undo: undoLast,
      changed: (next) => {
        ctxRef.current = next
        setScanContext(next)
        try { if (scanStorageKey) sessionStorage.setItem(scanStorageKey, JSON.stringify(next)) } catch { /* Optional UI context. */ }
      },
      notice: (message) => { setScanError(null); setScanNotice(message) },
      error: (error) => {
        setScanNotice(null)
        setScanError(error instanceof Error ? error.message : 'Не удалось получить ответ от сервера. Обновите документ для проверки результата.')
        setErrorTick((tick) => tick + 1)
      },
    })
  }
  useEffect(() => { void scannerRef.current?.resume() }, [])

  const focusKey = resolveFocus(focus, lines)
  const openKey = scanContext.objectId ? `o-${scanContext.objectId}` : null
  useEffect(() => {
    const key = openKey ?? focusKey
    if (!key) return
    // Строка основного списка — прокручиваем страницу к ней. Строка панели
    // ячеек — только саму панель: она прилипает к верху экрана, и прокрутка
    // страницы к ней уводила оператора с места действия к началу списка.
    const inMain = root.current?.querySelector(`[data-testid="objects-tree"] [data-row-key="${key}"]`)
    if (inMain) {
      inMain.scrollIntoView({ block: 'nearest', behavior: 'instant' })
      return
    }
    const box = panelScroll.current
    const inPanel = box?.querySelector<HTMLElement>(`[data-row-key="${key}"]`)
    if (!box || !inPanel) return
    const row = inPanel.getBoundingClientRect()
    const frame = box.getBoundingClientRect()
    if (row.top < frame.top || row.bottom > frame.bottom) {
      box.scrollTop += row.top - frame.top - (box.clientHeight - row.height) / 2
    }
  }, [openKey, focusKey])
  // Отказ и любой результат пишутся под полем сканера (R16): на длинном списке
  // поле должно оказаться в окне, иначе «нажал — ничего не произошло».
  useEffect(() => {
    if (errorTick) field.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' })
  }, [errorTick])
  // После окна «Куда положить» сканер снова слушает: фокус — в поле сканера.
  // Ждём, пока окно закроется и вернёт фокус кнопке, которой его открыли.
  useEffect(() => {
    if (asking !== null || !dialogWasOpen.current) return
    dialogWasOpen.current = false
    const timer = setTimeout(() => {
      field.current?.querySelector<HTMLInputElement>('input')?.focus({ preventScroll: true })
    }, 350)
    return () => clearTimeout(timer)
  }, [asking])

  /** Выполнить действие «+»/перетаскивания/снятия: экран двигает сразу, сервер подтверждает. */
  function run(key: string, action: () => Promise<void>) {
    busy.current.add(key)
    const done = action().finally(() => {
      busy.current.delete(key)
      inflight.current.delete(done)
      setInflightCount(inflight.current.size)
    })
    inflight.current.add(done)
    setInflightCount(inflight.current.size)
  }

  function targetParts(target: Holder): { cellId: string | null; toId: string | null } {
    if (!target) return { cellId: null, toId: null }
    if (target.startsWith('cell:')) return { cellId: target.slice(5), toId: null }
    return { cellId: null, toId: target.slice(4) }
  }

  function moveGoods(line: GoodsLine, qty: number, target: Holder) {
    const key = `l-${line.id}`
    if (busy.current.has(key)) return
    // Серверу уходит `line.id` — идентификатор СТРОКИ ОСТАТКА, а не товара:
    // один и тот же товар лежит в разных местах разными строками.
    const name = productById(live.current.products, line.productId).name
    const label = `${name}, ${qty} шт → ${placeLabel(target)}`
    const before = ctxRef.current
    const snapshot = live.current.lines
    const rest = snapshot.filter((one) => one.id !== line.id)
    const left = line.qty - qty
    const twin = rest.find((one) => one.productId === line.productId && one.holder === target)
    const withTarget = twin
      ? rest.map((one) => (one === twin ? { ...one, qty: one.qty + qty } : one))
      : [...rest, { id: `l-${Date.now()}-${line.id}`, productId: line.productId, qty, holder: target }]
    const next = left > 0 ? [...withTarget, { ...line, qty: left }] : withTarget
    live.current = { ...live.current, lines: next }
    setLines(next)
    setFocus(goodsFocus(line.productId, target))
    setScanError(null)
    const send = live.current.onPlace
    if (!send) {
      setScanNotice(label)
      return
    }
    run(key, async () => {
      try {
        const operationId = await send({ kind: 'product', id: line.id, qty, sourceHolder: line.holder, ...targetParts(target) })
        if (operationId) remember({ operationId, label, subject: name, before, focus: `l-${line.id}` })
        setScanNotice(label)
      } catch (error) {
        if (inflight.current.size <= 1) {
          live.current = { ...live.current, lines: snapshot }
          setLines(snapshot)
        }
        setFocus(`l-${line.id}`)
        setScanNotice(null)
        setScanError(`${name}: ${errorText(error)}`)
        setErrorTick((tick) => tick + 1)
      }
    })
  }

  function moveObject(object: WarehouseObject, target: Holder) {
    const key = `o-${object.id}`
    if (busy.current.has(key)) return
    const title = objectTitle(object)
    const label = `${title} → ${placeLabel(target)}`
    const before = ctxRef.current
    const next = live.current.objects.map((one) => (one.id === object.id ? { ...one, holder: target } : one))
    live.current = { ...live.current, objects: next }
    setObjects(next)
    setFocus(key)
    setScanError(null)
    onNote(`${KIND_TITLE[object.kind]} ${object.code} → ${placeLabel(target)}`)
    const send = live.current.onPlace
    if (!send) {
      setScanNotice(label)
      return
    }
    run(key, async () => {
      try {
        const operationId = await send({ kind: object.kind, id: object.id, qty: 1, sourceHolder: object.holder, ...targetParts(target) })
        if (operationId) remember({ operationId, label, subject: title, before, focus: key })
        setScanNotice(label)
      } catch (error) {
        // Строка возвращается туда, где была, и подсвечена; отказ — под полем (R16).
        const restored = live.current.objects.map((one) => (one.id === object.id ? { ...one, holder: object.holder } : one))
        live.current = { ...live.current, objects: restored }
        setObjects(restored)
        setFocus(key)
        setScanNotice(null)
        setScanError(`${title}: ${errorText(error)}`)
        setErrorTick((tick) => tick + 1)
      }
    })
  }

  // Поставленное по умолчанию свёрнуто: короб на ячейке — одна строка, а не десять.
  // Раскрыто то, что открыл сам оператор, плюс открытая сканом тара и путь к строке,
  // которой коснулось последнее действие.
  const focusLine = focusKey ? lines.find((one) => `l-${one.id}` === focusKey) : undefined
  const focusObject = focusKey ? objects.find((one) => `o-${one.id}` === focusKey) : undefined
  const forcedOpen = new Set<string>([
    ...(activeObject ? [activeObject.id, ...chainTo(activeObject.holder, objects)] : []),
    ...(focusLine ? chainTo(focusLine.holder, objects) : []),
    ...(focusObject ? chainTo(focusObject.holder, objects) : []),
  ])
  const placedCollapsed = new Set(
    objects.filter((one) => !placedOpen.has(one.id) && !forcedOpen.has(one.id)).map((one) => one.id),
  )
  const visibleCollapsed = new Set([...collapsed].filter((id) => !forcedOpen.has(id)))
  const mainRows = unplacedRows(objects, lines, products, visibleCollapsed)
  const mainKeys = new Set(mainRows.map((row) => row.key))
  const mainHighlight = openKey && mainKeys.has(openKey)
    ? { key: openKey, kind: 'open' as const }
    : focusKey && mainKeys.has(focusKey)
      ? { key: focusKey, kind: 'touched' as const }
      : null

  const selectCell = (id: string) => { void scannerRef.current?.selectCell(id) }
  const loose = lines.filter((line) => line.holder === null)
  const unplaced = objects.filter((one) => one.holder === null)
  const totalQty = lines.reduce((sum, line) => sum + line.qty, 0)
  const leftQty = lines
    .filter((line) => !whereIs(line.holder, objects, cells).cell)
    .reduce((sum, line) => sum + line.qty, 0)
  const quantitiesByCell = new Map<string, number>()
  for (const line of lines) {
    const id = whereIs(line.holder, objects, cells).cell?.id
    if (id) quantitiesByCell.set(id, (quantitiesByCell.get(id) ?? 0) + line.qty)
  }

  const lastStep = history[history.length - 1]
  const waiting = pendingScans.count > 0 || inflightCount > 0
  const canUndo = Boolean(onUndo) && !undoing && (history.length > 0 || waiting)
  const undoHint = lastStep
    ? `Отменить: ${lastStep.label}`
    : waiting && onUndo
      ? 'Отменить: действие, которое ещё подтверждается'
      : 'Отменять нечего'

  function undo() {
    if (undoBusy.current || !canUndo) return
    undoBusy.current = true
    setUndoing(true)
    void scannerRef.current?.undo()
  }

  function toggle(objectId: string) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(objectId)) next.delete(objectId)
      else next.add(objectId)
      return next
    })
  }

  function togglePlaced(objectId: string) {
    setPlacedOpen((current) => {
      const next = new Set(current)
      if (next.has(objectId)) next.delete(objectId)
      else next.add(objectId)
      return next
    })
  }

  /** Перетащили: контейнер едет целиком, у товара спрашиваем количество. */
  function drop(target: Holder) {
    if (!carried) return
    if (!canPut(carried, target, objects)) {
      setCarried(null)
      return
    }
    if (carried.kind === 'object') {
      moveObject(carried.object, target)
    } else {
      openDialog(carried, target)
    }
    setCarried(null)
  }

  /** Снять с ячейки: уезжает целиком и вместе с содержимым, без вопросов. */
  function takeOffCell(row: ObjectRow) {
    if (row.kind === 'goods') {
      moveGoods(row.line, row.line.qty, null)
      return
    }
    moveObject(row.object, null)
  }

  /** Вынуть наружу: то же окно, но место уже выбрано — россыпь. */
  function takeOut(row: ObjectRow) {
    openDialog(
      row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object },
      null,
    )
  }

  /** Нажали плюс: то же самое, только место выбирается в диалоге. */
  function openDialog(what: Carried, target?: Holder) {
    confirming.current = false
    dialogWasOpen.current = true
    setAsking(what)
    setAskTarget(target === undefined ? (activeCell ? cellRef(activeCell.id) : '') : (target ?? 'none'))
    setAskQty(what.kind === 'goods' ? what.line.qty : null)
  }

  function confirmDialog() {
    // Двойной клик «Положить» — одно действие (R17).
    if (!asking || confirming.current) return
    confirming.current = true
    const target: Holder = askTarget === 'none' || askTarget === '' ? null : askTarget
    if (asking.kind === 'object') {
      moveObject(asking.object, target)
    } else if (askQty && askQty > 0) {
      moveGoods(asking.line, Math.min(askQty, asking.line.qty), target)
    }
    setAsking(null)
  }

  function createObject(kind: ObjKind) {
    // На живом экране тару заводит сервер: он же выдаёт номер и штрихкод, по
    // которому её потом найдёт сканер. Придумывать их на клиенте нельзя —
    // разойдутся с настоящими.
    if (onCreateObject) {
      onCreateObject(kind)
      return
    }
    const number = created + 1
    setCreated(number)
    const code =
      kind === 'pallet'
        ? `П-${String(200 + number).padStart(6, '0')}`
        : kind === 'box'
          ? `КР-${String(500 + number).padStart(6, '0')}`
          : `ГМ-${String(400 + number).padStart(6, '0')}`
    setObjects((current) => [
      ...current,
      { id: `new-${number}`, kind, code, barcode: `29${String(number).padStart(11, '0')}`, holder: null },
    ])
    onNote(`Заглушка: создан ${KIND_TITLE[kind].toLowerCase()} ${code}`)
  }

  function handleScan(code: string) {
    // Подсветка последнего действия гаснет со следующим.
    setFocus(null)
    void scannerRef.current?.scan(code)
  }

  const destinations = asking ? destinationsFor(asking, objects, cells) : []

  return (
    <Box ref={root} data-testid="sorting-objects-screen">
      <ScreenHeader
        title="Раскладка по ячейкам"
        purpose={
          purpose ??
          'Приёмка №1284 от 27.08.2026. Собираем объект и ставим готовый объект на полку.'
        }
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        {/* Стрелка «назад» — как «Отменить последний скан» упаковки FBS: значок
            с подсказкой рядом с полем сканирования, без окна подтверждения. */}
        <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
          <Box ref={field} sx={{ flexGrow: 1, minWidth: 0 }}>
            <ScannerField
              onScan={handleScan}
              expects={activeCell ? activeObject ? `товар в ${activeObject.code} · ячейка ${activeCell.code}` : `тару или товар · ячейка ${activeCell.code}` : 'ячейку с полки'}
              error={scanError}
              notice={pendingScans.count && !pendingScans.paused ? `${scanNotice ?? ''} · Ожидают подтверждения: ${pendingScans.count}` : scanNotice}
              testId="objects-scan"
            />
          </Box>
          <Tooltip title={undoHint}>
            <span style={{ marginTop: 50 }}>
              <IconButton
                size="small"
                aria-label="Отменить последнее действие"
                disabled={!canUndo}
                // Не уводим фокус из поля сканера: следующий пик должен попасть в него.
                onMouseDown={(event) => event.preventDefault()}
                onClick={undo}
                data-testid="objects-undo"
              >
                <UndoOutlinedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{
            // Таблица занимает всю оставшуюся ширину, справа узкая колонка ячеек.
            flexGrow: 1,
            flexShrink: 1,
            minWidth: 0,
            width: { xs: '100%', lg: 'auto' },
          }}>
          <Stack spacing={1} sx={{ mb: 1.5 }}>
            <Stack direction="row" spacing={2} sx={{ alignItems: 'baseline' }}>
              <Typography variant="h5" data-testid="objects-left-qty">
                {leftQty.toLocaleString('ru-RU')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                штук осталось поставить из {totalQty.toLocaleString('ru-RU')} принятых —
                это {unplaced.length} объектов и {loose.length} позиций россыпью
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={totalQty === 0 ? 0 : ((totalQty - leftQty) / totalQty) * 100}
              sx={{ height: 8, borderRadius: 4 }}
            />
          </Stack>
          <Stack
            direction="row"
            spacing={1}
            sx={{ mb: 1.5, alignItems: 'center', flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}
          >
            <SecondaryAction onClick={() => setCellDialogOpen(true)} data-testid="objects-create-cell">
              Создать ячейку
            </SecondaryAction>
            <SecondaryAction onClick={() => createObject('pallet')} data-testid="objects-create-pallet">
              Новая палета
            </SecondaryAction>
            <SecondaryAction onClick={() => createObject('box')} data-testid="objects-create-box">
              Новый короб
            </SecondaryAction>
            <SecondaryAction
              onClick={() => createObject('cargo_place')}
              data-testid="objects-create-cargo_place"
            >
              Новое грузоместо
            </SecondaryAction>
          </Stack>
          <ObjectsTree
            rows={mainRows}
            objects={objects}
            carried={carried}
            testId="objects-tree"
            highlight={mainHighlight}
            empty={{
              title: 'Всё расставлено по ячейкам',
              hint: 'Ни товара россыпью, ни собранных объектов не осталось.',
            }}
            onToggle={toggle}
            onPlace={(row: ObjectRow) =>
              openDialog(
                row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object },
              )
            }
            onDragStart={(row: ObjectRow) =>
              setCarried(
                row.kind === 'goods' ? { kind: 'goods', line: row.line } : { kind: 'object', object: row.object },
              )
            }
            onDragEnd={() => setCarried(null)}
            onDropOn={drop}
            onTakeOut={takeOut}
            onMinus={takeOffCell}
            onPrint={(row) =>
              setPrinting(
                row.kind === 'object'
                  ? { title: objectTitle(row.object), barcode: row.object.barcode }
                  : { title: row.name, barcode: row.barcode },
              )
            }
            onPickCell={selectCell}
          />
        </Box>

        <Stack
          spacing={2}
          sx={{
            // Колонка ячеек — узкая приставка справа, а не половина экрана.
            flexGrow: 0,
            flexShrink: 0,
            minWidth: 0,
            width: { xs: '100%', lg: 320 },
            position: { lg: 'sticky' },
            top: { lg: 16 },
          }}
        >
          <Paper variant="outlined" data-testid="objects-cells">
            <Stack
              direction="row"
              sx={{ alignItems: 'baseline', justifyContent: 'space-between', px: 2, pt: 2, pb: 1 }}
            >
              <Typography variant="subtitle1">Ячейки склада</Typography>
              <Typography variant="caption" color="text.secondary" data-testid="objects-placed-qty">
                размещено {(totalQty - leftQty).toLocaleString('ru-RU')} шт
              </Typography>
            </Stack>
            <Box ref={panelScroll} sx={{ maxHeight: 'calc(100vh - 140px)', overflowY: 'auto', borderTop: '1px solid', borderColor: 'divider' }}>
              <PlacedByCells
                cells={cells}
                objects={objects}
                lines={lines}
                products={products}
                collapsed={placedCollapsed}
                quantities={quantitiesByCell}
                activeCellId={activeCellId}
                openObjectId={scanContext.objectId}
                focusKey={focusKey}
                carried={carried}
                onPickCell={selectCell}
                onDropOnCell={(cellId) => drop(cellRef(cellId))}
                onToggle={togglePlaced}
                onTakeOff={takeOffCell}
                onTakeOut={takeOut}
              />
            </Box>
          </Paper>
        </Stack>
      </Stack>

      {/* Сортировка — это документ, и заканчивается он так же, как остальные
          документы приёмки: сохранить черновик, завершить распределение, закрыть.
          Отдельной кнопки «записать ячейку» здесь нет — записывается документ. */}
      <Stack direction="row" sx={{ mt: 2, justifyContent: 'flex-end' }}>
        <ActionGroup>
          <SecondaryAction
            onClick={() => (onClose ? onClose() : onNote('Заглушка: документ закрыт'))}
            data-testid="objects-close"
          >
            Закрыть
          </SecondaryAction>
          <SecondaryAction
            onClick={() => onNote('Заглушка: раскладка сохранена')}
            disabledReason={
              savedImmediately
                ? 'Сохранять нечего: каждая постановка на полку уходит на сервер сразу'
                : undefined
            }
            data-testid="objects-save"
          >
            Сохранить
          </SecondaryAction>
          <PrimaryAction
            onClick={() => onNote('Заглушка: распределение завершено')}
            disabledReason={
              unplaced.length + loose.length > 0
                ? 'Ещё не всё поставлено на полки'
                : savedImmediately
                  ? 'Всё разложено и уже сохранено — завершать отдельно не нужно'
                  : undefined
            }
            data-testid="objects-complete"
          >
            Завершить
          </PrimaryAction>
        </ActionGroup>
      </Stack>

      <BoxLabelPrintDialog
        open={printing !== null}
        title={printing ? `Печать стикера: ${printing.title}` : ''}
        description="Выберите размер этикетки. Напечатанное не отменить."
        scope="label"
        onClose={() => setPrinting(null)}
        onConfirm={(size) => {
          const target = printing
          setPrinting(null)
          if (!target) return
          if (onPrint) {
            // Штрихкод приходит из самой строки: печатаем ровно то, что в ней стоит.
            if (!target.barcode) {
              onNote(`У «${target.title}» нет штрихкода — печатать нечего.`)
              return
            }
            onPrint(target.title, target.barcode, size)
            return
          }
          onNote(`Заглушка: ${target.title}, этикетка ${size.label} — принтера в превью нет`)
        }}
        testId="objects-print-dialog"
      />
      <CreateCellDialog
        open={cellDialogOpen}
        warehouseName={warehouseName ?? 'Ярцево'}
        existingCodes={cells.map((one) => one.code)}
        onClose={() => setCellDialogOpen(false)}
        onCreate={(code) => {
          if (onCreateCell) {
            onCreateCell(code)
            setCellDialogOpen(false)
            return
          }
          setExtraCells((current) => [
            ...current,
            { id: `new-cell-${current.length + 1}`, code, barcode: `29${String(current.length + 1).padStart(11, '0')}` },
          ])
          setCellDialogOpen(false)
          onNote(`Заглушка: ячейка ${code} создана только в макете`)
        }}
      />
      <AppDialog
        open={asking !== null}
        onClose={() => setAsking(null)}
        title="Куда положить"
        testId="objects-qty-dialog"
        actions={
          <ActionGroup>
            <SecondaryAction onClick={() => setAsking(null)} data-testid="objects-qty-cancel">
              Отмена
            </SecondaryAction>
            <PrimaryAction
              onClick={confirmDialog}
              disabledReason={askTarget === '' ? 'Выберите место' : undefined}
              data-testid="objects-qty-confirm"
            >
              Положить
            </PrimaryAction>
          </ActionGroup>
        }
      >
        <Stack spacing={2}>
          <Typography variant="subtitle2">
            {asking
              ? asking.kind === 'goods'
                ? productById(products, asking.line.productId).name
                : objectTitle(asking.object)
              : ''}
          </Typography>
          <SelectInput
            label="Место"
            value={askTarget}
            onChange={setAskTarget}
            options={destinations}
            emptyLabel="Выберите место"
            testId="objects-target"
          />
          {asking?.kind === 'goods' ? (
            <NumberInput
              label="Сколько штук"
              value={askQty}
              onChange={setAskQty}
              min={1}
              max={asking.line.qty}
              helperText={`Всего ${asking.line.qty} — можно переложить часть`}
              testId="objects-qty-input"
            />
          ) : (
            <Typography variant="body2" color="text.secondary">
              Переедет целиком, вместе со всем содержимым.
            </Typography>
          )}
        </Stack>
      </AppDialog>
    </Box>
  )
}
