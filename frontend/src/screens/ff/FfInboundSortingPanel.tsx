import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import AddIcon from '@mui/icons-material/Add'
import ExpandLessOutlined from '@mui/icons-material/ExpandLessOutlined'
import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined'
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined'
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  IconButton,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import { FfProductMarkingPrintProvider } from '../../components/FfProductMarkingPrintProvider'
import { useWbProductCatalog } from '../../hooks/useWbProductCatalog'
import { apiUrl } from '../../api'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }

type SortingBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  posted_qty: number
  remaining_qty: number
}

type SortingBox = {
  id: string
  box_number: number
  internal_barcode: string
  intake_closed_at: string | null
  remaining_qty: number
  lines: SortingBoxLine[]
}

type SortingInboundLine = {
  product_id: string
  sku_code: string
  product_name: string
  actual_qty: number | null
  posted_qty: number
}

type DistributionLineOut = {
  id: string
  box_id: string | null
  product_id: string
  storage_location_id: string
  storage_location_code: string
  quantity: number
  created_at: string
}

type DistributionScanOut = {
  kind: 'location' | 'product'
  active_storage_location_id: string | null
  active_storage_location_code: string | null
  product_id: string | null
  lines: DistributionLineOut[]
}

type CellDraftRow = {
  key: string
  box_id: string | null
  storage_location_id: string
  quantity: string
}

type ProductSortState = {
  product_id: string
  sku_code: string
  product_name: string
  accepted: number
  posted: number
  rows: CellDraftRow[]
}

type Props = {
  token: string
  requestId: string
  warehouseId: string
  lines: SortingInboundLine[]
  boxes: SortingBox[]
  sortingRemainingQty: number
  completed?: boolean
  onReload: () => Promise<void>
  onDirtyChange?: (dirty: boolean) => void
  toolbarElement?: HTMLElement | null
}

let draftRowSeq = 0

function nextDraftKey(): string {
  draftRowSeq += 1
  return `draft-${draftRowSeq}`
}

function emptyLooseDraftRow(): CellDraftRow {
  return {
    key: nextDraftKey(),
    box_id: null,
    storage_location_id: '',
    quantity: '',
  }
}

// Единственная строка «россыпи», которую панель создаёт сама (при первом открытии
// карточки товара), сразу получает количество = весь непринятый остаток — как у строк
// коробов, где количество тоже не нужно вводить руками. Раньше строка была пустой, и
// без скана (который заполняет её через distribution-scan) применить раскладку было
// нельзя, даже если оператор просто выбрал ячейку мышкой: buildPayload() отбрасывает
// строки без quantity, поэтому кнопка «Применить раскладку» держится задизейбленной,
// пока хоть в одной строке нет и ячейки, и положительного количества (см. hasSelectableRows
// ниже). Ручная раскладка без сканера — поддерживаемый сценарий, не только вспомогательный.
// Строки, которые оператор добавляет вручную кнопкой «Добавить ячейку» (для разбивки
// остатка по нескольким ячейкам), по-прежнему стартуют пустыми — там нет однозначного
// количества по умолчанию.
function defaultLooseDraftRow(loosePool: number): CellDraftRow {
  return {
    ...emptyLooseDraftRow(),
    quantity: loosePool > 0 ? String(loosePool) : '',
  }
}

function boxLineRemaining(bl: SortingBoxLine): number {
  return bl.remaining_qty ?? Math.max(0, bl.quantity - (bl.posted_qty ?? 0))
}

function defaultRowsForProduct(loosePool: number): CellDraftRow[] {
  return loosePool > 0 ? [defaultLooseDraftRow(loosePool)] : []
}

function distributionRowBoxId(row: DistributionLineOut): string | null {
  if (row.box_id != null && row.box_id !== '') {
    return row.box_id
  }
  return null
}

function linesFromDistributionRows(rows: DistributionLineOut[]): CellDraftRow[] {
  return rows.map((r) => ({
    key: nextDraftKey(),
    box_id: distributionRowBoxId(r),
    storage_location_id: r.storage_location_id,
    quantity: String(r.quantity),
  }))
}

// Строки коробов не вводятся оператором вручную — их количество всегда равно текущему
// остатку в коробе. Раньше здесь слепо доверяли сохранённой строке распределения: если
// короб уже был полностью разложен в прошлом цикле (частичная раскладка теперь разрешена),
// старая строка так и оставалась с прежним количеством, хотя реально раскладывать по
// этому коробу уже нечего. Она подсвечивалась как «превышение» и намертво блокировала
// кнопку «Применить раскладку», хотя это просто исторический след, а не ошибка ввода.
// Поэтому строки коробов всегда пересобираем из текущего остатка, а не из сохранённого
// черновика; выбранную ранее ячейку при этом сохраняем.
function mergeSavedRowsWithDefaults(
  saved: DistributionLineOut[],
  loosePool: number,
): CellDraftRow[] {
  const savedLooseRows = saved.filter((r) => distributionRowBoxId(r) == null)
  const draft = linesFromDistributionRows(savedLooseRows)
  if (loosePool > 0 && draft.length === 0) {
    draft.push(defaultLooseDraftRow(loosePool))
  }
  if (draft.length === 0) {
    return defaultRowsForProduct(loosePool)
  }
  return draft
}

function looseDraftQty(rows: CellDraftRow[]): number {
  let sum = 0
  for (const r of rows) {
    if (r.box_id != null) {
      continue
    }
    const q = Math.floor(Number(r.quantity))
    if (Number.isFinite(q) && q > 0) {
      sum += q
    }
  }
  return sum
}

function sumDraftQty(rows: CellDraftRow[]): number {
  let sum = 0
  for (const r of rows) {
    if (!r.storage_location_id) continue
    const q = Math.floor(Number(r.quantity))
    if (Number.isFinite(q) && q > 0) {
      sum += q
    }
  }
  return sum
}

