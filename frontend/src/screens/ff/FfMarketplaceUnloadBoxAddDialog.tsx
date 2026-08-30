import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useBarcodeScanner } from '../../hooks/useBarcodeScanner'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import { apiUrl } from '../../api'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import type { WbProductPickerCatalogRow } from '../../components/WbProductPickerDialog'
import { storageLocationLabel } from '../../utils/inboundQueues'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { resolveProductIdByBarcode } from '../../utils/resolveProductByBarcode'
import {
  boxFillDialogContentSx,
  boxFillDialogPaperSx,
  boxFillProductCellSx,
  boxFillTableScrollSx,
} from './boxFillDialogLayout'

type PickOptionLocation = {
  storage_location_id: string
  location_code: string
  quantity: number
  reserved: number
  available: number
}

type LocationOption = {
  id: string
  code: string
  available: number
}

type PickOptionProduct = {
  product_id: string
  sku_code: string
  product_name: string
  planned_qty: number
  picked_qty: number
  /** Сколько уже разложено по коробам. Упаковка считает остаток по нему. */
  boxed_qty?: number
  locations: PickOptionLocation[]
}

type Props = {
  open: boolean
  onClose: () => void
  requestId: string
  boxId: string
  boxLabel: string
  readOnly: boolean
  token: string
  addressStorageEnabled: boolean
  catalogById: Map<string, WbProductPickerCatalogRow>
  warehouseStockByProductId: Map<string, number>
  onUpdated: () => Promise<void>
  onAddSuccess?: (quantity: number) => void
  onProductScanned?: (line: {
    id: string
    product_id: string
    sku_code: string
    product_name: string
    quantity: number
  }) => void
}

function physicalAvailable(
  row: PickOptionProduct,
  addressStorageEnabled: boolean,
  activeLocationId: string | null,
  warehouseStockByProductId: Map<string, number>,
): number {
  if (!addressStorageEnabled) {
    return warehouseStockByProductId.get(row.product_id) ?? 0
  }
  if (activeLocationId) {
    const loc = row.locations.find((l) => l.storage_location_id === activeLocationId)
    return loc?.available ?? 0
  }
  return row.locations.reduce((sum, l) => sum + l.available, 0)
}

function addableQty(
  row: PickOptionProduct,
  addressStorageEnabled: boolean,
  activeLocationId: string | null,
  warehouseStockByProductId: Map<string, number>,
): number {
  // Считаем остаток к раскладке по коробам, а не по подобранному. Раньше здесь
  // стояло «план − подобрано»: после полного подбора выходил ноль, кнопка
  // «Добавить» гасла навсегда, и отгрузку нельзя было завершить в принципе.
  // Подобранное уже снято со склада — его достаточно переложить в короб.
  const boxed = row.boxed_qty ?? 0
  const leftToBox = Math.max(0, row.planned_qty - boxed)
  const alreadyPicked = Math.max(0, row.picked_qty - boxed)
  const physical = physicalAvailable(
    row,
    addressStorageEnabled,
    activeLocationId,
    warehouseStockByProductId,
  )
  return Math.min(leftToBox, alreadyPicked + physical)
}

function locationAddableQty(row: PickOptionProduct, locationId: string): number {
  const planRemaining = Math.max(0, row.planned_qty - row.picked_qty)
  if (planRemaining < 1) {
    return 0
  }
  const loc = row.locations.find((l) => l.storage_location_id === locationId)
  if (!loc || loc.available < 1) {
    return 0
  }
  return Math.min(planRemaining, loc.available)
}

function hasStorageCellBalances(locations: PickOptionLocation[]): boolean {
  return locations.some((l) => l.location_code !== 'Без ячеек')
}

function sortingZoneAvailable(locations: PickOptionLocation[]): number {
  return locations.find((l) => l.location_code === 'Без ячеек')?.available ?? 0
}

