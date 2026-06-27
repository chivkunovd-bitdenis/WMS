import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
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
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type PickOptionLocation = {
  storage_location_id: string
  location_code: string
  quantity: number
  reserved: number
  available: number
}

type PickOptionProduct = {
  product_id: string
  sku_code: string
  product_name: string
  planned_qty: number
  picked_qty: number
  locations: PickOptionLocation[]
}

type Props = {
  open: boolean
  onClose: () => void
  requestId: string
  boxId: string
  boxLabel: string
  boxClosed: boolean
  token: string
  addressStorageEnabled: boolean
  packagingGateActive: boolean
  catalogById: Map<string, WbProductPickerCatalogRow>
  warehouseStockByProductId: Map<string, number>
  onUpdated: () => Promise<void>
  onAddSuccess?: (quantity: number) => void
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
  const planRemaining = Math.max(0, row.planned_qty - row.picked_qty)
  const physical = physicalAvailable(
    row,
    addressStorageEnabled,
    activeLocationId,
    warehouseStockByProductId,
  )
  return Math.min(planRemaining, physical)
}

export function FfMarketplaceUnloadBoxAddDialog({
  open,
  onClose,
  requestId,
  boxId,
  boxLabel,
  boxClosed,
  token,
  addressStorageEnabled,
  packagingGateActive,
  catalogById,
  warehouseStockByProductId,
  onUpdated,
  onAddSuccess,
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
      return
    }
    void loadPickOptions()
  }, [open, loadPickOptions])

  const addManual = async (productId: string, quantity: number) => {
    if (boxClosed || packagingGateActive) {
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

  const doScan = async () => {
    if (boxClosed || packagingGateActive) {
      return
    }
    const raw = scanBarcode.trim()
    if (!raw) {
      setError('Введите штрихкод.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const scanBody: { barcode: string; quantity: number; storage_location_id?: string } = {
        barcode: raw,
        quantity: 1,
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
        }
        if (j.kind === 'location' && j.storage_location_id) {
          setActiveLocationId(j.storage_location_id)
          setActiveLocationCode(j.location_code ?? j.storage_location_id)
          setScanBarcode('')
          return
        }
        setScanBarcode('')
        onAddSuccess?.(1)
        await onUpdated()
        await loadPickOptions({ silent: true })
        return
      }
      if (addressStorageEnabled && !activeLocationId) {
        setError('Сначала отсканируйте ячейку.')
        return
      }
      setError(await readApiErrorMessage(scanRes))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    } finally {
      setBusy(false)
    }
  }

  const gateBlocked = boxClosed || packagingGateActive

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      data-testid="ff-mp-box-add-dialog"
    >
      <DialogTitle sx={{ pr: 6 }}>
        Добавить товары в короб
        <Typography variant="body2" color="text.secondary">
          {boxLabel}
        </Typography>
        <IconButton
          aria-label="Закрыть"
          onClick={onClose}
          sx={{ position: 'absolute', right: 8, top: 8 }}
          data-testid="ff-mp-box-add-close"
        >
          <CloseOutlined />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          {packagingGateActive ? (
            <Alert severity="warning">Сначала завершите упаковку товара.</Alert>
          ) : null}
          {boxClosed ? (
            <Alert severity="info">Короб закрыт — добавление недоступно.</Alert>
          ) : null}
          {error ? (
            <Alert severity="error" data-testid="ff-mp-box-add-error">
              {error}
            </Alert>
          ) : null}

          {!gateBlocked ? (
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              sx={{ alignItems: 'center' }}
            >
              {addressStorageEnabled ? (
                activeLocationCode ? (
                  <Chip
                    size="small"
                    label={`Ячейка: ${activeLocationCode}`}
                    data-testid="ff-mp-box-add-active-location"
                  />
                ) : (
                  <Typography variant="caption" color="warning.main">
                    Сначала отсканируйте ячейку
                  </Typography>
                )
              ) : null}
              <TextField
                size="small"
                label={
                  addressStorageEnabled ? 'Штрихкод ячейки / товара' : 'Штрихкод товара'
                }
                value={scanBarcode}
                onChange={(e) => setScanBarcode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void doScan()
                  }
                }}
                disabled={busy || initialLoading}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'ff-mp-box-add-scan-input' } }}
                data-testid="ff-mp-box-add-scan"
              />
              <Button
                variant="contained"
                onClick={() => void doScan()}
                disabled={busy || initialLoading}
                data-testid="ff-mp-box-add-scan-submit"
              >
                Скан
              </Button>
            </Stack>
          ) : null}

          {initialLoading ? (
            <Typography variant="body2" color="text.secondary">
              Загрузка…
            </Typography>
          ) : (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" data-testid="ff-mp-box-add-table">
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
                      return (
                        <TableRow
                          key={row.product_id}
                          data-testid={`ff-mp-box-add-row-${row.product_id}`}
                        >
                          <TableCell>
                            <ProductPhotoThumb
                              src={cat?.wb_primary_image_url}
                              alt={row.product_name}
                            />
                          </TableCell>
                          <TableCell>{row.sku_code}</TableCell>
                          <TableCell>{row.product_name}</TableCell>
                          <TableCell align="right">{row.planned_qty}</TableCell>
                          <TableCell align="right">{row.picked_qty}</TableCell>
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
                              slotProps={{ htmlInput: { min: 1, 'data-testid': `ff-mp-box-add-qty-${row.product_id}` } }}
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
  )
}