function sortingErrorMessageRu(code: string): string {
  const normalized = code.trim()
  const messages: Record<string, string> = {
    active_location_required: 'Сначала отсканируйте ячейку, потом товар.',
    barcode_empty: 'Отсканируйте ячейку или товар.',
    box_not_found: 'Короб не найден в этой приёмке.',
    distribution_completed: 'Раскладка уже применена, документ больше не редактируется.',
    distribution_incomplete: 'Разложите всё принятое количество перед применением.',
    insufficient_sorting_stock: 'В зоне сортировки не хватает остатка для этой раскладки. Обновите документ и проверьте количество.',
    invalid_qty: 'Количество должно быть целым числом больше нуля.',
    location_not_found: 'Ячейка не найдена на складе этой приёмки.',
    nothing_to_putaway: 'В этом коробе уже не осталось товара для размещения.',
    not_distributable: 'Документ ещё не находится в сортировке.',
    product_not_accepted: 'Этот товар не принят по документу.',
    product_inside_box: 'Этот товар лежит в коробе — отсканируйте короб, затем ячейку.',
    product_not_on_request: 'Этот товар не относится к этой приёмке.',
    qty_exceeds_accepted: 'По этому товару указано больше, чем принято. Уменьшите количество.',
    qty_exceeds_box_remaining: 'По коробу указано больше товара, чем осталось разложить.',
    scan_not_found: 'Такой товар или ячейка не найдены в этой приёмке.',
    sorting_location_reserved: 'Служебную зону сортировки нельзя выбрать как ячейку хранения.',
  }
  const known = messages[normalized]
  if (known) {
    return known
  }
  // Сырой код ошибки сервера не должен попадать в интерфейс оператора: логируем для
  // отладки, а на экране показываем понятный общий текст.
  console.warn('[ff-sorting] unrecognized error code from server:', normalized)
  return 'Не удалось выполнить действие. Попробуйте ещё раз или обновите страницу.'
}

