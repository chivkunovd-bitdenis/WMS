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

type Props = {
  token: string
  requestId: string
  warehouseId: string
  boxes: SortingBox[]
  sortingRemainingQty: number
  onReload: () => Promise<void>
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
                      <TableCell align="right">Остаток</TableCell>
                      {!done ? <TableCell align="right">Частично</TableCell> : null}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {box.lines.map((ln) => {
                      const key = `${box.id}:${ln.product_id}`
                      return (
                        <TableRow key={ln.id} data-testid="ff-sorting-box-line">
                          <TableCell>{ln.sku_code}</TableCell>
                          <TableCell>{ln.product_name}</TableCell>
                          <TableCell align="right">{ln.quantity}</TableCell>
                          <TableCell align="right">{ln.posted_qty}</TableCell>
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
