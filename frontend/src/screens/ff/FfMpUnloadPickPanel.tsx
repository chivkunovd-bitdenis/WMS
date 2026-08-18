import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ExpandMoreOutlined } from '@mui/icons-material'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
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
import { FfProductLineCells, FfProductTableHeadCells } from '../../components/FfProductLineCells'
import { storageLocationLabel } from '../../utils/inboundQueues'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import type { WbProductCatalogRow } from '../../types/wbProductCatalog'
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
  /** Каталог WB для фото/ШК/размера в строке товара — тот же, что уже грузит родительская страница. */
  catalogById: Map<string, WbProductCatalogRow>
}

export function FfMpUnloadPickPanel({
  token: _token,
  authHeaders,
  requestId,
  disabled,
  onChanged,
  catalogById,
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
  // Свёрнуто/раскрыто по товару. Дефолт выставляется один раз при первом появлении
  // товара в списке (см. эффект ниже) — раз доподобрано, держим свёрнутым, но не
  // схлопываем силой, если оператор сам раскрыл карточку во время работы.
  const [expandedByProductId, setExpandedByProductId] = useState<Record<string, boolean>>({})

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

  useEffect(() => {
    setExpandedByProductId((prev) => {
      let changed = false
      const next = { ...prev }
      for (const product of pickOptions) {
        if (!(product.product_id in next)) {
          const remaining = Math.max(0, product.planned_qty - product.picked_qty)
          next[product.product_id] = remaining > 0
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [pickOptions])

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
        setScanMessage(
          `Активная ячейка: ${storageLocationLabel(scanRes.location_code ?? '')}`,
        )
      } else {
        setScanMessage(
          `Принято: ${scanRes.product_name} → ${
            scanRes.location_code ? storageLocationLabel(scanRes.location_code) : 'без ячейки'
          }`,
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
  const activeLocationLabel = activeLocationCode ? storageLocationLabel(activeLocationCode) : null

  return (
    <Box>
      {/* Чип активной ячейки */}
      {activeLocationLabel ? (
        <Chip
          color="info"
          label={`Ячейка ${activeLocationLabel}`}
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

      {/* Строка состояния сканера — всегда на экране, как в сортировке (ff-sorting-scan-message) */}
      <Typography
        variant="caption"
        color="text.secondary"
        data-testid="ff-mp-pick-cell-scan-message"
        data-task-id="MPFBO-01"
        sx={{ display: 'block', mb: 1 }}
      >
        {scanMessage
          ? scanMessage
          : activeLocationLabel
            ? `Сканер активен — пикните ШК товара для ячейки ${activeLocationLabel}.`
            : 'Сканер активен — пикните ШК ячейки или товара.'}
      </Typography>

      {/* Загрузка */}
      {loading ? (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">
            Загрузка…
          </Typography>
        </Box>
      ) : pickOptions.length === 0 ? (
        <Alert severity="info" data-testid="ff-mp-pick-empty">
          Нет товаров в плане отгрузки.
        </Alert>
      ) : (
        /* Карточки товаров — тот же вид, что на раскладке при сортировке (FfInboundSortingPanel):
           полноценная строка товара (фото/артикул/ШК/наименование) сверху и под ней понятные
           строки ячеек «Ячейка / Доступно / Шт». При этом сам товар — сворачиваемая карточка
           (Accordion): свёрнутый вид уже даёт всё главное (фото/артикул/наименование/план/
           подобрано/осталось), а блок ячеек с кнопками «Добавить» открывается по клику и
           оформлен как явно вложенный (отступ + приглушённый фон + лёгкие заголовки), чтобы
           при десятке товаров границы между ними не терялись (просьба заказчика со стенда,
           17.08.2026 — раньше это была простыня из пар таблиц без явных границ). */
        <Stack spacing={1.5} data-testid="ff-mp-pick-list">
          {pickOptions.map((product) => {
            const remaining = Math.max(0, product.planned_qty - product.picked_qty)
            const hasLocations = product.locations.length > 0
            const displayMeta = productDisplayMetaFromCatalog(
              product.product_id,
              product,
              catalogById,
            )
            const done = remaining <= 0
            const isExpanded = expandedByProductId[product.product_id] ?? remaining > 0

            return (
              <Accordion
                key={product.product_id}
                variant="outlined"
                disableGutters
                expanded={isExpanded}
                onChange={(_e, nextExpanded) =>
                  setExpandedByProductId((prev) => ({
                    ...prev,
                    [product.product_id]: nextExpanded,
                  }))
                }
                sx={{
                  minWidth: 0,
                  '&:before': { display: 'none' },
                  ...(done
                    ? { opacity: 0.85, bgcolor: (theme) => alpha(theme.palette.success.main, 0.06) }
                    : null),
                }}
                data-testid="ff-mp-pick-product-card"
                data-product-id={product.product_id}
              >
                <AccordionSummary
                  expandIcon={<ExpandMoreOutlined />}
                  data-testid={`ff-mp-pick-toggle-${product.product_id}`}
                  sx={{
                    '& .MuiAccordionSummary-content': { minWidth: 0, overflow: 'hidden' },
                  }}
                >
                  <TableContainer sx={{ width: '100%', minWidth: 0 }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <FfProductTableHeadCells showPrint={false} />
                          <TableCell align="right">План</TableCell>
                          <TableCell align="right">Подобрано</TableCell>
                          <TableCell align="right">Осталось</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        <TableRow data-testid={`ff-mp-pick-row-${product.product_id}`}>
                          <FfProductLineCells
                            meta={displayMeta}
                            showPrint={false}
                            lineTestIdPrefix={`ff-mp-pick-product-${product.product_id}`}
                          />
                          <TableCell align="right" data-testid={`ff-mp-pick-plan-${product.product_id}`}>
                            {product.planned_qty}
                          </TableCell>
                          <TableCell align="right" data-testid={`ff-mp-pick-picked-${product.product_id}`}>
                            {product.picked_qty}
                          </TableCell>
                          <TableCell
                            align="right"
                            data-testid={`ff-mp-pick-remaining-${product.product_id}`}
                            sx={remaining > 0 ? { color: 'warning.main' } : undefined}
                          >
                            {remaining}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </AccordionSummary>
                <AccordionDetails
                  sx={{
                    pt: 0,
                    pl: { xs: 2, sm: 4 },
                    pr: 2,
                    pb: 2,
                  }}
                >
                  <Box
                    sx={{
                      borderLeft: '3px solid',
                      borderColor: 'divider',
                      borderRadius: 1,
                      bgcolor: (theme) => alpha(theme.palette.text.primary, 0.03),
                      p: 1,
                      minWidth: 0,
                    }}
                  >
                    {hasLocations ? (
                      <TableContainer sx={{ width: '100%', minWidth: 0 }}>
                        <Table size="small" data-testid="ff-mp-pick-cell-rows">
                          <TableHead>
                            <TableRow>
                              <TableCell
                                sx={{ minWidth: 180, fontSize: 12, fontWeight: 400, color: 'text.secondary', border: 'none' }}
                              >
                                Ячейка
                              </TableCell>
                              <TableCell
                                align="right"
                                sx={{ width: 100, fontSize: 12, fontWeight: 400, color: 'text.secondary', border: 'none' }}
                              >
                                Доступно
                              </TableCell>
                              <TableCell
                                align="right"
                                sx={{ width: 110, fontSize: 12, fontWeight: 400, color: 'text.secondary', border: 'none' }}
                              >
                                Шт
                              </TableCell>
                              <TableCell align="right" sx={{ width: 120, border: 'none' }} />
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {product.locations.map((location) => {
                              const qtyKey = `${product.product_id}-${location.storage_location_id}`
                              const qtyStr = manualQtyByProductLocation[qtyKey] ?? '1'
                              const qtyNum = Number(qtyStr)
                              const qtyValid =
                                Number.isInteger(qtyNum) && qtyNum >= 1 && qtyNum <= location.available

                              return (
                                <TableRow key={qtyKey} data-testid="ff-mp-pick-cell-row">
                                  <TableCell sx={{ border: 'none' }}>
                                    <Typography variant="body2" data-testid="ff-mp-pick-cell-code">
                                      {storageLocationLabel(location.location_code)}
                                    </Typography>
                                  </TableCell>
                                  <TableCell align="right" sx={{ border: 'none' }}>
                                    {location.available}
                                  </TableCell>
                                  <TableCell align="right" sx={{ border: 'none' }}>
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
                                      sx={{ width: 72, bgcolor: 'background.paper' }}
                                      disabled={isDisabled}
                                    />
                                  </TableCell>
                                  <TableCell align="right" sx={{ border: 'none' }}>
                                    <Button
                                      size="small"
                                      variant="outlined"
                                      disabled={isDisabled || !qtyValid || location.available < 1}
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
                                  </TableCell>
                                </TableRow>
                              )
                            })}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        data-testid={`ff-mp-pick-no-stock-${product.product_id}`}
                      >
                        Нет остатка по ячейкам
                      </Typography>
                    )}
                  </Box>
                </AccordionDetails>
              </Accordion>
            )
          })}
        </Stack>
      )}
    </Box>
  )
}