export function FfInboundSortingPanel({
  token,
  requestId,
  warehouseId,
  lines,
  boxes,
  sortingRemainingQty,
  completed = false,
  onReload,
  onDirtyChange,
  toolbarElement = null,
}: Props) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])
  const { catalogById } = useWbProductCatalog(token)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [distributionLoadError, setDistributionLoadError] = useState<string | null>(null)
  const [productStates, setProductStates] = useState<ProductSortState[]>([])
  const [distributionLoaded, setDistributionLoaded] = useState(false)
  const [scanValue, setScanValue] = useState('')
  const [scanBusy, setScanBusy] = useState(false)
  const [scanMessage, setScanMessage] = useState<string | null>(null)
  const [activeLocationId, setActiveLocationId] = useState<string | null>(null)
  const [activeLocationCode, setActiveLocationCode] = useState<string | null>(null)
  const [pendingBoxId, setPendingBoxId] = useState<string | null>(null)
  const [boxLocationById, setBoxLocationById] = useState<Record<string, string>>({})
  const [distributionRows, setDistributionRows] = useState<DistributionLineOut[]>([])
  const [boxesExpanded, setBoxesExpanded] = useState(true)
  const [looseExpanded, setLooseExpanded] = useState(true)
  const [highlightedProductId, setHighlightedProductId] = useState<string | null>(null)
  const [rowOverflowByProduct, setRowOverflowByProduct] = useState<Record<string, string | null>>({})
  const [, setDirty] = useState(false)
  const scanInputRef = useRef<HTMLInputElement | null>(null)
  const boxPutawayInFlightRef = useRef(false)
  const distributionLoadSeq = useRef(0)
  const distributionEditSeq = useRef(0)
  const dirtyRef = useRef(false)
  const activeLocationStorageKey = useMemo(
    () => `wms.ff.sorting.activeLocation.${requestId}`,
    [requestId],
  )

  const markDirty = useCallback(
    (nextDirty: boolean) => {
      if (nextDirty) {
        distributionEditSeq.current += 1
      }
      dirtyRef.current = nextDirty
      setDirty(nextDirty)
      onDirtyChange?.(nextDirty)
    },
    [onDirtyChange],
  )

  const displayBoxes = useMemo(
    () => boxes.filter((box) => box.lines.length > 0).sort((a, b) => a.box_number - b.box_number),
    [boxes],
  )

  const sortableBoxes = useMemo(
    () =>
      boxes
        .filter((b) =>
          b.lines.some((l) => {
            const rem = l.remaining_qty ?? Math.max(0, l.quantity - (l.posted_qty ?? 0))
            return rem > 0
          }),
        )
        .sort((a, b) => a.box_number - b.box_number),
    [boxes],
  )

  const boxLocationCodesById = useMemo(() => {
    const result = new Map<string, string[]>()
    for (const box of displayBoxes) {
      const postedByProduct = new Map(
        box.lines.map((line) => [line.product_id, line.posted_qty ?? 0]),
      )
      const countedByProduct = new Map<string, number>()
      const newestRows = distributionRows
        .filter((row) => row.box_id === box.id)
        .sort((a, b) => {
          const byCreatedAt = b.created_at.localeCompare(a.created_at)
          return byCreatedAt !== 0 ? byCreatedAt : b.id.localeCompare(a.id)
        })
      const codes: string[] = []
      for (const row of newestRows) {
        const alreadyCounted = countedByProduct.get(row.product_id) ?? 0
        const postedQty = postedByProduct.get(row.product_id) ?? 0
        const backedQty = Math.min(row.quantity, Math.max(0, postedQty - alreadyCounted))
        if (backedQty <= 0) continue
        countedByProduct.set(row.product_id, alreadyCounted + backedQty)
        if (!codes.includes(row.storage_location_code)) {
          codes.push(row.storage_location_code)
        }
      }
      result.set(box.id, codes)
    }
    return result
  }, [displayBoxes, distributionRows])

  const pendingBox = useMemo(
    () => sortableBoxes.find((box) => box.id === pendingBoxId) ?? null,
    [pendingBoxId, sortableBoxes],
  )

  const boxByBarcode = useMemo(() => {
    const map = new Map<string, SortingBox>()
    for (const box of sortableBoxes) {
      const barcode = box.internal_barcode.trim().toUpperCase()
      if (barcode) map.set(barcode, box)
    }
    return map
  }, [sortableBoxes])

  const acceptedByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const ln of lines) {
      // In sorting workspace actual_qty is finalized total from complete_receiving, not loose-only.
      m.set(ln.product_id, ln.actual_qty ?? 0)
    }
    return m
  }, [lines])

  const postedByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const ln of lines) {
      m.set(ln.product_id, ln.posted_qty)
    }
    return m
  }, [lines])

  const loosePoolByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const ln of lines) {
      const accepted = acceptedByProductId.get(ln.product_id) ?? 0
      let boxedTotal = 0
      for (const box of boxes) {
        const bl = box.lines.find((l) => l.product_id === ln.product_id)
        if (bl) {
          boxedTotal += bl.quantity
        }
      }
      m.set(ln.product_id, Math.max(0, accepted - boxedTotal))
    }
    return m
  }, [acceptedByProductId, boxes, lines])

  const boxPostedByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const box of boxes) {
      for (const line of box.lines) {
        m.set(line.product_id, (m.get(line.product_id) ?? 0) + (line.posted_qty ?? 0))
      }
    }
    return m
  }, [boxes])

  const boxRemainingTotal = useMemo(
    () => sortableBoxes.reduce(
      (boxSum, box) => boxSum + box.lines.reduce((lineSum, line) => lineSum + boxLineRemaining(line), 0),
      0,
    ),
    [sortableBoxes],
  )

  const sortableProducts = useMemo(() => {
    const seen = new Set<string>()
    const out: { product_id: string; sku_code: string; product_name: string; accepted: number; posted: number }[] = []
    for (const ln of lines) {
      if (seen.has(ln.product_id)) continue
      seen.add(ln.product_id)
      const accepted = loosePoolByProductId.get(ln.product_id) ?? 0
      const posted = Math.max(
        0,
        (postedByProductId.get(ln.product_id) ?? 0) - (boxPostedByProductId.get(ln.product_id) ?? 0),
      )
      if (accepted <= 0 && posted <= 0) continue
      out.push({
        product_id: ln.product_id,
        sku_code: ln.sku_code,
        product_name: ln.product_name,
        accepted,
        posted,
      })
    }
    return out.sort((a, b) => a.sku_code.localeCompare(b.sku_code))
  }, [boxPostedByProductId, lines, loosePoolByProductId, postedByProductId])

  const loadLocations = useCallback(async () => {
    const res = await fetch(
      apiUrl(`/warehouses/${warehouseId}/locations?exclude_sorting_zone=true`),
      { headers: authHeaders },
    )
    if (!res.ok) {
      setLocations([])
      return
    }
    setLocations((await res.json()) as LocationRow[])
  }, [authHeaders, warehouseId])

  const hydrateDistributionRows = useCallback(
    (rows: DistributionLineOut[]) => {
      setDistributionRows(rows)
      const byProduct = new Map<string, DistributionLineOut[]>()
      for (const r of rows) {
        const list = byProduct.get(r.product_id) ?? []
        list.push(r)
        byProduct.set(r.product_id, list)
      }
      setProductStates(
        sortableProducts.map((p) => ({
          ...p,
          rows: mergeSavedRowsWithDefaults(
            byProduct.get(p.product_id) ?? [],
            loosePoolByProductId.get(p.product_id) ?? 0,
          ),
        })),
      )
      setRowOverflowByProduct({})
    },
    [loosePoolByProductId, sortableProducts],
  )

  const loadDistribution = useCallback(async () => {
    const seq = ++distributionLoadSeq.current
    const editSeq = distributionEditSeq.current
    const res = await fetch(
      apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
      { headers: authHeaders },
    )
    if (
      seq !== distributionLoadSeq.current ||
      editSeq !== distributionEditSeq.current ||
      dirtyRef.current
    ) {
      return
    }
    if (!res.ok) {
      setDistributionLoadError(sortingErrorMessageRu(await readApiErrorMessage(res)))
      setDistributionLoaded(false)
      return
    }
    setDistributionLoadError(null)
    const rows = (await res.json()) as DistributionLineOut[]
    hydrateDistributionRows(rows)
    markDirty(false)
    setDistributionLoaded(true)
  }, [authHeaders, hydrateDistributionRows, markDirty, requestId])

  useEffect(() => {
    void loadLocations()
  }, [loadLocations])

  useEffect(() => {
    if (locations.length === 0 || activeLocationId != null) {
      return
    }
    const raw = window.sessionStorage.getItem(activeLocationStorageKey)
    if (!raw) {
      return
    }
    try {
      const saved = JSON.parse(raw) as { id?: unknown; code?: unknown }
      const id = typeof saved.id === 'string' ? saved.id : ''
      const loc = locations.find((x) => x.id === id)
      if (loc == null) {
        window.sessionStorage.removeItem(activeLocationStorageKey)
        return
      }
      setActiveLocationId(loc.id)
      setActiveLocationCode(
        typeof saved.code === 'string' && saved.code.trim() ? saved.code : loc.code,
      )
    } catch {
      window.sessionStorage.removeItem(activeLocationStorageKey)
    }
  }, [activeLocationId, activeLocationStorageKey, locations])

  useEffect(() => {
    if (activeLocationId == null || activeLocationCode == null) {
      window.sessionStorage.removeItem(activeLocationStorageKey)
      return
    }
    window.sessionStorage.setItem(
      activeLocationStorageKey,
      JSON.stringify({ id: activeLocationId, code: activeLocationCode }),
    )
  }, [activeLocationCode, activeLocationId, activeLocationStorageKey])

  useEffect(() => {
    if (dirtyRef.current) {
      return
    }
    setDistributionLoaded(false)
    setDistributionLoadError(null)
    setHighlightedProductId(null)
  }, [lines, boxes, requestId])

  useEffect(() => {
    setScanMessage(null)
    setPendingBoxId(null)
  }, [requestId])

  useEffect(() => {
    if (pendingBoxId != null && !sortableBoxes.some((box) => box.id === pendingBoxId)) {
      setPendingBoxId(null)
    }
  }, [pendingBoxId, sortableBoxes])

  const retryDistributionLoad = () => {
    setDistributionLoadError(null)
    void loadDistribution()
  }

  useEffect(() => {
    if (!distributionLoaded) {
      void loadDistribution()
    }
  }, [distributionLoaded, loadDistribution])

  const updateProductRows = (productId: string, updater: (rows: CellDraftRow[]) => CellDraftRow[]) => {
    markDirty(true)
    setProductStates((prev) =>
      prev.map((p) => (p.product_id === productId ? { ...p, rows: updater(p.rows) } : p)),
    )
  }

  const draftSumByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of productStates) {
      m.set(p.product_id, sumDraftQty(p.rows))
    }
    return m
  }, [productStates])

  // «Разложено» товара — это не просто сумма текущих строк-черновиков: строки могут
  // повторно показывать то, что уже было применено в прошлый раз (частичная раскладка
  // теперь разрешена), и тогда draftSum и posted совпадают или даже draftSum меньше (если
  // строку удалили, а применённое из зоны сортировки никуда не делось). Поэтому берём
  // максимум — «уже применено» не может уменьшиться от того, что в черновике сейчас пусто.
  const effectiveDistributedByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of productStates) {
      const draft = draftSumByProductId.get(p.product_id) ?? 0
      m.set(p.product_id, Math.max(p.posted, draft))
    }
    return m
  }, [draftSumByProductId, productStates])

  // Осталось = принято минус фактически разложенное (effectiveDistributedByProductId).
  // Специально НЕ схлопываем отрицательный результат в ноль: если расчёт всё же уйдёт в
  // минус, это должно быть видно на экране, а не спрятано, — именно молчаливый
  // Math.max(0, …) в чипе ниже когда-то ввёл оператора в заблуждение (показывал 0, когда
  // на самом деле ещё оставалось раскладывать).
  const remainingByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of productStates) {
      const effective = effectiveDistributedByProductId.get(p.product_id) ?? 0
      m.set(p.product_id, p.accepted - effective)
    }
    return m
  }, [effectiveDistributedByProductId, productStates])

  // Чип наверху и колонка «Осталось» в таблице должны говорить об одном и том же — оба
  // считаются от effectiveDistributedByProductId, а не от «сырой» суммы черновика, иначе
  // строка, повторно показывающая уже применённое, вычитается дважды и уводит чип в минус.
  // Минус не прячем (см. комментарий выше).
  const draftAwareRemainingTotal = useMemo(() => {
    let total = boxRemainingTotal
    for (const qty of remainingByProductId.values()) {
      total += qty
    }
    return total
  }, [boxRemainingTotal, remainingByProductId])

  const rowMaxQty = (productId: string, row: CellDraftRow): number => {
    const accepted = acceptedByProductId.get(productId) ?? 0
    const productRows = productStates.find((p) => p.product_id === productId)?.rows ?? []
    const otherSum = productRows
      .filter((r) => r.key !== row.key)
      .reduce((s, r) => {
        const q = Math.floor(Number(r.quantity))
        return s + (Number.isFinite(q) && q > 0 ? q : 0)
      }, 0)
    const productCap = Math.max(accepted - otherSum, 0)

    const looseCap = loosePoolByProductId.get(productId) ?? 0
    const looseUsed = productRows
      .filter((r) => r.key !== row.key && !r.box_id)
      .reduce((s, r) => {
        const q = Math.floor(Number(r.quantity))
        return s + (Number.isFinite(q) && q > 0 ? q : 0)
      }, 0)
    return Math.min(productCap, Math.max(looseCap - looseUsed, 0))
  }

  const rowExceeds = (productId: string, row: CellDraftRow): boolean => {
    const q = Math.floor(Number(row.quantity))
    if (!Number.isFinite(q) || q <= 0) return false
    return q > rowMaxQty(productId, row)
  }

  const hasValidationError = useMemo(() => {
    for (const p of productStates) {
      const draft = draftSumByProductId.get(p.product_id) ?? 0
      if (draft > p.accepted) return true
      for (const row of p.rows) {
        if (rowExceeds(p.product_id, row)) return true
      }
    }
    return false
  }, [draftSumByProductId, productStates])

  // «Применить раскладку» не должна быть доступна, пока нет ни одной строки с выбранной
  // ячейкой и положительным количеством — иначе кнопка выглядит готовой к нажатию сразу
  // после открытия карточки, до единого скана, а buildPayload() отправит пустой список.
  const hasSelectableRows = useMemo(() => {
    return productStates.some((p) =>
      p.rows.some((row) => {
        if (!row.storage_location_id) return false
        const q = Math.floor(Number(row.quantity))
        return Number.isFinite(q) && q > 0
      }),
    )
  }, [productStates])

  const buildPayload = () => {
    const payload: {
      box_id: string | null
      product_id: string
      storage_location_id: string
      quantity: number
    }[] = []
    for (const p of productStates) {
      for (const row of p.rows) {
        if (!row.storage_location_id || !row.quantity) continue
        const q = Math.floor(Number(row.quantity))
        if (!Number.isFinite(q) || q <= 0) continue
        payload.push({
          box_id: row.box_id || null,
          product_id: p.product_id,
          storage_location_id: row.storage_location_id,
          quantity: q,
        })
      }
    }
    return payload
  }

  const persistDistribution = async (): Promise<boolean> => {
    setError(null)
    distributionEditSeq.current += 1
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify(buildPayload()),
        },
      )
      if (!res.ok) {
        setError(sortingErrorMessageRu(await readApiErrorMessage(res)))
        return false
      }
      const rows = (await res.json()) as DistributionLineOut[]
      hydrateDistributionRows(rows)
      markDirty(false)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить раскладку.')
      return false
    }
  }

  const editable = !completed
  const distributionReady = distributionLoaded

  const focusScanner = useCallback(() => {
    let attempts = 0
    const focus = () => {
      const input = scanInputRef.current
      input?.focus()
      attempts += 1
      if (input != null && document.activeElement !== input && attempts < 8) {
        window.setTimeout(focus, 50)
      }
    }
    window.setTimeout(focus, 0)
  }, [])

  const putawayWholeBox = async (box: SortingBox, location: LocationRow) => {
    if (
      !distributionReady ||
      !editable ||
      scanBusy ||
      busy ||
      boxPutawayInFlightRef.current
    ) {
      return
    }
    boxPutawayInFlightRef.current = true
    setScanBusy(true)
    setError(null)
    setScanMessage(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/boxes/${box.id}/putaway`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ storage_location_id: location.id }),
        },
      )
      if (!res.ok) {
        setError(sortingErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      setPendingBoxId(null)
      setBoxLocationById((prev) => {
        const next = { ...prev }
        delete next[box.id]
        return next
      })
      setActiveLocationId(location.id)
      setActiveLocationCode(location.code)
      markDirty(false)
      await onReload()
      setDistributionLoaded(false)
      setScanMessage(`Короб №${box.box_number} полностью размещён в ячейке ${location.code}.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось разместить короб в ячейку.')
    } finally {
      boxPutawayInFlightRef.current = false
      setScanValue('')
      setScanBusy(false)
      focusScanner()
    }
  }

  useEffect(() => {
    if (!editable || !distributionReady || locations.length === 0 || busy || scanBusy) {
      return
    }
    focusScanner()
  }, [busy, distributionReady, editable, focusScanner, locations.length, scanBusy])

  const scanDistribution = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault()
    if (!distributionReady || !editable || scanBusy) {
      focusScanner()
      return
    }
    const barcode = scanValue.trim()
    if (!barcode) {
      setScanMessage('Отсканируйте ячейку или товар.')
      focusScanner()
      return
    }
    setScanBusy(true)
    setError(null)
    setScanMessage(null)
    distributionEditSeq.current += 1
    try {
      const scannedBox = boxByBarcode.get(barcode.toUpperCase())
      if (scannedBox != null) {
        setPendingBoxId(scannedBox.id)
        // Для короба всегда требуем свежий скан ячейки: ранее выбранный адрес нельзя
        // молча переиспользовать для физически другого короба.
        setActiveLocationId(null)
        setActiveLocationCode(null)
        setScanMessage(`Короб №${scannedBox.box_number} выбран. Теперь отсканируйте ячейку.`)
        setScanValue('')
        return
      }

      if (pendingBox != null) {
        const location = locations.find((row) => {
          const raw = barcode.toUpperCase()
          return row.barcode.trim().toUpperCase() === raw || row.code.trim().toUpperCase() === raw
        })
        if (location == null) {
          setError('После короба отсканируйте ячейку этого склада.')
          setScanValue('')
          return
        }
        await putawayWholeBox(pendingBox, location)
        return
      }

      setScanBusy(true)
      distributionEditSeq.current += 1
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-scan`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            barcode,
            active_storage_location_id: activeLocationId,
          }),
        },
      )
      if (!res.ok) {
        setError(sortingErrorMessageRu(await readApiErrorMessage(res)))
        setScanValue('')
        return
      }
      const result = (await res.json()) as DistributionScanOut
      if (result.active_storage_location_id != null) {
        setActiveLocationId(result.active_storage_location_id)
        setActiveLocationCode(result.active_storage_location_code)
      }
      if (result.kind === 'location') {
        setScanMessage(`Активная ячейка: ${result.active_storage_location_code ?? 'без кода'}.`)
      } else {
        hydrateDistributionRows(result.lines)
        markDirty(false)
        setHighlightedProductId(result.product_id)
        const product = productStates.find((p) => p.product_id === result.product_id)
        const allocated = result.lines
          .filter((r) => r.product_id === result.product_id && r.box_id == null)
          .reduce((sum, r) => sum + Number(r.quantity || 0), 0)
        const accepted = product?.accepted ?? 0
        const remaining = Math.max(0, accepted - allocated)
        setScanMessage(
          `Скан принят: ${product?.product_name ?? 'товар'} → ${result.active_storage_location_code ?? activeLocationCode ?? 'ячейка'}; разложено ${allocated}, осталось ${remaining}.`,
        )
      }
      setScanValue('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось обработать скан.')
    } finally {
      setScanBusy(false)
      focusScanner()
    }
  }

  const applyDistribution = async () => {
    if (
      !distributionReady ||
      busy ||
      scanBusy ||
      boxPutawayInFlightRef.current
    ) {
      return
    }
    if (hasValidationError) {
      setError('Превышено принятое количество — исправьте строки перед применением.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const saved = await persistDistribution()
      if (!saved) return
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-complete`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(sortingErrorMessageRu(await readApiErrorMessage(res)))
        return
      }
      await onReload()
      setDistributionLoaded(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось применить раскладку.')
    } finally {
      setBusy(false)
    }
  }

  if (sortableProducts.length === 0 && displayBoxes.length === 0) {
    if (sortingRemainingQty > 0) {
      return (
        <Alert severity="warning" data-testid="ff-sorting-products-loading-gap">
          Осталось разложить {sortingRemainingQty} шт., но состав строк не загрузился. Обновите
          страницу или откройте заявку снова.
        </Alert>
      )
    }
    return (
      <Alert severity="info" data-testid="ff-sorting-no-products">
        Нет принятого товара для раскладки. Завершите приёмку в разделе «Приёмка».
      </Alert>
    )
  }

  return (
    <FfProductMarkingPrintProvider token={token}>
      <Box data-testid="ff-sorting-panel" sx={{ width: '100%', minWidth: 0 }}>
      {distributionLoadError ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          data-testid="ff-sorting-distribution-load-error"
          action={
            <Button color="inherit" size="small" onClick={retryDistributionLoad} data-testid="ff-sorting-distribution-retry">
              Повторить
            </Button>
          }
        >
          {distributionLoadError}
        </Alert>
      ) : null}

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-sorting-error">
          {error}
        </Alert>
      ) : null}

      {editable ? (
        <Box
          component="form"
          onSubmit={(event) => void scanDistribution(event)}
          sx={{
            mb: 2,
            p: 1.5,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            bgcolor: (theme) => alpha(theme.palette.info.main, 0.04),
          }}
          data-testid="ff-sorting-scanner"
        >
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.25} sx={{ alignItems: { md: 'center' } }}>
            <TextField
              inputRef={scanInputRef}
              value={scanValue}
              onChange={(event) => setScanValue(event.target.value)}
              size="small"
              autoFocus={editable && distributionReady && locations.length > 0}
              fullWidth
              autoComplete="off"
              placeholder={activeLocationId == null ? 'Скан ячейки' : 'Скан товара'}
              disabled={scanBusy || busy || !distributionReady || locations.length === 0}
              slotProps={{
                htmlInput: {
                  'data-testid': 'ff-sorting-scan-input',
                },
              }}
            />
            <Button
              type="submit"
              variant="outlined"
              startIcon={<QrCodeScannerOutlined />}
              disabled={scanBusy || busy || !distributionReady || locations.length === 0}
              data-testid="ff-sorting-scan-submit"
              sx={{ whiteSpace: 'nowrap' }}
            >
              Скан
            </Button>
          </Stack>
          {/* SORT-01: одна подпись на оба состояния — до скана ячейки и после.
              Раньше рядом висел ещё чип с тем же смыслом, он убран как дубль. */}
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', mt: 0.75 }}
            data-testid="ff-sorting-scan-message"
          >
            {scanMessage
              ? scanMessage
              : pendingBox != null
                ? `Короб №${pendingBox.box_number} выбран — отсканируйте ячейку.`
              : activeLocationId == null
                ? 'Отсканируйте короб или ячейку.'
                : `Активная ячейка: ${activeLocationCode}.`}
          </Typography>
        </Box>
      ) : null}

      {displayBoxes.length > 0 ? (
        <Paper variant="outlined" sx={{ mb: 2, p: 1.5 }} data-testid="ff-sorting-box-putaway">
          <Button
            color="inherit"
            onClick={() => setBoxesExpanded((expanded) => !expanded)}
            startIcon={boxesExpanded ? <ExpandLessOutlined /> : <ExpandMoreOutlined />}
            aria-expanded={boxesExpanded}
            data-testid="ff-sorting-boxes-toggle"
            sx={{ p: 0, mb: boxesExpanded ? 1 : 0, minWidth: 0, textTransform: 'none' }}
          >
            <Typography variant="h6" component="span" sx={{ fontWeight: 800 }}>
              Короба
            </Typography>
          </Button>
          {boxesExpanded ? <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Короб</TableCell>
                  <TableCell align="right">Осталось</TableCell>
                  <TableCell sx={{ width: 260 }}>Ячейка</TableCell>
                  <TableCell align="right" sx={{ width: 120 }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {displayBoxes.map((box) => {
                  const remaining = box.lines.reduce((sum, line) => sum + boxLineRemaining(line), 0)
                  const placed = remaining <= 0
                  const locationId = boxLocationById[box.id] ?? ''
                  const selectedLocation = locations.find((row) => row.id === locationId) ?? null
                  const locationCodes = boxLocationCodesById.get(box.id) ?? []
                  return (
                    <TableRow
                      key={box.id}
                      selected={box.id === pendingBoxId}
                      aria-selected={box.id === pendingBoxId}
                      data-testid="ff-sorting-box-putaway-row"
                      data-box-id={box.id}
                      data-placed={placed ? 'true' : 'false'}
                    >
                      <TableCell colSpan={4} sx={{ p: 0 }}>
                        <Table size="small">
                          <TableBody>
                            <TableRow>
                              <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          Короб №{box.box_number}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {box.internal_barcode}
                        </Typography>
                              </TableCell>
                              <TableCell align="right" sx={{ width: 120 }}>{remaining} шт.</TableCell>
                              <TableCell sx={{ width: 260 }}>
                        {placed ? (
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 700 }}
                            data-testid="ff-sorting-box-placed-location"
                          >
                            {locationCodes.join(', ') || 'Ячейка не указана'}
                          </Typography>
                        ) : <FormControl size="small" fullWidth>
                          <Select
                            displayEmpty
                            value={locationId}
                            disabled={scanBusy || busy || locations.length === 0}
                            onChange={(event) =>
                              setBoxLocationById((prev) => ({
                                ...prev,
                                [box.id]: String(event.target.value),
                              }))
                            }
                            data-testid="ff-sorting-box-location"
                          >
                            <MenuItem value="">
                              <em>Выберите ячейку</em>
                            </MenuItem>
                            {locations.map((location) => (
                              <MenuItem key={location.id} value={location.id}>
                                {location.code}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>}
                              </TableCell>
                              <TableCell align="right" sx={{ width: 120 }}>
                        {placed ? (
                          <Chip label="Разложен" color="success" size="small" data-testid="ff-sorting-box-placed" />
                        ) : <Button
                          size="small"
                          variant="outlined"
                          disabled={scanBusy || busy || selectedLocation == null}
                          onClick={() => {
                            if (selectedLocation != null) void putawayWholeBox(box, selectedLocation)
                          }}
                          data-testid="ff-sorting-box-putaway-submit"
                        >
                          Разместить
                        </Button>}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell colSpan={4} sx={{ p: 0, borderBottom: 0 }}>
                                <TableContainer>
                                  <Table size="small" data-testid="ff-sorting-box-products">
                                    <TableHead>
                                      <TableRow>
                                        <FfProductTableHeadCells showPrint={false} />
                                        <TableCell align="right" sx={{ width: 110 }}>В коробе</TableCell>
                                      </TableRow>
                                    </TableHead>
                                    <TableBody>
                                      {box.lines.map((line) => {
                                        const meta = productDisplayMetaFromCatalog(
                                          line.product_id,
                                          line,
                                          catalogById,
                                        )
                                        return (
                                          <TableRow
                                            key={line.id}
                                            data-testid="ff-sorting-box-product-row"
                                            data-product-id={line.product_id}
                                          >
                                            <FfProductLineCells
                                              meta={meta}
                                              showPrint={false}
                                              lineTestIdPrefix="ff-sorting-box-product"
                                            />
                                            <TableCell
                                              align="right"
                                              data-testid="ff-sorting-box-product-qty"
                                            >
                                              {line.quantity}
                                            </TableCell>
                                          </TableRow>
                                        )
                                      })}
                                    </TableBody>
                                  </Table>
                                </TableContainer>
                              </TableCell>
                            </TableRow>
                          </TableBody>
                        </Table>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer> : null}
        </Paper>
      ) : null}

      {toolbarElement
        ? createPortal(
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Chip
                label={
                  draftAwareRemainingTotal < 0
                    ? `Превышение на ${Math.abs(draftAwareRemainingTotal)} шт`
                    : `Осталось: ${draftAwareRemainingTotal} шт`
                }
                color={
                  draftAwareRemainingTotal > 0
                    ? 'warning'
                    : draftAwareRemainingTotal < 0
                      ? 'error'
                      : 'success'
                }
                size="small"
                sx={{ fontWeight: 800 }}
                data-testid="ff-sorting-remaining-total"
              />
              {editable ? (
                <Tooltip
                  title={
                    hasValidationError
                      ? 'Есть строки, где указано больше, чем доступно для раскладки. Уменьшите количество, чтобы применить.'
                      : !hasSelectableRows
                        ? 'Выберите ячейку и укажите количество хотя бы в одной строке, чтобы применить раскладку.'
                        : ''
                  }
                >
                  <span>
                    <Button
                      variant="contained"
                      size="small"
                      disabled={
                        busy ||
                        scanBusy ||
                        hasValidationError ||
                        !hasSelectableRows ||
                        sortingRemainingQty <= 0 ||
                        !distributionReady
                      }
                      onClick={() => void applyDistribution()}
                      data-testid="ff-sorting-apply"
                    >
                      Применить раскладку
                    </Button>
                  </span>
                </Tooltip>
              ) : null}
            </Stack>,
            toolbarElement,
          )
        : null}

      {locations.length === 0 ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="ff-sorting-no-locations">
          Адресное хранение включено, но на складе нет обычных ячеек. Создайте ячейку в каталоге складов.
        </Alert>
      ) : null}

      {sortableProducts.length > 0 ? (
        <Button
          color="inherit"
          onClick={() => setLooseExpanded((expanded) => !expanded)}
          startIcon={looseExpanded ? <ExpandLessOutlined /> : <ExpandMoreOutlined />}
          aria-expanded={looseExpanded}
          data-testid="ff-sorting-loose-toggle"
          sx={{ p: 0, mb: looseExpanded ? 1 : 0, minWidth: 0, textTransform: 'none' }}
        >
          <Typography variant="h6" component="span" sx={{ fontWeight: 800 }}>
            Россыпь
          </Typography>
        </Button>
      ) : null}

      {looseExpanded ? <Stack spacing={2}>
        {productStates.map((product) => {
          const displayMeta = productDisplayMetaFromCatalog(product.product_id, product, catalogById)
          const effectiveDistributed = effectiveDistributedByProductId.get(product.product_id) ?? 0
          const remaining = remainingByProductId.get(product.product_id) ?? 0
          const remainingOverflow = remaining < 0
          const loosePool = loosePoolByProductId.get(product.product_id) ?? 0
          const looseAllocated = looseDraftQty(product.rows)
          const looseRemaining = Math.max(0, loosePool - looseAllocated)
          const looseRowCount = product.rows.length
          const done = completed || remaining <= 0

          return (
            <Paper
              key={product.product_id}
              variant="outlined"
              sx={{
                p: 2,
                minWidth: 0,
                borderColor: product.product_id === highlightedProductId ? 'info.main' : undefined,
                boxShadow:
                  product.product_id === highlightedProductId
                    ? (theme) => `0 0 0 1px ${theme.palette.info.main}`
                    : undefined,
                ...(done
                  ? { opacity: 0.85, bgcolor: (theme) => alpha(theme.palette.success.main, 0.06) }
                  : null),
              }}
              data-testid="ff-sorting-product-card"
              data-product-id={product.product_id}
            >
              <TableContainer sx={{ mb: 1.5, width: '100%', minWidth: 0 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <FfProductTableHeadCells />
                      <TableCell align="right">Принято</TableCell>
                      <TableCell align="right">Разложено</TableCell>
                      <TableCell align="right">Осталось</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow data-testid="ff-sorting-product-summary">
                      <FfProductLineCells
                        meta={displayMeta}
                        productId={product.product_id}
                        qtyNeedPack={product.accepted}
                        printSource="packaging"
                      />
                      <TableCell align="right" data-testid="ff-sorting-product-accepted">
                        {product.accepted}
                      </TableCell>
                      <TableCell align="right" data-testid="ff-sorting-product-distributed">
                        {effectiveDistributed}
                      </TableCell>
                      <TableCell
                        align="right"
                        data-testid="ff-sorting-product-remaining"
                        sx={remainingOverflow ? { color: 'error.main', fontWeight: 700 } : undefined}
                      >
                        {remaining}
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>

              {product.rows.length > 0 ? (
                <TableContainer sx={{ mb: 1, width: '100%', minWidth: 0 }}>
                  <Table size="small" data-testid="ff-sorting-cell-rows">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ minWidth: 180 }}>Ячейка</TableCell>
                        <TableCell align="right" sx={{ width: 120 }}>
                          Шт
                        </TableCell>
                        {editable ? <TableCell align="right" sx={{ width: 48 }} /> : null}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {product.rows.map((row) => {
                        const maxQty = rowMaxQty(product.product_id, row)
                        const exceeds = rowExceeds(product.product_id, row)
                        return (
                          <TableRow
                            key={row.key}
                            data-testid="ff-sorting-cell-row"
                            sx={exceeds ? { bgcolor: (theme) => alpha(theme.palette.error.main, 0.08) } : null}
                          >
                            <TableCell>
                              <FormControl size="small" fullWidth>
                                <Select
                                  value={row.storage_location_id}
                                  disabled={busy || !editable || !distributionReady || locations.length === 0}
                                  displayEmpty
                                  onChange={(e) => {
                                    const v = String(e.target.value)
                                    updateProductRows(product.product_id, (rows) =>
                                      rows.map((r) =>
                                        r.key === row.key ? { ...r, storage_location_id: v } : r,
                                      ),
                                    )
                                  }}
                                  data-testid="ff-sorting-cell-location"
                                >
                                  <MenuItem value="">
                                    <em>Выберите ячейку</em>
                                  </MenuItem>
                                  {locations.map((loc) => (
                                    <MenuItem key={loc.id} value={loc.id}>
                                      {loc.code}
                                    </MenuItem>
                                  ))}
                                </Select>
                              </FormControl>
                            </TableCell>
                            <TableCell align="right">
                              <TextField
                                type="number"
                                size="small"
                                value={row.quantity}
                                disabled={busy || !editable || !distributionReady}
                                error={exceeds}
                                onChange={(e) => {
                                  const raw = e.target.value
                                  const parsed = Math.floor(Number(raw))
                                  // Верхняя граница проверяется в момент ввода, а не только
                                  // при попытке применить: превышение сразу обрезаем до
                                  // максимума и объясняем числами, сколько реально доступно.
                                  if (raw !== '' && Number.isFinite(parsed) && parsed > maxQty) {
                                    setRowOverflowByProduct((prev) => ({
                                      ...prev,
                                      [product.product_id]: `Осталось разложить ${maxQty} шт., вы указали ${parsed}. Количество уменьшено до ${maxQty}.`,
                                    }))
                                    updateProductRows(product.product_id, (rows) =>
                                      rows.map((r) =>
                                        r.key === row.key ? { ...r, quantity: String(maxQty) } : r,
                                      ),
                                    )
                                    return
                                  }
                                  setRowOverflowByProduct((prev) =>
                                    prev[product.product_id] ? { ...prev, [product.product_id]: null } : prev,
                                  )
                                  updateProductRows(product.product_id, (rows) =>
                                    rows.map((r) => (r.key === row.key ? { ...r, quantity: raw } : r)),
                                  )
                                }}
                                slotProps={{
                                  htmlInput: {
                                    min: 1,
                                    max: maxQty > 0 ? maxQty : undefined,
                                    'data-testid': 'ff-sorting-cell-qty',
                                  },
                                }}
                                sx={{ width: 96 }}
                              />
                            </TableCell>
                            {editable ? (
                              <TableCell align="right">
                                {looseRowCount > 1 ? (
                                  <IconButton
                                    disabled={busy}
                                    aria-label="Удалить строку"
                                    onClick={() =>
                                      updateProductRows(product.product_id, (rows) =>
                                        rows.filter((r) => r.key !== row.key),
                                      )
                                    }
                                    data-testid="ff-sorting-cell-remove"
                                    sx={{ width: 40, height: 40, fontSize: 20 }}
                                  >
                                    ×
                                  </IconButton>
                                ) : null}
                              </TableCell>
                            ) : null}
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : null}

              {rowOverflowByProduct[product.product_id] ? (
                <Alert
                  severity="warning"
                  variant="outlined"
                  sx={{ mb: 1, py: 0 }}
                  data-testid="ff-sorting-cell-overflow"
                >
                  {rowOverflowByProduct[product.product_id]}
                </Alert>
              ) : null}

              {editable && looseRemaining > 0 ? (
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<AddIcon />}
                  disabled={busy || !distributionReady || locations.length === 0}
                  onClick={() =>
                    updateProductRows(product.product_id, (rows) => [...rows, emptyLooseDraftRow()])
                  }
                  data-testid="ff-sorting-add-cell"
                >
                  Добавить ячейку
                </Button>
              ) : null}
            </Paper>
          )
        })}
      </Stack> : null}

      {sortingRemainingQty <= 0 ? (
        <Alert severity="success" sx={{ mt: 2 }} data-testid="ff-sorting-all-done">
          Всё принятое разложено по ячейкам хранения.
        </Alert>
      ) : null}
    </Box>
    </FfProductMarkingPrintProvider>
  )
}
