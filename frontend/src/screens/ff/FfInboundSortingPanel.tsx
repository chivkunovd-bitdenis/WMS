import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
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

type BoxLine = {
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
  lines: BoxLine[]
}

type PutawayHistoryRow = {
  id: string
  box_id: string | null
  product_id: string
  storage_location_code: string
  quantity: number
  created_at: string
}

type CellProductLine = {
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
}

type CellWholeBoxLine = {
  created_at: string
  total_qty: number
  products: CellProductLine[]
}

type CellPutawayGroup = {
  cell_code: string
  total_qty: number
  whole_box_batches: CellWholeBoxLine[]
  products: CellProductLine[]
}

type Props = {
  token: string
  requestId: string
  warehouseId: string
  boxes: SortingBox[]
  sortingRemainingQty: number
  /** Заявка уже оприходована — только просмотр разкладки. */
  completed?: boolean
  onReload: () => Promise<void>
}

function resolveBoxPutawayHistory(
  boxId: string,
  closedBoxes: SortingBox[],
  putawayHistory: PutawayHistoryRow[],
  byBoxId: Map<string, PutawayHistoryRow[]>,
): PutawayHistoryRow[] {
  const direct = byBoxId.get(boxId) ?? []
  if (direct.length > 0) {
    return direct
  }
  if (closedBoxes.length !== 1 || closedBoxes[0]?.id !== boxId) {
    return direct
  }
  return putawayHistory
    .filter((r) => !r.box_id)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
}

function buildCellPutawayGroups(
  boxHistory: PutawayHistoryRow[],
  productMetaById: Map<string, { sku_code: string; product_name: string }>,
): CellPutawayGroup[] {
  const byCell = new Map<string, PutawayHistoryRow[]>()
  for (const row of boxHistory) {
    const list = byCell.get(row.storage_location_code) ?? []
    list.push(row)
    byCell.set(row.storage_location_code, list)
  }

  const groups: CellPutawayGroup[] = []

  for (const [cell_code, rows] of byCell) {
    const byTime = new Map<string, PutawayHistoryRow[]>()
    for (const row of rows) {
      const list = byTime.get(row.created_at) ?? []
      list.push(row)
      byTime.set(row.created_at, list)
    }

    const whole_box_batches: CellWholeBoxLine[] = []
    const productQty = new Map<string, number>()

    for (const [created_at, batch] of byTime) {
      if (batch.length >= 2) {
        const products: CellProductLine[] = batch.map((r) => {
          const meta = productMetaById.get(r.product_id)
          return {
            product_id: r.product_id,
            sku_code: meta?.sku_code ?? '—',
            product_name: meta?.product_name ?? r.product_id.slice(0, 8),
            quantity: r.quantity,
          }
        })
        whole_box_batches.push({
          created_at,
          total_qty: batch.reduce((s, r) => s + r.quantity, 0),
          products,
        })
        continue
      }
      for (const r of batch) {
        productQty.set(r.product_id, (productQty.get(r.product_id) ?? 0) + r.quantity)
      }
    }

    const products: CellProductLine[] = Array.from(productQty.entries())
      .map(([product_id, quantity]) => {
        const meta = productMetaById.get(product_id)
        return {
          product_id,
          sku_code: meta?.sku_code ?? '—',
          product_name: meta?.product_name ?? product_id.slice(0, 8),
          quantity,
        }
      })
      .sort((a, b) => a.product_name.localeCompare(b.product_name))

    const total_qty =
      whole_box_batches.reduce((s, b) => s + b.total_qty, 0) +
      products.reduce((s, p) => s + p.quantity, 0)

    groups.push({ cell_code, total_qty, whole_box_batches, products })
  }

  groups.sort((a, b) => a.cell_code.localeCompare(b.cell_code))
  return groups
}