function productNeedsExplicitLocation(
  row: PickOptionProduct,
  addressStorageEnabled: boolean,
): boolean {
  if (!addressStorageEnabled) {
    return false
  }
  return hasStorageCellBalances(row.locations)
}

function looksLikeReadyBoxBarcode(raw: string): boolean {
  return raw.startsWith('WHB-') || raw.startsWith('INB-')
}

export function FfMarketplaceUnloadBoxAddDialog({
  open,
  onClose,
  requestId,
  boxId,
  boxLabel,
  readOnly,
  token,
  addressStorageEnabled,
  catalogById,
  warehouseStockByProductId,
  onUpdated,
  onAddSuccess,
  onProductScanned,
}: Props) {
  const authHeaders = useMemo(
    () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }),
    [token],
  )
  const [pickOptions, setPickOptions] = useState<PickOptionProduct[]>([])
  const [initialLoading, setInitialLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scanBarcode, setScanBarcode] = useState('')
  const [activeLocationId, setActiveLocationId] = useState<string | null>(null)
  const [activeLocationCode, setActiveLocationCode] = useState<string | null>(null)
  const [manualQtyByProduct, setManualQtyByProduct] = useState<Record<string, string>>({})
  const [readyBoxConfirmOpen, setReadyBoxConfirmOpen] = useState(false)
  const [readyBoxOverPlanOpen, setReadyBoxOverPlanOpen] = useState(false)
  const [pendingReadyBoxBarcode, setPendingReadyBoxBarcode] = useState<string | null>(null)
  const [lastScannedProductId, setLastScannedProductId] = useState<string | null>(null)
  const scanQueueRef = useRef<Promise<void>>(Promise.resolve())
  const scanChangedRef = useRef(false)

  const catalogRows = useMemo(
    () =>
      pickOptions
        .map((row) => catalogById.get(row.product_id))
        .filter((row): row is WbProductPickerCatalogRow => row != null),
    [catalogById, pickOptions],
  )

  const locationOptions = useMemo(() => {
    const byId = new Map<string, LocationOption>()
    for (const row of pickOptions) {
      const rowRemaining = Math.max(0, row.planned_qty - row.picked_qty)
      if (rowRemaining < 1) {
        continue
      }
      for (const loc of row.locations) {
        const addable = locationAddableQty(row, loc.storage_location_id)
        if (addable > 0) {
          const current = byId.get(loc.storage_location_id)
          if (current) {
            current.available += addable
          } else {
            byId.set(loc.storage_location_id, {
              id: loc.storage_location_id,
              code: storageLocationLabel(loc.location_code),
              available: addable,
            })
          }
        }
      }
    }
    return [...byId.values()].sort((a, b) => a.code.localeCompare(b.code))
  }, [pickOptions])

  const sortingBufferPickAllowed = useMemo(
    () =>
      addressStorageEnabled &&
      !activeLocationId &&
      pickOptions.some(
        (row) =>
          sortingZoneAvailable(row.locations) > 0 &&
          !productNeedsExplicitLocation(row, addressStorageEnabled),
      ),
    [activeLocationId, addressStorageEnabled, pickOptions],
  )

  const scanPlaceholder = useMemo(() => {
    if (addressStorageEnabled && !activeLocationId) {
      return 'Штрихкод ячейки, товара или готового короба (WHB-…)'
    }
    if (addressStorageEnabled) {
      return 'Штрихкод товара или готового короба (WHB-…)'
    }
    return 'Штрихкод товара или готового короба (WHB-…)'
  }, [addressStorageEnabled, activeLocationId])

  const loadPickOptions = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) {
      setInitialLoading(true)
    }
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${requestId}/pick-options`),
        { headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        if (!opts?.silent) {
          setPickOptions([])
        }
        return
      }
      setPickOptions((await res.json()) as PickOptionProduct[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить товары.')
      if (!opts?.silent) {
        setPickOptions([])
      }
    } finally {
      if (!opts?.silent) {
        setInitialLoading(false)
      }
    }
  }, [authHeaders, requestId])

  useEffect(() => {
    if (!open) {
      setScanBarcode('')
      setActiveLocationId(null)
      setActiveLocationCode(null)
      setManualQtyByProduct({})
      setError(null)
      setReadyBoxConfirmOpen(false)
      setReadyBoxOverPlanOpen(false)
      setPendingReadyBoxBarcode(null)
      setLastScannedProductId(null)
      scanChangedRef.current = false
      return
    }
    void loadPickOptions()
  }, [open, loadPickOptions])

  const closeDialog = () => {
    const needsRefresh = scanChangedRef.current
    scanChangedRef.current = false
    onClose()
    if (needsRefresh) {
      void onUpdated()
    }
  }

  const selectLocation = (locationId: string) => {
    const loc = locationOptions.find((l) => l.id === locationId)
    setActiveLocationId(locationId || null)
    setActiveLocationCode(loc?.code ?? null)
  }

  const addManual = async (productId: string, quantity: number) => {
    if (readOnly) {
      return
    }
    const row = pickOptions.find((p) => p.product_id === productId)
    if (
      row &&
      productNeedsExplicitLocation(row, addressStorageEnabled) &&
      !activeLocationId
    ) {
      setError('Выберите ячейку или отсканируйте её штрихкод.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const body: {
        product_id: string
        quantity: number
        storage_location_id?: string
      } = { product_id: productId, quantity }
      if (addressStorageEnabled && activeLocationId) {
        body.storage_location_id = activeLocationId
      }
      const res = await fetch(
        apiUrl(
          `/operations/marketplace-unload-requests/${requestId}/boxes/${boxId}/manual-line`,
        ),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify(body),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      onAddSuccess?.(quantity)
      await onUpdated()
      await loadPickOptions({ silent: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось добавить товар.')
    } finally {
      setBusy(false)
    }
  }

  const runScan = async (barcode: string, allowOverPlan: boolean) => {
    const readyBoxScan = looksLikeReadyBoxBarcode(barcode)
    if (readyBoxScan) setBusy(true)
    setError(null)
    try {
      const scanBody: {
        barcode: string
        product_id?: string
        quantity: number
        storage_location_id?: string
        allow_over_plan?: boolean
      } = {
        barcode,
        quantity: 1,
        allow_over_plan: allowOverPlan,
      }
      const productId = resolveProductIdByBarcode(catalogRows, barcode)
      if (productId) {
        scanBody.product_id = productId
      }
      if (addressStorageEnabled && activeLocationId) {
        scanBody.storage_location_id = activeLocationId
      }

      const scanRes = await fetch(
        apiUrl(
          `/operations/marketplace-unload-requests/${requestId}/boxes/${boxId}/scan`,
        ),
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify(scanBody),
        },
      )
      if (scanRes.ok) {
        const j = (await scanRes.json()) as {
          kind: string
          storage_location_id?: string | null
          location_code?: string | null
          total_qty?: number | null
          product_id?: string | null
          id?: string | null
          sku_code?: string | null
          product_name?: string | null
          quantity?: number | null
          picked_qty?: number | null
        }
        if (j.kind === 'location' && j.storage_location_id) {
          setActiveLocationId(j.storage_location_id)
          setActiveLocationCode(j.location_code ?? j.storage_location_id)
          setScanBarcode('')
          return
        }
        if (j.kind === 'ready_box') {
          setScanBarcode('')
          onAddSuccess?.(j.total_qty ?? 1)
          scanChangedRef.current = true
          await onUpdated()
          await loadPickOptions({ silent: true })
          return
        }
        setScanBarcode('')
        if (j.product_id) {
          setPickOptions((current) =>
            current.map((row) => {
              if (row.product_id !== j.product_id) return row
              return {
                ...row,
                picked_qty: j.picked_qty ?? row.picked_qty + 1,
                locations: row.locations.map((location) =>
                  location.storage_location_id === j.storage_location_id
                    ? { ...location, available: Math.max(0, location.available - 1) }
                    : location,
                ),
              }
            }),
          )
          setLastScannedProductId(j.product_id)
          if (j.id && j.sku_code && j.product_name && j.quantity != null) {
            onProductScanned?.({
              id: j.id,
              product_id: j.product_id,
              sku_code: j.sku_code,
              product_name: j.product_name,
              quantity: j.quantity,
            })
          }
        }
        scanChangedRef.current = true
        onAddSuccess?.(1)
        return
      }
      const errText = await scanRes.text()
      let errDetail: string | null = null
      try {
        const errBody = JSON.parse(errText) as { detail?: unknown }
        errDetail = typeof errBody.detail === 'string' ? errBody.detail : null
      } catch {
        errDetail = null
      }
      if (errDetail === 'plan_limit_exceeded' && !allowOverPlan) {
        setPendingReadyBoxBarcode(barcode)
        setReadyBoxOverPlanOpen(true)
        return
      }
      if (addressStorageEnabled && !activeLocationId && errDetail === 'location_required') {
        setError('Сначала выберите ячейку или отсканируйте её штрихкод.')
        return
      }
      if (errDetail === 'insufficient_available') {
        setError(
          'Недостаточно остатка в выбранной ячейке. Если товар ещё в зоне сортировки — не выбирайте ячейку и сканируйте товар снова.',
        )
        return
      }
      setError(errDetail ?? errText.slice(0, 200) ?? 'Не удалось выполнить скан.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    } finally {
      if (readyBoxScan) setBusy(false)
    }
  }

  const enqueueScan = (barcode: string, allowOverPlan: boolean) => {
    const job = scanQueueRef.current.then(() => runScan(barcode, allowOverPlan))
    scanQueueRef.current = job.catch(() => undefined)
    return job
  }

  const doScan = (rawInput?: string) => {
    if (readOnly) {
      return
    }
    const raw = (rawInput ?? scanBarcode).trim()
    if (!raw) {
      setError('Введите штрихкод.')
      return
    }
    if (looksLikeReadyBoxBarcode(raw)) {
      setPendingReadyBoxBarcode(raw)
      setReadyBoxConfirmOpen(true)
      return
    }
    void enqueueScan(raw, false)
  }

  useBarcodeScanner({
    enabled: open && !readOnly && !readyBoxConfirmOpen && !readyBoxOverPlanOpen,
    onScan: doScan,
  })

  const confirmReadyBox = () => {
    setReadyBoxConfirmOpen(false)
    const barcode = pendingReadyBoxBarcode
    if (!barcode) {
      return
    }
    void enqueueScan(barcode, false)
  }

  const confirmReadyBoxOverPlan = () => {
    setReadyBoxOverPlanOpen(false)
    const barcode = pendingReadyBoxBarcode
    if (!barcode) {
      return
    }
    void enqueueScan(barcode, true)
  }

  const gateBlocked = readOnly

  return (
    <>
      <Dialog
        open={open}
        onClose={closeDialog}
        maxWidth={false}
        fullWidth
        data-testid="ff-mp-box-add-dialog"
        slotProps={{ paper: { sx: boxFillDialogPaperSx } }}
      >
        <DialogTitle sx={{ pr: 6, flexShrink: 0 }}>
          Наполнить короб
          <Typography variant="body2" color="text.secondary">
            {boxLabel}
          </Typography>
          <IconButton
            aria-label="Закрыть"
            onClick={closeDialog}
            sx={{ position: 'absolute', right: 8, top: 8 }}
            data-testid="ff-mp-box-add-close"
          >
            <CloseOutlined />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={boxFillDialogContentSx}>
          <Stack spacing={2} sx={{ flex: 1, minHeight: 0 }}>
            {readOnly ? (
              <Alert severity="info">Отгрузка проведена — состав короба только для просмотра.</Alert>
            ) : null}
            {error ? (
              <Alert severity="error" data-testid="ff-mp-box-add-error">
                {error}
              </Alert>
            ) : null}

            {!gateBlocked ? (
              <Stack spacing={1}>
                {addressStorageEnabled ? (
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: 'center' }}>
                    <FormControl size="small" sx={{ minWidth: 200 }} data-testid="ff-mp-box-add-location-select">
                      <InputLabel id="ff-mp-box-add-location-label">Ячейка</InputLabel>
                      <Select
                        labelId="ff-mp-box-add-location-label"
                        label="Ячейка"
                        value={activeLocationId ?? ''}
                        onChange={(e) => selectLocation(String(e.target.value))}
                        disabled={busy || initialLoading || locationOptions.length === 0}
                      >
                        <MenuItem value="">
                          <em>Не выбрана</em>
                        </MenuItem>
                        {locationOptions.map((loc) => (
                          <MenuItem key={loc.id} value={loc.id}>
                            {loc.code} · {loc.available} шт
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    {activeLocationCode ? (
                      <Chip
                        size="small"
                        label={`Ячейка: ${activeLocationCode}`}
                        onDelete={() => {
                          setActiveLocationId(null)
                          setActiveLocationCode(null)
                        }}
                        data-testid="ff-mp-box-add-active-location"
                      />
                    ) : sortingBufferPickAllowed ? (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        data-testid="ff-mp-box-add-sorting-buffer-hint"
                      >
                        Остаток в зоне сортировки — можно сканировать товар без выбора ячейки
                      </Typography>
                    ) : addressStorageEnabled && locationOptions.length === 0 ? (
                      <Typography variant="caption" color="warning.main">
                        Нет доступных ячеек для выбора
                      </Typography>
                    ) : (
                      <Typography variant="caption" color="warning.main">
                        Выберите ячейку или отсканируйте её
                      </Typography>
                    )}
                  </Stack>
                ) : null}
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1}
                  sx={{ alignItems: 'center' }}
                >
                  <TextField
                    size="small"
                    label={scanPlaceholder}
                    value={scanBarcode}
                    onChange={(e) => setScanBarcode(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        doScan()
                      }
                    }}
                    disabled={busy || initialLoading}
                    fullWidth
                    slotProps={{ htmlInput: { 'data-testid': 'ff-mp-box-add-scan-input' } }}
                    data-testid="ff-mp-box-add-scan"
                  />
                  <Button
                    variant="contained"
                    onClick={() => doScan()}
                    disabled={busy || initialLoading}
                    data-testid="ff-mp-box-add-scan-submit"
                  >
                    Скан
                  </Button>
                </Stack>
              </Stack>
            ) : null}

            {initialLoading ? (
              <Typography variant="body2" color="text.secondary">
                Загрузка…
              </Typography>
            ) : (
              <Box sx={boxFillTableScrollSx}>
                <Table size="small" stickyHeader data-testid="ff-mp-box-add-table">
                  <TableHead>
                    <TableRow>
                      <TableCell width={56} />
                      <TableCell>Артикул</TableCell>
                      <TableCell>Товар</TableCell>
                      <TableCell align="right">План</TableCell>
                      <TableCell align="right">В коробах</TableCell>
                      <TableCell align="right">Доступно</TableCell>
                      <TableCell align="right">Кол-во</TableCell>
                      <TableCell align="right" />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {pickOptions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8}>
                          <Typography variant="body2" color="text.secondary">
                            Нет товаров в плане отгрузки
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ) : (
                      pickOptions.map((row) => {
                        const cat = catalogById.get(row.product_id)
                        const available = addableQty(
                          row,
                          addressStorageEnabled,
                          activeLocationId,
                          warehouseStockByProductId,
                        )
                        const qtyStr = manualQtyByProduct[row.product_id] ?? '1'
                        const qtyNum = Number(qtyStr)
                        const qtyValid = Number.isInteger(qtyNum) && qtyNum >= 1
                        // Ячейка нужна только чтобы снять товар со склада. То, что уже
                        // подобрано, лежит на упаковке и просто перекладывается в короб —
                        // требовать для него ячейку бессмысленно, а на упаковке ячеек
                        // с этим товаром уже и не остаётся.
                        const readyToBox = Math.max(0, row.picked_qty - (row.boxed_qty ?? 0))
                        const needsLocation =
                          productNeedsExplicitLocation(row, addressStorageEnabled) &&
                          !activeLocationId &&
                          qtyNum > readyToBox
                        return (
                          <TableRow
                            key={row.product_id}
                            data-testid={`ff-mp-box-add-row-${row.product_id}`}
                            sx={
                              row.product_id === lastScannedProductId
                                ? {
                                    bgcolor: 'success.main',
                                    boxShadow: (theme) =>
                                      `inset 0 0 0 1px ${theme.palette.success.main}`,
                                    '& td': { bgcolor: 'success.light' },
                                  }
                                : undefined
                            }
                          >
                            <TableCell>
                              <ProductPhotoThumb
                                src={cat?.wb_primary_image_url}
                                alt={row.product_name}
                              />
                            </TableCell>
                            <TableCell sx={boxFillProductCellSx}>{row.sku_code}</TableCell>
                            <TableCell sx={boxFillProductCellSx} title={row.product_name}>
                              {row.product_name}
                            </TableCell>
                            <TableCell align="right">{row.planned_qty}</TableCell>
                            <TableCell align="right">{row.boxed_qty ?? 0}</TableCell>
                            <TableCell align="right" data-testid={`ff-mp-box-add-available-${row.product_id}`}>
                              {available}
                            </TableCell>
                            <TableCell align="right">
                              <TextField
                                size="small"
                                type="number"
                                value={qtyStr}
                                onChange={(e) =>
                                  setManualQtyByProduct((prev) => ({
                                    ...prev,
                                    [row.product_id]: e.target.value,
                                  }))
                                }
                                slotProps={{
                                  htmlInput: {
                                    min: 1,
                                    max: available > 0 ? available : undefined,
                                    'data-testid': `ff-mp-box-add-qty-${row.product_id}`,
                                  },
                                }}
                                sx={{ width: 72 }}
                                disabled={gateBlocked || busy}
                              />
                            </TableCell>
                            <TableCell align="right">
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={
                                  gateBlocked ||
                                  busy ||
                                  needsLocation ||
                                  available < 1 ||
                                  !qtyValid ||
                                  qtyNum > available
                                }
                                onClick={() => void addManual(row.product_id, qtyNum)}
                                data-testid={`ff-mp-box-add-manual-${row.product_id}`}
                              >
                                Добавить
                              </Button>
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </Box>
            )}
          </Stack>
        </DialogContent>
      </Dialog>

      <Dialog
        open={readyBoxConfirmOpen}
        onClose={() => {
          setReadyBoxConfirmOpen(false)
          setPendingReadyBoxBarcode(null)
        }}
        data-testid="ff-mp-box-add-ready-box-dialog"
      >
        <DialogTitle>Добавить готовый короб?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Весь состав готового короба будет добавлен в этот короб отгрузки.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setReadyBoxConfirmOpen(false)
              setPendingReadyBoxBarcode(null)
            }}
            disabled={busy}
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={busy}
            onClick={confirmReadyBox}
            data-testid="ff-mp-box-add-ready-box-confirm"
          >
            Добавить
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={readyBoxOverPlanOpen}
        onClose={() => {
          setReadyBoxOverPlanOpen(false)
          setPendingReadyBoxBarcode(null)
        }}
        data-testid="ff-mp-box-add-over-plan-dialog"
      >
        <DialogTitle>Больше, чем в плане</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            В коробе больше товара, чем осталось по плану. Добавить всё содержимое?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setReadyBoxOverPlanOpen(false)
              setPendingReadyBoxBarcode(null)
            }}
            disabled={busy}
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={busy}
            onClick={confirmReadyBoxOverPlan}
            data-testid="ff-mp-box-add-over-plan-confirm"
          >
            Добавить всё
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
