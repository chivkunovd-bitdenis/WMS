import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
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

type ScanResponse = {
  kind: string
  storage_location_id?: string | null
  location_code?: string | null
  product_id?: string | null
  sku_code?: string | null
  product_name?: string | null
  picked_qty?: number | null
  allocation_quantity?: number | null
}

type Props = {
  token: string
  authHeaders: Record<string, string>
  requestId: string
  disabled?: boolean
  onChanged?: () => void
}

export function FfMpUnloadPickPanel({
  token: _token,
  authHeaders,
  requestId,
  disabled,
  onChanged,
}: Props) {
  const scanInputRef = useRef<HTMLInputElement>(null)
  const [pickOptions, setPickOptions] = useState<PickOptionProduct[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scanBarcode, setScanBarcode] = useState('')
  const [activeLocationId, setActiveLocationId] = useState<string | null>(null)
  const [activeLocationCode, setActiveLocationCode] = useState<string | null>(null)
  const [scanMessage, setScanMessage] = useState<string | null>(null)
  const [manualQtyByProductLocation, setManualQtyByProductLocation] = useState<
    Record<string, string>
  >({})

  const headerMap = useMemo(() => ({ ...authHeaders }), [authHeaders])
  // Без Content-Type FastAPI не разбирает тело и отвечает
  // «body: Input should be a valid dictionary…» — и скан, и ручное добавление падают.
  const jsonHeaderMap = useMemo(
    () => ({ ...authHeaders, 'Content-Type': 'application/json' }),
    [authHeaders],
  )

  const loadPickOptions = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) {
        setLoading(true)
      }
      setError(null)
      setScanMessage(null)
      try {
        const res = await fetch(
          apiUrl(`/operations/marketplace-unload-requests/${requestId}/pick-options`),
          { headers: headerMap },
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
          setLoading(false)
        }
      }
    },
    [headerMap, requestId],
  )

  useEffect(() => {
    void loadPickOptions()
  }, [loadPickOptions])

  const doScan = useCallback(async () => {
    const barcode = scanBarcode.trim()
    if (!barcode) {
      setError('Введите штрихкод.')
      return
    }

    setBusy(true)
    setError(null)
    setScanMessage(null)

    try {
      const body: {
        barcode: string
        storage_location_id?: string | null
      } = {
        barcode,
        storage_location_id: activeLocationId ?? null,
      }

      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${requestId}/pick/scan`),
        {
          method: 'POST',
          headers: jsonHeaderMap,
          body: JSON.stringify(body),
        },
      )

      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }

      const scanRes = (await res.json()) as ScanResponse

      if (scanRes.kind === 'location') {
        setActiveLocationId(scanRes.storage_location_id ?? null)
        setActiveLocationCode(scanRes.location_code ?? null)
        setScanMessage(`Активная ячейка: ${scanRes.location_code}`)
      } else {
        setScanMessage(
          `Принято: ${scanRes.product_name} → ${scanRes.location_code ?? 'без ячейки'}`,
        )
      }

      setScanBarcode('')
      onChanged?.()
      await loadPickOptions({ silent: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    } finally {
      setBusy(false)
      scanInputRef.current?.focus()
    }
  }, [scanBarcode, activeLocationId, jsonHeaderMap, requestId, onChanged, loadPickOptions])

  const handleScanKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      void doScan()
    }
  }

  const addProduct = useCallback(
    async (productId: string, locationId: string | null, quantity: number) => {
      setBusy(true)
      setError(null)
      setScanMessage(null)

      try {
        const body: {
          product_id: string
          quantity: number
          storage_location_id?: string | null
        } = {
          product_id: productId,
          quantity,
          storage_location_id: locationId,
        }

        const res = await fetch(
          apiUrl(`/operations/marketplace-unload-requests/${requestId}/pick/add`),
          {
            method: 'POST',
            headers: jsonHeaderMap,
            body: JSON.stringify(body),
          },
        )

        if (!res.ok) {
          setError(await readApiErrorMessage(res))
          return
        }

        setScanMessage(`Добавлено: ${quantity} шт.`)
        onChanged?.()
        await loadPickOptions({ silent: true })
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Не удалось добавить товар.')
      } finally {
        setBusy(false)
      }
    },
    [jsonHeaderMap, requestId, onChanged, loadPickOptions],
  )

  const isDisabled = disabled || busy || loading

  return (
    <Box>
      {/* Чип активной ячейки */}
      {activeLocationCode ? (
        <Chip
          color="info"
          label={`Ячейка ${activeLocationCode}`}
          data-testid="ff-mp-pick-active-location"
          sx={{ mb: 1 }}
        />
      ) : (
        <Chip
          label="Ячейка не выбрана"
          data-testid="ff-mp-pick-active-location"
          sx={{ mb: 1 }}
        />
      )}

      {/* Ошибки */}
      {error && (
        <Alert severity="error" data-testid="ff-mp-pick-error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}

      {/* Поле сканирования */}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 2 }}>
        <TextField
          inputRef={scanInputRef}
          size="small"
          label="Штрихкод ячейки или товара"
          value={scanBarcode}
          onChange={(e) => setScanBarcode(e.target.value)}
          onKeyDown={handleScanKeyDown}
          disabled={isDisabled}
          fullWidth
          data-testid="ff-mp-pick-cell-scan-input"
        />
        <Button
          variant="contained"
          onClick={() => void doScan()}
          disabled={isDisabled}
          data-testid="ff-mp-pick-cell-scan"
        >
          Скан
        </Button>
      </Stack>

      {/* Сообщение о скане */}
      {scanMessage && (
        <Typography
          variant="caption"
          data-testid="ff-mp-pick-cell-scan-message"
          sx={{ display: 'block', mb: 1, color: 'success.main' }}
        >
          {scanMessage}
        </Typography>
      )}

      {/* Загрузка */}
      {loading ? (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">
            Загрузка…
          </Typography>
        </Box>
      ) : (
        /* Таблица товаров */
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" data-testid="ff-mp-pick-table">
            <TableHead>
              <TableRow sx={{ backgroundColor: 'action.hover' }}>
                <TableCell>Товар</TableCell>
                <TableCell align="right">План</TableCell>
                <TableCell align="right">Подобрано</TableCell>
                <TableCell align="right">Осталось</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pickOptions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography variant="body2" color="text.secondary">
                      Нет товаров в плане отгрузки
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                pickOptions.map((product) => {
                  const remaining = Math.max(0, product.planned_qty - product.picked_qty)
                  const hasLocations = product.locations.length > 0

                  return (
                    // <div> между <tbody> и <tr> — невалидная разметка: браузер выбрасывает
                    // строки из табличного контекста, и они теряют выравнивание по колонкам.
                    // Нужен фрагмент, а не Box.
                    <Fragment key={product.product_id}>
                      {/* Строка товара */}
                      <TableRow data-testid={`ff-mp-pick-row-${product.product_id}`}>
                        <TableCell>
                          <Typography variant="body2">
                            {product.product_name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            SKU: {product.sku_code}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">{product.planned_qty}</TableCell>
                        <TableCell align="right">{product.picked_qty}</TableCell>
                        <TableCell
                          align="right"
                          sx={remaining > 0 ? { color: 'warning.main' } : undefined}
                        >
                          {remaining}
                        </TableCell>
                      </TableRow>

                      {/* Строки с ячейками */}
                      {hasLocations ? (
                        product.locations.map((location) => {
                          const qtyKey = `${product.product_id}-${location.storage_location_id}`
                          const qtyStr = manualQtyByProductLocation[qtyKey] ?? '1'
                          const qtyNum = Number(qtyStr)
                          const qtyValid = Number.isInteger(qtyNum) && qtyNum >= 1 && qtyNum <= location.available

                          return (
                            <TableRow key={qtyKey}>
                              <TableCell sx={{ paddingLeft: 4 }}>
                                <Typography variant="body2">
                                  {location.location_code}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  Доступно: {location.available}
                                </Typography>
                              </TableCell>
                              <TableCell colSpan={2} />
                              <TableCell align="right">
                                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                                  <TextField
                                    size="small"
                                    type="number"
                                    value={qtyStr}
                                    onChange={(e) =>
                                      setManualQtyByProductLocation((prev) => ({
                                        ...prev,
                                        [qtyKey]: e.target.value,
                                      }))
                                    }
                                    slotProps={{
                                      htmlInput: {
                                        min: 1,
                                        max: location.available,
                                        'data-testid': `ff-mp-pick-qty-${product.product_id}-${location.storage_location_id}`,
                                      },
                                    }}
                                    sx={{ width: 60 }}
                                    disabled={isDisabled}
                                  />
                                  <Button
                                    size="small"
                                    variant="outlined"
                                    disabled={
                                      isDisabled || !qtyValid || location.available < 1
                                    }
                                    onClick={() =>
                                      void addProduct(
                                        product.product_id,
                                        location.storage_location_id,
                                        qtyNum,
                                      )
                                    }
                                    data-testid={`ff-mp-pick-add-${product.product_id}-${location.storage_location_id}`}
                                  >
                                    Добавить
                                  </Button>
                                </Stack>
                              </TableCell>
                            </TableRow>
                          )
                        })
                      ) : (
                        <TableRow>
                          <TableCell sx={{ paddingLeft: 4 }} colSpan={4}>
                            <Typography variant="caption" color="text.secondary">
                              Нет остатка по ячейкам
                            </Typography>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })
              )}
            </TableBody>
          </Table>
        </Box>
      )}
    </Box>
  )
}
