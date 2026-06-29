import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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

function emptyDraftRow(defaultBoxId: string | null): CellDraftRow {
  return {
    key: nextDraftKey(),
    box_id: defaultBoxId,
    storage_location_id: '',
    quantity: '',
  }
}

function distributionRowBoxId(
  row: DistributionLineOut,
  defaultBoxId: string | null,
  loosePool: number,
): string | null {
  if (row.box_id != null && row.box_id !== '') {
    return row.box_id
  }
  // API returns box_id: null for loose lines — do not assign defaultBoxId when loose pool exists.
  return loosePool > 0 ? null : defaultBoxId
}

function linesFromDistributionRows(
  rows: DistributionLineOut[],
  defaultBoxId: string | null,
  loosePool: number,
): CellDraftRow[] {
  return rows.map((r) => ({
    key: nextDraftKey(),
    box_id: distributionRowBoxId(r, defaultBoxId, loosePool),
    storage_location_id: r.storage_location_id,
    quantity: String(r.quantity),
  }))
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
  const navigate = useNavigate()
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])
  const { catalogById } = useWbProductCatalog(token)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [productStates, setProductStates] = useState<ProductSortState[]>([])
  const [distributionLoaded, setDistributionLoaded] = useState(false)
  const distributionLoadSeq = useRef(0)

  const closedBoxes = useMemo(
    () =>
      boxes
        .filter((b) => b.intake_closed_at != null)
        .sort((a, b) => a.box_number - b.box_number),
    [boxes],
  )

  const defaultBoxId = closedBoxes.length === 1 ? closedBoxes[0]!.id : null

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
      for (const box of closedBoxes) {
        const bl = box.lines.find((l) => l.product_id === ln.product_id)
        if (bl) {
          boxRemainder += bl.remaining_qty
        }
      }
      m.set(ln.product_id, Math.max(0, accepted - boxRemainder))
    }
    return m
  }, [acceptedByProductId, closedBoxes, lines])

  const boxRemainderByKey = useMemo(() => {
    const m = new Map<string, number>()
    for (const box of closedBoxes) {
      for (const bl of box.lines) {
        m.set(`${box.id}:${bl.product_id}`, bl.remaining_qty)
      }
    }
    return m
  }, [closedBoxes])

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
      setProductStates(
        sortableProducts.map((p) => ({
          ...p,
          rows: [],
        })),
      )
      setDistributionLoaded(true)
      return
    }
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
        rows: linesFromDistributionRows(
          byProduct.get(p.product_id) ?? [],
          defaultBoxId,
          loosePoolByProductId.get(p.product_id) ?? 0,
        ),
      })),
    )
    setDistributionLoaded(true)
  }, [authHeaders, defaultBoxId, loosePoolByProductId, requestId, sortableProducts])

  useEffect(() => {
    void loadLocations()
  }, [loadLocations])

  useEffect(() => {
    setDistributionLoaded(false)
  }, [lines, boxes, requestId])

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
          rows: linesFromDistributionRows(
            byProduct.get(p.product_id) ?? [],
            defaultBoxId,
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

  const sortingPackLines = useMemo(
    () =>
      sortableProducts
        .map((p) => ({
          product_id: p.product_id,
          sku_code: p.sku_code,
          product_name: p.product_name,
          quantity: Math.max(0, p.accepted - p.posted),
        }))
        .filter((ln) => ln.quantity > 0),
    [sortableProducts],
  )

  const createPackagingFromSorting = async () => {
    if (sortingPackLines.length === 0) {
      setError('Нет товара в сортировке для упаковки.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/operations/packaging-tasks'), {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          warehouse_id: warehouseId,
          inbound_intake_request_id: requestId,
          lines: sortingPackLines.map((ln) => ({
            product_id: ln.product_id,
            quantity: ln.quantity,
          })),
        }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const task = (await res.json()) as { id: string }
      navigate('/ff/packaging', { state: { taskId: task.id } })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать задание.')
    } finally {
      setBusy(false)
    }
  }

  const boxSourcesForProduct = (productId: string) =>
    closedBoxes
      .map((box) => {
        const bl = box.lines.find((l) => l.product_id === productId)
        if (!bl || bl.remaining_qty <= 0) return null
        return { box_id: box.id, box_number: box.box_number, remaining: bl.remaining_qty }
      })
      .filter((x): x is { box_id: string; box_number: number; remaining: number } => x != null)

  if (sortableProducts.length === 0) {
    return (
      <Alert severity="info" data-testid="ff-sorting-no-products">
        Нет принятого товара для разкладки. Завершите приёмку в разделе «Приёмка».
      </Alert>
    )
  }

  const editable = !completed

  return (
    <Box data-testid="ff-sorting-panel">
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
        {editable && sortingRemainingQty > 0 ? (
          <Button
            variant="outlined"
            size="small"
            disabled={busy}
            onClick={() => void createPackagingFromSorting()}
            data-testid="ff-sorting-pack-btn"
          >
            Упаковать
          </Button>
        ) : null}
        {editable ? (
          <>
            <Button
              variant="outlined"
              size="small"
              disabled={busy || hasValidationError}
              onClick={() => void saveDistribution()}
              data-testid="ff-sorting-save"
            >
              Сохранить
            </Button>
            <Button
              variant="contained"
              size="small"
              disabled={busy || hasValidationError || sortingRemainingQty <= 0}
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
          const boxSources = boxSourcesForProduct(product.product_id)
          const loosePool = loosePoolByProductId.get(product.product_id) ?? 0
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
                    <FfProductLineCells meta={displayMeta} />
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
                        {boxSources.length > 0 || loosePool > 0 ? (
                          <TableCell sx={{ width: 160 }}>Источник</TableCell>
                        ) : null}
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
                            {boxSources.length > 0 || loosePool > 0 ? (
                              <TableCell>
                                <FormControl size="small" fullWidth>
                                  <Select
                                    value={row.box_id ?? ''}
                                    disabled={busy || !editable}
                                    displayEmpty
                                    onChange={(e) => {
                                      const v = String(e.target.value)
                                      updateProductRows(product.product_id, (rows) =>
                                        rows.map((r) =>
                                          r.key === row.key
                                            ? { ...r, box_id: v ? v : null }
                                            : r,
                                        ),
                                      )
                                    }}
                                    data-testid="ff-sorting-cell-source"
                                  >
                                    {loosePool > 0 ? (
                                      <MenuItem value="">
                                        <em>Россыпь</em>
                                      </MenuItem>
                                    ) : null}
                                    {boxSources.map((bs) => (
                                      <MenuItem key={bs.box_id} value={bs.box_id}>
                                        Короб №{bs.box_number}
                                      </MenuItem>
                                    ))}
                                  </Select>
                                </FormControl>
                              </TableCell>
                            ) : null}
                            <TableCell>
                              <FormControl size="small" fullWidth>
                                <Select
                                  value={row.storage_location_id}
                                  disabled={busy || !editable || locations.length === 0}
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
                                disabled={busy || !editable}
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
                                  },
                                }}
                                sx={{ width: 96 }}
                              />
                            </TableCell>
                            {editable ? (
                              <TableCell align="right">
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
                              </TableCell>
                            ) : null}
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : null}

              {editable && remaining > 0 ? (
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<AddIcon />}
                  disabled={busy || locations.length === 0}
                  onClick={() =>
                    updateProductRows(product.product_id, (rows) => [
                      ...rows,
                      emptyDraftRow(
                        loosePool > 0 ? null : (boxSources[0]?.box_id ?? defaultBoxId),
                      ),
                    ])
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
  )
}
