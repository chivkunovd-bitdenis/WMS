import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { apiUrl } from '../../api'
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

type Props = {
  token: string
  requestId: string
  warehouseId: string
  boxes: SortingBox[]
  sortingRemainingQty: number
  onReload: () => Promise<void>
}

function groupQtyByCell(rows: PutawayHistoryRow[]): [string, number][] {
  const m = new Map<string, number>()
  for (const h of rows) {
    m.set(h.storage_location_code, (m.get(h.storage_location_code) ?? 0) + h.quantity)
  }
  return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]))
}

function productPutawayByCell(
  history: PutawayHistoryRow[],
  productId: string,
): [string, number][] {
  const m = new Map<string, number>()
  for (const h of history) {
    if (h.product_id !== productId) {
      continue
    }
    m.set(h.storage_location_code, (m.get(h.storage_location_code) ?? 0) + h.quantity)
  }
  return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]))
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

function formatPutawayTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) {
    return iso
  }
  return d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}

export function FfInboundSortingPanel({
  token,
  requestId,
  warehouseId,
  boxes,
  sortingRemainingQty,
  onReload,
}: Props) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])
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
    for (const list of m.values()) {
      list.sort((a, b) => a.created_at.localeCompare(b.created_at))
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

  const putawayWholeBox = async (box: SortingBox) => {
    const locId = cellByBoxId[box.id]?.trim()
    if (!locId) {
      setError('Выберите ячейку для короба.')
      return
    }
    await putawayBox(box.id, locId, null)
  }

  const putawayPartialLine = async (box: SortingBox, line: BoxLine) => {
    const locId = cellByBoxId[box.id]?.trim()
    if (!locId) {
      setError('Выберите ячейку.')
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
      </Stack>

      {locations.length === 0 ? (
        <Alert severity="warning" sx={{ mb: 2 }} data-testid="ff-sorting-no-locations">
          На складе нет ячеек хранения — создайте их в «Каталог → Ячейки».
        </Alert>
      ) : null}

      <Stack spacing={2}>
        {closedBoxes.map((box) => {
          const done = box.remaining_qty <= 0
          const cellId = cellByBoxId[box.id] ?? ''
          const boxHistory = resolveBoxPutawayHistory(
            box.id,
            closedBoxes,
            putawayHistory,
            putawayHistoryByBoxId,
          )
          const historyByCell = groupQtyByCell(boxHistory)
          const boxPostedQty = box.lines.reduce((s, ln) => s + ln.posted_qty, 0)
          const showPutawayBlock = boxHistory.length > 0 || boxPostedQty > 0
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

              {showPutawayBlock ? (
                <Box
                  sx={{
                    mb: 1.5,
                    p: 1.5,
                    borderRadius: 1,
                    bgcolor: (theme) => alpha(theme.palette.info.main, 0.06),
                    border: (theme) => `1px solid ${alpha(theme.palette.info.main, 0.2)}`,
                  }}
                  data-testid="ff-sorting-putaway-history"
                >
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                    Уже в ячейках
                  </Typography>
                  {historyLoadFailed ? (
                    <Alert severity="warning" sx={{ mb: 1 }}>
                      Не удалось загрузить историю разкладки. Обновите страницу.
                    </Alert>
                  ) : null}
                  {historyByCell.length > 0 ? (
                    <Stack direction="row" spacing={0.75} sx={{ mb: 1.25, flexWrap: 'wrap' }}>
                      {historyByCell.map(([code, qty]) => (
                        <Chip
                          key={code}
                          size="small"
                          color="info"
                          variant="outlined"
                          label={`${code}: ${qty} шт`}
                          data-testid="ff-sorting-putaway-cell-summary"
                        />
                      ))}
                    </Stack>
                  ) : boxPostedQty > 0 ? (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Разложено {boxPostedQty} шт, но список ячеек пуст — возможно, разкладка была до
                      обновления системы. Следующие операции появятся здесь.
                    </Typography>
                  ) : null}
                  {boxHistory.length > 0 ? (
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Ячейка</TableCell>
                            <TableCell>Артикул</TableCell>
                            <TableCell>Товар</TableCell>
                            <TableCell align="right">Кол-во</TableCell>
                            <TableCell>Когда</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {boxHistory.map((h) => {
                            const meta = productMetaById.get(h.product_id)
                            return (
                              <TableRow key={h.id} data-testid="ff-sorting-putaway-history-row">
                                <TableCell>{h.storage_location_code}</TableCell>
                                <TableCell>{meta?.sku_code ?? '—'}</TableCell>
                                <TableCell>
                                  {meta?.product_name ?? h.product_id.slice(0, 8)}
                                </TableCell>
                                <TableCell align="right">{h.quantity}</TableCell>
                                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                                  {formatPutawayTime(h.created_at)}
                                </TableCell>
                              </TableRow>
                            )
                          })}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  ) : null}
                </Box>
              ) : null}

              {!done ? (
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  sx={{ mb: 1.5 }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <FormControl size="small" sx={{ minWidth: 200, flexGrow: 1 }}>
                    <InputLabel id={`ff-sort-cell-${box.id}`}>Ячейка</InputLabel>
                    <Select
                      labelId={`ff-sort-cell-${box.id}`}
                      label="Ячейка"
                      value={cellId}
                      disabled={busy || locations.length === 0}
                      onChange={(e) =>
                        setCellByBoxId((prev) => ({ ...prev, [box.id]: String(e.target.value) }))
                      }
                      data-testid="ff-sorting-box-location"
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
                  <Button
                    variant="contained"
                    disabled={busy || !cellId}
                    onClick={() => void putawayWholeBox(box)}
                    data-testid="ff-sorting-box-putaway-whole"
                  >
                    Весь короб в ячейку
                  </Button>
                </Stack>
              ) : null}

              <TableContainer>
                <Table size="small" data-testid="ff-sorting-box-lines">
                  <TableHead>
                    <TableRow>
                      <TableCell>Артикул</TableCell>
                      <TableCell>Товар</TableCell>
                      <TableCell align="right">В коробе</TableCell>
                      <TableCell align="right">Разложено</TableCell>
                      <TableCell>По ячейкам</TableCell>
                      <TableCell align="right">Остаток</TableCell>
                      {!done ? <TableCell align="right">Частично</TableCell> : null}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {box.lines.map((ln) => {
                      const key = `${box.id}:${ln.product_id}`
                      const lineCells = productPutawayByCell(boxHistory, ln.product_id)
                      return (
                        <TableRow key={ln.id} data-testid="ff-sorting-box-line">
                          <TableCell>{ln.sku_code}</TableCell>
                          <TableCell>{ln.product_name}</TableCell>
                          <TableCell align="right">{ln.quantity}</TableCell>
                          <TableCell align="right">{ln.posted_qty}</TableCell>
                          <TableCell>
                            {lineCells.length > 0 ? (
                              <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                                {lineCells.map(([code, qty]) => (
                                  <Chip
                                    key={code}
                                    size="small"
                                    variant="outlined"
                                    label={`${code}: ${qty}`}
                                    data-testid="ff-sorting-line-cell-chip"
                                  />
                                ))}
                              </Stack>
                            ) : ln.posted_qty > 0 ? (
                              <Typography variant="caption" color="text.secondary">
                                —
                              </Typography>
                            ) : (
                              <Typography variant="caption" color="text.secondary">
                                ещё не разложено
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell align="right">{ln.remaining_qty}</TableCell>
                          {!done && ln.remaining_qty > 0 ? (
                            <TableCell align="right" onClick={(e) => e.stopPropagation()}>
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