export function FfInboundSortingPanel({
  token,
  requestId,
  warehouseId,
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
  const [selectedBoxId, setSelectedBoxId] = useState<string>('')
  const [cellByBoxId, setCellByBoxId] = useState<Record<string, string>>({})
  const [partialQtyByKey, setPartialQtyByKey] = useState<Record<string, string>>({})
  const [putawayHistory, setPutawayHistory] = useState<PutawayHistoryRow[]>([])
  const [historyLoadFailed, setHistoryLoadFailed] = useState(false)

  const productMetaById = useMemo(() => {
    const m = new Map<string, { sku_code: string; product_name: string }>()
    for (const box of boxes) {
      for (const ln of box.lines) {
        m.set(ln.product_id, { sku_code: ln.sku_code, product_name: ln.product_name })
      }
    }
    return m
  }, [boxes])

  const locationIdByCode = useMemo(() => {
    const m = new Map<string, string>()
    for (const loc of locations) {
      m.set(loc.code, loc.id)
    }
    return m
  }, [locations])

  const loadPutawayHistory = useCallback(async () => {
    const res = await fetch(
      apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
      { headers: authHeaders },
    )
    if (!res.ok) {
      setPutawayHistory([])
      setHistoryLoadFailed(true)
      return
    }
    setHistoryLoadFailed(false)
    setPutawayHistory((await res.json()) as PutawayHistoryRow[])
  }, [authHeaders, requestId])

  useEffect(() => {
    void loadPutawayHistory()
  }, [loadPutawayHistory, boxes])

  const putawayHistoryByBoxId = useMemo(() => {
    const m = new Map<string, PutawayHistoryRow[]>()
    for (const row of putawayHistory) {
      if (!row.box_id) {
        continue
      }
      const list = m.get(row.box_id) ?? []
      list.push(row)
      m.set(row.box_id, list)
    }
    return m
  }, [putawayHistory])

  const closedBoxes = useMemo(
    () =>
      boxes
        .filter((b) => b.intake_closed_at != null)
        .sort((a, b) => a.box_number - b.box_number),
    [boxes],
  )

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

  useEffect(() => {
    void loadLocations()
  }, [loadLocations])

  useEffect(() => {
    if (closedBoxes.length === 0) {
      setSelectedBoxId('')
      return
    }
    if (!selectedBoxId || !closedBoxes.some((b) => b.id === selectedBoxId)) {
      const firstWithRemain = closedBoxes.find((b) => b.remaining_qty > 0)
      setSelectedBoxId(firstWithRemain?.id ?? closedBoxes[0]!.id)
    }
  }, [closedBoxes, selectedBoxId])

  const putawayBox = async (
    boxId: string,
    storageLocationId: string,
    lines: { product_id: string; quantity: number }[] | null,
  ) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/boxes/${boxId}/putaway`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            storage_location_id: storageLocationId,
            lines: lines ?? undefined,
          }),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await onReload()
      await loadPutawayHistory()
      setPartialQtyByKey({})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось разложить короб.')
    } finally {
      setBusy(false)
    }
  }

  const putawayWholeBoxToLocation = async (box: SortingBox, storageLocationId: string) => {
    if (!storageLocationId.trim()) {
      setError('Выберите ячейку.')
      return
    }
    await putawayBox(box.id, storageLocationId, null)
  }

  const putawayPartialLine = async (box: SortingBox, line: BoxLine) => {
    const locId = cellByBoxId[box.id]?.trim()
    if (!locId) {
      setError('Выберите ячейку для разкладки.')
      return
    }
    const key = `${box.id}:${line.product_id}`
    const raw = partialQtyByKey[key] ?? String(line.remaining_qty)
    const qty = Math.floor(Number(raw))
    if (!Number.isFinite(qty) || qty < 1) {
      setError('Укажите количество ≥ 1.')
      return
    }
    if (qty > line.remaining_qty) {
      setError(`В коробе осталось ${line.remaining_qty} шт.`)
      return
    }
    await putawayBox(box.id, locId, [{ product_id: line.product_id, quantity: qty }])
  }

  const sortingPackLines = useMemo(() => {
    const m = new Map<string, { product_id: string; sku_code: string; product_name: string; quantity: number }>()
    for (const box of closedBoxes) {
      for (const ln of box.lines) {
        if (ln.remaining_qty <= 0) {
          continue
        }
        const prev = m.get(ln.product_id)
        if (prev) {
          prev.quantity += ln.remaining_qty
        } else {
          m.set(ln.product_id, {
            product_id: ln.product_id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
            quantity: ln.remaining_qty,
          })
        }
      }
    }
    return Array.from(m.values())
  }, [closedBoxes])

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

  if (closedBoxes.length === 0) {
    return (
      <Alert severity="info" data-testid="ff-sorting-no-boxes">
        Нет закрытых коробов для разкладки. Завершите приёмку в разделе «Приёмка».
      </Alert>
    )
  }

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
        {!completed && sortingRemainingQty > 0 ? (
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
      </Stack>

      {locations.length === 0 ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="ff-sorting-no-locations">
          На складе нет ячеек хранения — создайте их в разделе «Ячейки».
        </Alert>
      ) : null}

      <Stack spacing={2}>
        {closedBoxes.map((box) => {
          const done = completed || box.remaining_qty <= 0
          const cellId = cellByBoxId[box.id] ?? ''
          const boxHistory = resolveBoxPutawayHistory(
            box.id,
            closedBoxes,
            putawayHistory,
            putawayHistoryByBoxId,
          )
          const cellGroups = buildCellPutawayGroups(boxHistory, productMetaById)
          const boxPostedQty = box.lines.reduce((s, ln) => s + ln.posted_qty, 0)
          const showPutawayBlock = cellGroups.length > 0 || boxPostedQty > 0
          const usedCellCodes = new Set(cellGroups.map((g) => g.cell_code))

          return (
            <Paper
              key={box.id}
              variant="outlined"
              sx={{
                p: 2,
                ...(done
                  ? {
                      opacity: 0.72,
                      bgcolor: (theme) => alpha(theme.palette.success.main, 0.06),
                    }
                  : selectedBoxId === box.id
                    ? {
                        borderColor: (theme) => theme.palette.primary.main,
                        borderWidth: 2,
                      }
                    : null),
              }}
              data-testid="ff-sorting-box-card"
              data-box-id={box.id}
              onClick={() => setSelectedBoxId(box.id)}
            >
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1.5}
                sx={{ mb: 1.5, alignItems: { sm: 'center' } }}
              >
                <Box sx={{ flexGrow: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                    Короб № {box.box_number}
                  </Typography>
                  <Typography variant="body2" component="code" color="text.secondary">
                    {box.internal_barcode}
                  </Typography>
                </Box>
                <Chip
                  size="small"
                  label={done ? 'Разложен' : `Осталось ${box.remaining_qty} шт`}
                  color={done ? 'success' : 'warning'}
                  variant="outlined"
                  data-testid="ff-sorting-box-remaining"
                />
              </Stack>

              <Box onClick={(e) => e.stopPropagation()}>
                <TableContainer>
                <Table size="small" data-testid="ff-sorting-box-lines">
                  <TableHead>
                    <TableRow>
                      <FfProductTableHeadCells />
                      <TableCell align="right">В коробе</TableCell>
                      <TableCell align="right">Разложено</TableCell>
                      <TableCell align="right">Остаток</TableCell>
                      {!done ? <TableCell align="right">Частично</TableCell> : null}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {box.lines.map((ln) => {
                      const key = `${box.id}:${ln.product_id}`
                      const displayMeta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                      return (
                        <TableRow key={ln.id} data-testid="ff-sorting-box-line">
                          <FfProductLineCells
                            meta={displayMeta}
                            printTestId={`ff-sorting-line-print-${ln.id}`}
                          />
                          <TableCell align="right">{ln.quantity}</TableCell>
                          <TableCell align="right">{ln.posted_qty}</TableCell>
                          <TableCell align="right">{ln.remaining_qty}</TableCell>
                          {!done && ln.remaining_qty > 0 ? (
                            <TableCell align="right">
                              <Stack
                                direction="row"
                                spacing={0.5}
                                sx={{ justifyContent: 'flex-end' }}
                              >
                                <TextField
                                  type="number"
                                  size="small"
                                  value={partialQtyByKey[key] ?? ''}
                                  placeholder={String(ln.remaining_qty)}
                                  disabled={busy}
                                  onChange={(e) =>
                                    setPartialQtyByKey((prev) => ({
                                      ...prev,
                                      [key]: e.target.value,
                                    }))
                                  }
                                  slotProps={{
                                    htmlInput: {
                                      min: 1,
                                      max: ln.remaining_qty,
                                      'data-testid': 'ff-sorting-partial-qty',
                                    },
                                  }}
                                  sx={{ width: 88 }}
                                />
                                <Button
                                  size="small"
                                  variant="outlined"
                                  disabled={busy || !cellId}
                                  onClick={() => void putawayPartialLine(box, ln)}
                                  data-testid="ff-sorting-partial-apply"
                                >
                                  OK
                                </Button>
                              </Stack>
                            </TableCell>
                          ) : !done ? (
                            <TableCell />
                          ) : null}
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                </TableContainer>

                {!done ? (
                  <Stack spacing={1.5} sx={{ mt: 1.5, mb: 1.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      Разложить остаток
                    </Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                      <FormControl size="small" sx={{ minWidth: 200, flexGrow: 1 }}>
                        <InputLabel id={`ff-sort-cell-${box.id}`}>Ячейка</InputLabel>
                        <Select
                          labelId={`ff-sort-cell-${box.id}`}
                          label="Ячейка"
                          value={cellId}
                          disabled={busy || locations.length === 0}
                          onChange={(e) =>
                            setCellByBoxId((prev) => ({
                              ...prev,
                              [box.id]: String(e.target.value),
                            }))
                          }
                          data-testid="ff-sorting-box-location"
                        >
                          <MenuItem value="">
                            <em>Выберите ячейку</em>
                          </MenuItem>
                          {locations.map((loc) => (
                            <MenuItem key={loc.id} value={loc.id}>
                              {loc.code}
                              {usedCellCodes.has(loc.code) ? ' (уже есть)' : ''}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <Button
                        variant="contained"
                        disabled={busy || !cellId}
                        onClick={() => void putawayWholeBoxToLocation(box, cellId)}
                        data-testid="ff-sorting-box-putaway-whole"
                      >
                        Весь короб в ячейку
                      </Button>
                    </Stack>
                    {cellGroups.length > 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        Или «Весь остаток короба сюда» в блоке «Уже в ячейках» ниже.
                      </Typography>
                    ) : null}
                  </Stack>
                ) : null}

                {showPutawayBlock ? (
                  <Box sx={{ mt: 2 }} data-testid="ff-sorting-putaway-history">
                    <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                      Уже в ячейках
                    </Typography>
                    {historyLoadFailed ? (
                      <Alert severity="warning" sx={{ mb: 1 }}>
                        Не удалось загрузить историю разкладки. Обновите страницу.
                      </Alert>
                    ) : null}
                    {cellGroups.length === 0 && boxPostedQty > 0 ? (
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        Разложено {boxPostedQty} шт, но детализация по ячейкам недоступна (старая
                        разкладка).
                      </Typography>
                    ) : null}
                    <Stack spacing={1.25}>
                      {cellGroups.map((group) => {
                        const locId = locationIdByCode.get(group.cell_code) ?? ''
                        return (
                          <Paper
                            key={group.cell_code}
                            variant="outlined"
                            sx={{
                              p: 1.25,
                              bgcolor: (theme) => alpha(theme.palette.info.main, 0.04),
                            }}
                            data-testid="ff-sorting-putaway-cell-group"
                            data-cell-code={group.cell_code}
                          >
                            <Stack
                              direction="row"
                              spacing={1}
                              sx={{ mb: 1, alignItems: 'center', flexWrap: 'wrap' }}
                            >
                              <Chip
                                label={group.cell_code}
                                color="info"
                                size="small"
                                sx={{ fontWeight: 700 }}
                                data-testid="ff-sorting-putaway-cell-summary"
                              />
                              <Typography variant="caption" color="text.secondary">
                                всего {group.total_qty} шт
                              </Typography>
                            </Stack>

                            <Stack spacing={0.75} sx={{ mb: !done && locId ? 1 : 0 }}>
                              {group.whole_box_batches.map((batch) => (
                                <Box
                                  key={batch.created_at}
                                  data-testid="ff-sorting-putaway-whole-box-row"
                                >
                                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                    Короб № {box.box_number}{' '}
                                    <Typography
                                      component="span"
                                      variant="body2"
                                      color="text.secondary"
                                      sx={{ fontWeight: 400 }}
                                    >
                                      {box.internal_barcode} — {batch.total_qty} шт
                                    </Typography>
                                  </Typography>
                                  <Stack component="ul" sx={{ m: 0, pl: 2.5, mt: 0.25 }}>
                                    {batch.products.map((p) => (
                                      <Typography
                                        key={`${batch.created_at}-${p.product_id}`}
                                        component="li"
                                        variant="body2"
                                        color="text.secondary"
                                      >
                                        {p.sku_code} · {p.product_name} — {p.quantity} шт
                                      </Typography>
                                    ))}
                                  </Stack>
                                </Box>
                              ))}
                              {group.products.map((p) => (
                                <Typography
                                  key={p.product_id}
                                  variant="body2"
                                  data-testid="ff-sorting-putaway-product-row"
                                >
                                  {p.sku_code} · {p.product_name} —{' '}
                                  <strong>{p.quantity} шт</strong>
                                </Typography>
                              ))}
                            </Stack>

                            {!done && locId ? (
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={busy}
                                onClick={() => void putawayWholeBoxToLocation(box, locId)}
                                data-testid="ff-sorting-cell-putaway-whole"
                              >
                                Весь остаток короба сюда
                              </Button>
                            ) : null}
                          </Paper>
                        )
                      })}
                    </Stack>
                  </Box>
                ) : null}
              </Box>
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
