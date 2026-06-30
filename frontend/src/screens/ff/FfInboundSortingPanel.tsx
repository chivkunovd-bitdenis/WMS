import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AddIcon from '@mui/icons-material/Add'
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

function boxLineRemaining(bl: SortingBoxLine): number {
  return bl.remaining_qty ?? Math.max(0, bl.quantity - (bl.posted_qty ?? 0))
}

function defaultRowsForProduct(
  productId: string,
  sortableBoxes: SortingBox[],
  loosePool: number,
): CellDraftRow[] {
  const rows: CellDraftRow[] = []
  for (const box of sortableBoxes) {
    const bl = box.lines.find((l) => l.product_id === productId)
    if (bl == null) {
      continue
    }
    const rem = boxLineRemaining(bl)
    if (rem <= 0) {
      continue
    }
    rows.push({
      key: nextDraftKey(),
      box_id: box.id,
      storage_location_id: '',
      quantity: String(rem),
    })
  }
  if (loosePool > 0) {
    rows.push(emptyLooseDraftRow())
  }
  return rows
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

function mergeSavedRowsWithDefaults(
  saved: DistributionLineOut[],
  productId: string,
  sortableBoxes: SortingBox[],
  loosePool: number,
): CellDraftRow[] {
  const draft = saved.length > 0 ? linesFromDistributionRows(saved) : []
  const boxIdsWithRow = new Set(draft.filter((r) => r.box_id != null).map((r) => r.box_id as string))
  for (const box of sortableBoxes) {
    if (boxIdsWithRow.has(box.id)) {
      continue
    }
    const bl = box.lines.find((l) => l.product_id === productId)
    if (bl == null) {
      continue
    }
    const rem = boxLineRemaining(bl)
    if (rem <= 0) {
      continue
    }
    draft.push({
      key: nextDraftKey(),
      box_id: box.id,
      storage_location_id: '',
      quantity: String(rem),
    })
  }
  const hasLooseRow = draft.some((r) => r.box_id == null)
  if (loosePool > 0 && !hasLooseRow) {
    draft.push(emptyLooseDraftRow())
  }
  if (draft.length === 0) {
    return defaultRowsForProduct(productId, sortableBoxes, loosePool)
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
    const q = Math.floor(Number(r.quantity))
    if (Number.isFinite(q) && q > 0) {
      sum += q
    }
  }
  return sum
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
}: Props) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])
  const { catalogById } = useWbProductCatalog(token)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [distributionLoadError, setDistributionLoadError] = useState<string | null>(null)
  const [productStates, setProductStates] = useState<ProductSortState[]>([])
  const [distributionLoaded, setDistributionLoaded] = useState(false)
  const distributionLoadSeq = useRef(0)

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

  const boxNumberById = useMemo(() => {
    const m = new Map<string, number>()
    for (const box of sortableBoxes) {
      m.set(box.id, box.box_number)
    }
    return m
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
      let boxRemainder = 0
      for (const box of sortableBoxes) {
        const bl = box.lines.find((l) => l.product_id === ln.product_id)
        if (bl) {
          boxRemainder += bl.remaining_qty
        }
      }
      m.set(ln.product_id, Math.max(0, accepted - boxRemainder))
    }
    return m
  }, [acceptedByProductId, sortableBoxes, lines])

  const boxRemainderByKey = useMemo(() => {
    const m = new Map<string, number>()
    for (const box of sortableBoxes) {
      for (const bl of box.lines) {
        m.set(`${box.id}:${bl.product_id}`, bl.remaining_qty)
      }
    }
    return m
  }, [sortableBoxes])

  const sortableProducts = useMemo(() => {
    const seen = new Set<string>()
    const out: { product_id: string; sku_code: string; product_name: string; accepted: number; posted: number }[] = []
    for (const ln of lines) {
      if (seen.has(ln.product_id)) continue
      seen.add(ln.product_id)
      const accepted = acceptedByProductId.get(ln.product_id) ?? 0
      if (accepted <= 0 && (postedByProductId.get(ln.product_id) ?? 0) <= 0) continue
      out.push({
        product_id: ln.product_id,
        sku_code: ln.sku_code,
        product_name: ln.product_name,
        accepted,
        posted: postedByProductId.get(ln.product_id) ?? 0,
      })
    }
    return out.sort((a, b) => a.sku_code.localeCompare(b.sku_code))
  }, [acceptedByProductId, lines, postedByProductId])

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

  const loadDistribution = useCallback(async () => {
    const seq = ++distributionLoadSeq.current
    const res = await fetch(
      apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
      { headers: authHeaders },
    )
    if (seq !== distributionLoadSeq.current) {
      return
    }
    if (!res.ok) {
      setDistributionLoadError(await readApiErrorMessage(res))
      setDistributionLoaded(false)
      return
    }
    setDistributionLoadError(null)
    const rows = (await res.json()) as DistributionLineOut[]
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
          p.product_id,
          sortableBoxes,
          loosePoolByProductId.get(p.product_id) ?? 0,
        ),
      })),
    )
    setDistributionLoaded(true)
  }, [authHeaders, loosePoolByProductId, requestId, sortableProducts, sortableBoxes])

  useEffect(() => {
    void loadLocations()
  }, [loadLocations])

  useEffect(() => {
    setDistributionLoaded(false)
    setDistributionLoadError(null)
  }, [lines, boxes, requestId])

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

  const remainingByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of productStates) {
      const draft = draftSumByProductId.get(p.product_id) ?? 0
      m.set(p.product_id, Math.max(0, p.accepted - draft))
    }
    return m
  }, [draftSumByProductId, productStates])

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

    if (row.box_id) {
      const boxCap = boxRemainderByKey.get(`${row.box_id}:${productId}`) ?? 0
      const boxUsed = productRows
        .filter((r) => r.key !== row.key && r.box_id === row.box_id)
        .reduce((s, r) => {
          const q = Math.floor(Number(r.quantity))
          return s + (Number.isFinite(q) && q > 0 ? q : 0)
        }, 0)
      return Math.min(productCap, Math.max(boxCap - boxUsed, 0))
    }

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
        const text = await res.text()
        let detail: unknown = null
        try {
          detail = (JSON.parse(text) as { detail?: unknown }).detail
        } catch {
          /* use readApiErrorMessage fallback */
        }
        if (detail === 'qty_exceeds_accepted') {
          setError('Превышено принятое количество по товару.')
        } else {
          setError(await readApiErrorMessage(new Response(text, { status: res.status })))
        }
        return false
      }
      const rows = (await res.json()) as DistributionLineOut[]
      const byProduct = new Map<string, DistributionLineOut[]>()
      for (const r of rows) {
        const list = byProduct.get(r.product_id) ?? []
        list.push(r)
        byProduct.set(r.product_id, list)
      }
      setProductStates((prev) =>
        prev.map((p) => ({
          ...p,
          rows: mergeSavedRowsWithDefaults(
            byProduct.get(p.product_id) ?? [],
            p.product_id,
            sortableBoxes,
            loosePoolByProductId.get(p.product_id) ?? 0,
          ),
        })),
      )
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить разкладку.')
      return false
    }
  }

  const saveDistribution = async () => {
    if (!distributionReady) {
      return
    }
    if (hasValidationError) {
      setError('Превышено принятое количество — уменьшите количество в строках.')
      return
    }
    setBusy(true)
    try {
      await persistDistribution()
    } finally {
      setBusy(false)
    }
  }

  const applyDistribution = async () => {
    if (!distributionReady) {
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
        setError(await readApiErrorMessage(res))
        return
      }
      await onReload()
      setDistributionLoaded(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось применить разкладку.')
    } finally {
      setBusy(false)
    }
  }

  if (sortableProducts.length === 0) {
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
        Нет принятого товара для разкладки. Завершите приёмку в разделе «Приёмка».
      </Alert>
    )
  }

  const editable = !completed
  const distributionReady = distributionLoaded

  return (
    <FfProductMarkingPrintProvider token={token}>
    <Box data-testid="ff-sorting-panel">
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

      <Stack direction="row" spacing={1} sx={{ mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          Осталось разложить:
        </Typography>
        <Chip
          label={`${sortingRemainingQty} шт`}
          color={sortingRemainingQty > 0 ? 'warning' : 'success'}
          size="small"
          data-testid="ff-sorting-remaining-total"
        />
        {editable ? (
          <>
            <Button
              variant="outlined"
              size="small"
              disabled={busy || hasValidationError || !distributionReady}
              onClick={() => void saveDistribution()}
              data-testid="ff-sorting-save"
            >
              Сохранить
            </Button>
            <Button
              variant="contained"
              size="small"
              disabled={busy || hasValidationError || sortingRemainingQty <= 0 || !distributionReady}
              onClick={() => void applyDistribution()}
              data-testid="ff-sorting-apply"
            >
              Применить разкладку
            </Button>
          </>
        ) : null}
      </Stack>

      {locations.length === 0 ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="ff-sorting-no-locations">
          На складе нет ячеек хранения — создайте их в разделе «Ячейки».
        </Alert>
      ) : null}

      <Stack spacing={2}>
        {productStates.map((product) => {
          const displayMeta = productDisplayMetaFromCatalog(product.product_id, product, catalogById)
          const draftSum = draftSumByProductId.get(product.product_id) ?? 0
          const remaining = remainingByProductId.get(product.product_id) ?? 0
          const loosePool = loosePoolByProductId.get(product.product_id) ?? 0
          const looseAllocated = looseDraftQty(product.rows)
          const looseRemaining = Math.max(0, loosePool - looseAllocated)
          const hasBoxRows = product.rows.some((r) => r.box_id != null)
          const hasLooseRows = loosePool > 0
          const showSourceColumn = hasBoxRows || hasLooseRows
          const looseRowCount = product.rows.filter((r) => r.box_id == null).length
          const done = completed || remaining <= 0

          return (
            <Paper
              key={product.product_id}
              variant="outlined"
              sx={{
                p: 2,
                ...(done
                  ? { opacity: 0.85, bgcolor: (theme) => alpha(theme.palette.success.main, 0.06) }
                  : null),
              }}
              data-testid="ff-sorting-product-card"
              data-product-id={product.product_id}
            >
              <Table size="small" sx={{ mb: 1.5 }}>
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
                      {draftSum}
                    </TableCell>
                    <TableCell align="right" data-testid="ff-sorting-product-remaining">
                      {remaining}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>

              {product.rows.length > 0 ? (
                <TableContainer sx={{ mb: 1 }}>
                  <Table size="small" data-testid="ff-sorting-cell-rows">
                    <TableHead>
                      <TableRow>
                        {showSourceColumn ? <TableCell sx={{ width: 160 }}>Источник</TableCell> : null}
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
                        const isBoxRow = row.box_id != null
                        const sourceLabel = isBoxRow
                          ? `Короб №${boxNumberById.get(row.box_id!) ?? '?'}`
                          : 'Россыпь'
                        return (
                          <TableRow
                            key={row.key}
                            data-testid="ff-sorting-cell-row"
                            sx={exceeds ? { bgcolor: (theme) => alpha(theme.palette.error.main, 0.08) } : null}
                          >
                            {showSourceColumn ? (
                              <TableCell>
                                <Typography variant="body2" data-testid="ff-sorting-cell-source">
                                  {sourceLabel}
                                </Typography>
                              </TableCell>
                            ) : null}
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
                                disabled={busy || !editable || !distributionReady || isBoxRow}
                                error={exceeds}
                                onChange={(e) => {
                                  const v = e.target.value
                                  updateProductRows(product.product_id, (rows) =>
                                    rows.map((r) => (r.key === row.key ? { ...r, quantity: v } : r)),
                                  )
                                }}
                                slotProps={{
                                  htmlInput: {
                                    min: 1,
                                    max: maxQty > 0 ? maxQty : undefined,
                                    'data-testid': 'ff-sorting-cell-qty',
                                    readOnly: isBoxRow ? true : undefined,
                                  },
                                }}
                                sx={{ width: 96 }}
                              />
                            </TableCell>
                            {editable ? (
                              <TableCell align="right">
                                {!isBoxRow && looseRowCount > 1 ? (
                                  <IconButton
                                    size="small"
                                    disabled={busy}
                                    aria-label="Удалить строку"
                                    onClick={() =>
                                      updateProductRows(product.product_id, (rows) =>
                                        rows.filter((r) => r.key !== row.key),
                                      )
                                    }
                                    data-testid="ff-sorting-cell-remove"
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
                  + ячейка
                </Button>
              ) : null}
            </Paper>
          )
        })}
      </Stack>

      {sortingRemainingQty <= 0 ? (
        <Alert severity="success" sx={{ mt: 2 }} data-testid="ff-sorting-all-done">
          Всё принятое разложено по ячейкам хранения.
        </Alert>
      ) : null}
    </Box>
    </FfProductMarkingPrintProvider>
  )
}
