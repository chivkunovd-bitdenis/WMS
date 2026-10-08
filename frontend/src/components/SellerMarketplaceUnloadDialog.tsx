import { ErrorBoundary } from './errors/ErrorBoundary'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import ExpandLessOutlined from '@mui/icons-material/ExpandLessOutlined'
import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined'
import { apiUrl } from '../api'
import { ProductPhotoThumb } from './ProductPhotoThumb'
import { ProductBarcodeCell } from './ProductBarcodeCell'
import {
  SellerWbProductPickerDialog,
  type SellerWbCatalogRow,
} from './SellerWbProductPickerDialog'
import { WmsDateField } from './WmsDateField'
import { insufficientAvailableMessage, readApiErrorMessage } from '../utils/readApiErrorMessage'
import { createLatestRequestSequence } from '../utils/latestRequestSequence'
import { downloadAuthorizedFile } from '../utils/downloadAuthorizedFile'
import { ActionGroup, SecondaryAction } from '../ui-kit'
import { FboPassDialog } from './FboPassDialog'

type StockRow = {
  product_id: string
  sku_code: string
  product_name: string
  available: number
}

type UnloadLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  // WMS-686: сервер отдаёт селлеру подбор и КИЗ отгрузки только для чтения.
  picked_qty?: number
  kiz_count?: number
  requires_honest_sign?: boolean
}

type MarkingItem = {
  marking_code_id: string
  cis_code: string
  product_id: string
  line_id: string
  intake_document_number?: string | null
}

type UnloadBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
}

type UnloadBox = {
  id: string
  internal_barcode: string | null
  lines: UnloadBoxLine[]
}

type UnloadDetail = {
  id: string
  warehouse_id: string
  warehouse_name: string
  status: string
  marketplace?: string | null
  wb_mp_warehouse_id: number | null
  planned_shipment_date: string | null
  lines: UnloadLine[]
  boxes?: UnloadBox[]
}

type WbWarehouse = { wb_warehouse_id: number; name: string }

type Props = {
  open: boolean
  requestId: string | null
  token: string
  authHeaders: (t: string) => Record<string, string>
  warehouseId: string | null
  busy: boolean
  catalogScopeKey?: string
  onClose: () => void
  onRefreshList: () => Promise<void>
}

// Выгрузка состава для WB имеет смысл, когда ФФ уже собирает короба: «Утверждено», «Сборка», «Отгружено».
const WB_EXPORT_STATUSES = ['confirmed', 'collecting', 'shipped']

function statusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Запланировано'
  if (status === 'confirmed') return 'Подтверждено'
  if (status === 'collecting') return 'На сборке'
  if (status === 'shipped') return 'Отгружено'
  if (status === 'cancelled') return 'Отменено'
  return status
}

export function SellerMarketplaceUnloadDialog(props: Props) {
  return (
    <ErrorBoundary component="SellerMarketplaceUnloadDialog" resetKey={String(props.open)}>
      <SellerMarketplaceUnloadDialogContent {...props} />
    </ErrorBoundary>
  )
}

function SellerMarketplaceUnloadDialogContent({
  open,
  requestId,
  token,
  authHeaders,
  warehouseId,
  busy: parentBusy,
  catalogScopeKey = '',
  onClose,
  onRefreshList,
}: Props) {
  const [modalBusy, setModalBusy] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)
  const [detail, setDetail] = useState<UnloadDetail | null>(null)
  const [stockRows, setStockRows] = useState<StockRow[]>([])
  const [catalog, setCatalog] = useState<SellerWbCatalogRow[] | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [wbWarehouses, setWbWarehouses] = useState<WbWarehouse[]>([])
  const [plannedDate, setPlannedDate] = useState<string | null>(null)
  const [passOpen, setPassOpen] = useState(false)
  const [kizOpenLineIds, setKizOpenLineIds] = useState<ReadonlySet<string>>(new Set())
  const [markingItems, setMarkingItems] = useState<MarkingItem[] | null>(null)
  const [markingError, setMarkingError] = useState<string | null>(null)
  const markingRequests = useRef(createLatestRequestSequence())
  const [wbExportBusy, setWbExportBusy] = useState(false)
  const [wbExportError, setWbExportError] = useState<string | null>(null)
  const [wbExportWarning, setWbExportWarning] = useState<string | null>(null)
  const wbExportRequests = useRef(createLatestRequestSequence())
  const detailRequests = useRef(createLatestRequestSequence())
  const stockRequests = useRef(createLatestRequestSequence())
  const activeRequestId = useRef<string | null>(null)
  activeRequestId.current = open ? requestId : null

  const isDraft = detail?.status === 'draft'
  const isSubmitted = detail?.status === 'submitted'
  const modalBusyEffective = modalBusy || parentBusy

  const stockByProductId = useMemo(() => {
    const m = new Map<string, StockRow>()
    for (const row of stockRows) {
      m.set(row.product_id, row)
    }
    return m
  }, [stockRows])

  const catalogById = useMemo(() => {
    const m = new Map<string, SellerWbCatalogRow>()
    if (catalog) {
      for (const r of catalog) {
        m.set(r.id, r)
      }
    }
    return m
  }, [catalog])

  const lineProductIds = useMemo(
    () => new Set(detail?.lines.map((l) => l.product_id) ?? []),
    [detail],
  )

  const loadDetail = useCallback(async () => {
    if (activeRequestId.current !== requestId) {
      return
    }
    const detailRequestId = detailRequests.current.next()
    const isCurrentDetail = () =>
      detailRequests.current.isLatest(detailRequestId) &&
      activeRequestId.current === requestId
    if (!token || !requestId) {
      setDetail(null)
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${requestId}`), {
        headers: authHeaders(token),
      })
      if (!isCurrentDetail()) {
        return
      }
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        if (isCurrentDetail()) {
          setModalError(message)
          setDetail(null)
        }
        return
      }
      const j = (await res.json()) as UnloadDetail
      if (!isCurrentDetail()) {
        return
      }
      setDetail(j)
      setPlannedDate(j.planned_shipment_date ?? null)
    } catch (e) {
      if (isCurrentDetail()) {
        setModalError(e instanceof Error ? e.message : 'Не удалось загрузить заявку.')
      }
    } finally {
      if (isCurrentDetail()) {
        setModalBusy(false)
      }
    }
  }, [authHeaders, requestId, token])

  const loadStock = useCallback(async () => {
    if (activeRequestId.current !== requestId) {
      return
    }
    const stockRequestId = stockRequests.current.next()
    const isCurrentStock = () =>
      stockRequests.current.isLatest(stockRequestId) &&
      activeRequestId.current === requestId
    if (!token || !warehouseId) {
      setStockRows([])
      return
    }
    try {
      const params = new URLSearchParams({ warehouse_id: warehouseId })
      if (requestId) {
        params.set('exclude_request_id', requestId)
      }
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/available-products?${params.toString()}`),
        { headers: authHeaders(token) },
      )
      if (!isCurrentStock()) {
        return
      }
      if (!res.ok) {
        setStockRows([])
        return
      }
      const rows = (await res.json()) as StockRow[]
      if (!isCurrentStock()) {
        return
      }
      setStockRows(rows)
    } catch {
      if (isCurrentStock()) {
        setStockRows([])
      }
    }
  }, [authHeaders, requestId, token, warehouseId])

  const loadWbWarehouses = useCallback(async () => {
    if (!token) {
      setWbWarehouses([])
      return
    }
    try {
      const res = await fetch(apiUrl('/operations/wb-mp-warehouses'), {
        headers: authHeaders(token),
      })
      if (!res.ok) {
        setWbWarehouses([])
        return
      }
      const rows = (await res.json()) as WbWarehouse[]
      setWbWarehouses(rows)
    } catch {
      setWbWarehouses([])
    }
  }, [authHeaders, token])

  useEffect(() => {
    if (!open) {
      detailRequests.current.invalidate()
      stockRequests.current.invalidate()
      return
    }
    void loadDetail()
    void loadStock()
    void loadWbWarehouses()
  }, [open, loadDetail, loadStock, loadWbWarehouses])

  useEffect(() => {
    setCatalog(null)
  }, [catalogScopeKey, token])

  // Закрытие окна или другая отгрузка: устаревший ответ выгрузки не сохраняется,
  // ошибка и предупреждение прежней отгрузки не переходят в новую.
  useEffect(() => {
    wbExportRequests.current.invalidate()
    markingRequests.current.invalidate()
    setWbExportBusy(false)
    setWbExportError(null)
    setWbExportWarning(null)
    setPassOpen(false)
    setKizOpenLineIds(new Set())
    setMarkingItems(null)
    setMarkingError(null)
  }, [open, requestId])

  // Коды отгрузки читаем при каждом раскрытии списка: ФФ мог привязать новые, пока окно открыто.
  const loadMarkingItems = async () => {
    if (!token || !requestId) {
      return
    }
    const markingRequestId = markingRequests.current.next()
    const isCurrentMarking = () => markingRequests.current.isLatest(markingRequestId)
    setMarkingError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${requestId}/marking-codes`),
        { headers: authHeaders(token) },
      )
      if (!isCurrentMarking()) {
        return
      }
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        if (isCurrentMarking()) {
          setMarkingError(message)
        }
        return
      }
      const body = (await res.json()) as { items?: MarkingItem[] }
      if (isCurrentMarking()) {
        setMarkingItems(body.items ?? [])
      }
    } catch (e) {
      if (isCurrentMarking()) {
        setMarkingError(e instanceof Error ? e.message : 'Не удалось загрузить КИЗ.')
      }
    }
  }

  const toggleKizList = (lineId: string) => {
    const opening = !kizOpenLineIds.has(lineId)
    setKizOpenLineIds((current) => {
      const next = new Set(current)
      if (next.has(lineId)) {
        next.delete(lineId)
      } else {
        next.add(lineId)
      }
      return next
    })
    if (opening) {
      void loadMarkingItems()
    }
  }

  const downloadWbExport = async () => {
    if (!token || !requestId || wbExportBusy) {
      return
    }
    const exportRequestId = wbExportRequests.current.next()
    const isCurrentExport = () => wbExportRequests.current.isLatest(exportRequestId)
    setWbExportBusy(true)
    setWbExportError(null)
    setWbExportWarning(null)
    try {
      const file = await downloadAuthorizedFile(
        `/operations/marketplace-unload-requests/${requestId}/wb-fbw-packaging.xlsx`,
        authHeaders(token),
        'wb-fbw-packaging.xlsx',
        isCurrentExport,
      )
      if (file?.warningCode === 'wb-shelf-life-date-required' && isCurrentExport()) {
        setWbExportWarning(
          'Перед загрузкой в WB укажите фактическую дату партии для товаров со сроком годности: WMS не хранит дату окончания партии.',
        )
      }
    } catch (e) {
      if (isCurrentExport()) {
        setWbExportError(e instanceof Error ? e.message : 'Не удалось скачать XLSX для WB.')
      }
    } finally {
      if (isCurrentExport()) {
        setWbExportBusy(false)
      }
    }
  }

  useEffect(() => {
    if (!token || !open) {
      return
    }
    if (catalog !== null) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(apiUrl('/products/wb-catalog'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          return
        }
        const rows = (await res.json()) as SellerWbCatalogRow[]
        if (!cancelled) {
          setCatalog(rows)
        }
      } catch {
        // photos optional until picker opens
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, catalog, catalogScopeKey, open, token])

  const openPicker = async () => {
    setModalError(null)
    if (catalog === null) {
      try {
        const res = await fetch(apiUrl('/products/wb-catalog'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          return
        }
        setCatalog((await res.json()) as SellerWbCatalogRow[])
      } catch (e) {
        setModalError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
        return
      }
    }
    setPickerOpen(true)
  }

  const pickerFilterRow = useCallback(
    (row: SellerWbCatalogRow) => {
      const available = stockByProductId.get(row.id)?.available ?? 0
      return available >= 1 || lineProductIds.has(row.id)
    },
    [lineProductIds, stockByProductId],
  )

  const pickerGetAvailable = useCallback(
    (productId: string) => stockByProductId.get(productId)?.available ?? 0,
    [stockByProductId],
  )

  const applyPicker = async (pickerQtyByProduct: Record<string, number>) => {
    if (!token || !requestId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      for (const [productId, rawQty] of Object.entries(pickerQtyByProduct)) {
        const qty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (qty <= 0 || lineProductIds.has(productId)) {
          continue
        }
        const stock = stockByProductId.get(productId)
        const available = stock?.available ?? 0
        if (qty > available) {
          const product = catalogById.get(productId)
          setModalError(
            insufficientAvailableMessage(
              {
                name: stock?.product_name ?? product?.name ?? null,
                sku: stock?.sku_code ?? product?.sku_code ?? null,
              },
              available,
              qty,
            ),
          )
          setModalBusy(false)
          return
        }
        const res = await fetch(
          apiUrl(`/operations/marketplace-unload-requests/${requestId}/lines`),
          {
            method: 'POST',
            headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_id: productId, quantity: qty }),
          },
        )
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          setModalBusy(false)
          return
        }
      }
      setPickerOpen(false)
      await loadDetail()
      await loadStock()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось добавить товары.')
    } finally {
      setModalBusy(false)
    }
  }

  const replaceAllLines = async (lines: { product_id: string; quantity: number }[]): Promise<boolean> => {
    if (!token || !requestId) {
      return false
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${requestId}/lines`), {
        method: 'PUT',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines }),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return false
      }
      await loadDetail()
      await loadStock()
      return true
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось сохранить состав.')
      return false
    } finally {
      setModalBusy(false)
    }
  }

  const patchLineQty = async (lineId: string, quantity: number) => {
    if (!detail) {
      return
    }
    const lines = detail.lines.map((ln) => ({
      product_id: ln.product_id,
      quantity: ln.id === lineId ? quantity : ln.quantity,
    }))
    await replaceAllLines(lines)
  }

  const deleteLine = async (lineId: string) => {
    if (!token || !requestId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${requestId}/lines/${lineId}`),
        { method: 'DELETE', headers: authHeaders(token) },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
      await loadStock()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось удалить строку.')
    } finally {
      setModalBusy(false)
    }
  }

  const setWbWarehouse = async (wbId: number) => {
    if (!token || !requestId || !isDraft) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${requestId}`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ wb_mp_warehouse_id: wbId }),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось выбрать склад МП.')
    } finally {
      setModalBusy(false)
    }
  }

  const patchPlannedDate = async (iso: string | null) => {
    if (!token || !requestId || !isDraft || !iso) {
      return
    }
    setPlannedDate(iso)
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${requestId}`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ planned_shipment_date: iso }),
      })
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        // loadDetail сбрасывает ошибку окна — показываем её после перечитывания.
        await loadDetail()
        setModalError(message)
        return
      }
      await loadDetail()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось сохранить дату отгрузки.')
    } finally {
      setModalBusy(false)
    }
  }

  const plan = async () => {
    if (!token || !requestId) {
      return
    }
    if (!plannedDate) {
      setModalError('Укажите дату отгрузки на маркетплейс.')
      return
    }
    if (!detail || detail.lines.length < 1) {
      setModalError('Добавьте хотя бы один товар.')
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const patchRes = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${requestId}`),
        {
          method: 'PATCH',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ planned_shipment_date: plannedDate }),
        },
      )
      if (!patchRes.ok) {
        setModalError(await readApiErrorMessage(patchRes))
        return
      }
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${requestId}/plan`), {
        method: 'POST',
        headers: authHeaders(token),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
      await onRefreshList()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось запланировать.')
    } finally {
      setModalBusy(false)
    }
  }

  const unplan = async () => {
    if (!token || !requestId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marketplace-unload-requests/${requestId}/unplan`),
        { method: 'POST', headers: authHeaders(token) },
      )
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
      await loadStock()
      await onRefreshList()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось вернуть в черновик.')
    } finally {
      setModalBusy(false)
    }
  }

  const draftLinesTable = isDraft && detail ? (
    <>
      <Stack direction="row" spacing={1} sx={{ mb: 1.5, justifyContent: 'flex-end' }}>
        <Button
          variant="outlined"
          disabled={modalBusyEffective}
          onClick={() => void openPicker()}
          data-testid="seller-mp-add-products"
        >
          Добавить товары
        </Button>
      </Stack>
      <TableContainer sx={{ width: '100%', overflowX: 'hidden', mb: 2 }}>
        <Table
          size="small"
          data-testid="seller-mp-lines-table"
          sx={{
            tableLayout: 'fixed',
            width: '100%',
            '& th': { py: 1.25 },
            '& td': { py: 1.25 },
          }}
        >
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: 56 }}>Фото</TableCell>
              <TableCell sx={{ width: 190, pl: 2 }}>Артикул</TableCell>
              <TableCell sx={{ width: 220 }}>ШК</TableCell>
              <TableCell sx={{ width: 140 }}>Артикул продавца</TableCell>
              <TableCell sx={{ width: 120, pr: 2 }}>Артикул WB</TableCell>
              <TableCell sx={{ pl: 2 }}>Наименование</TableCell>
              <TableCell align="right" sx={{ width: 110 }}>
                Доступно
              </TableCell>
              <TableCell align="right" sx={{ width: 120 }}>
                К отгрузке
              </TableCell>
              <TableCell sx={{ width: 92 }} />
            </TableRow>
          </TableHead>
          <TableBody>
            {detail.lines.map((ln) => {
              const cat = catalogById.get(ln.product_id)
              const img = cat?.wb_primary_image_url ?? undefined
              const barcode =
                cat?.wb_primary_barcode ??
                (cat?.wb_barcodes.length ? cat.wb_barcodes[0] ?? null : null)
              const available = stockByProductId.get(ln.product_id)?.available ?? 0
              return (
                <TableRow
                  key={ln.id}
                  hover
                  data-testid="seller-mp-line-row"
                  sx={{
                    '& td': { px: 1.25 },
                    '& td:first-of-type': { pl: 1 },
                    '& td:last-of-type': { pr: 1 },
                  }}
                >
                  <TableCell>
                    <ProductPhotoThumb src={img} />
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap', pl: 2 }} title={ln.sku_code}>
                    {ln.sku_code}
                  </TableCell>
                  <TableCell sx={{ maxWidth: 220 }}>
                    <ProductBarcodeCell
                      barcode={barcode}
                      wb_size={cat?.wb_size}
                      wb_composition={cat?.wb_composition}
                    />
                  </TableCell>
                  <TableCell
                    sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                    title={cat?.wb_vendor_code ?? '—'}
                  >
                    {cat?.wb_vendor_code ?? '—'}
                  </TableCell>
                  <TableCell sx={{ pr: 2 }}>{cat?.wb_nm_id ?? '—'}</TableCell>
                  <TableCell sx={{ pl: 2, whiteSpace: 'normal', wordBreak: 'break-word' }}>
                    <Typography variant="body2" sx={{ lineHeight: 1.25 }}>
                      {ln.product_name}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{available}</TableCell>
                  <TableCell align="right" sx={{ minWidth: 120 }}>
                    <TextField
                      type="number"
                      size="small"
                      disabled={modalBusyEffective}
                      defaultValue={ln.quantity}
                      key={`${ln.id}-${ln.quantity}`}
                      onBlur={(e) => {
                        const v = Number(e.target.value)
                        if (!Number.isFinite(v) || v < 1) {
                          return
                        }
                        if (v > available) {
                          setModalError(
                            insufficientAvailableMessage(
                              { name: ln.product_name, sku: ln.sku_code },
                              available,
                              v,
                            ),
                          )
                          return
                        }
                        if (v !== ln.quantity) {
                          void patchLineQty(ln.id, v)
                        }
                      }}
                      slotProps={{
                        htmlInput: {
                          min: 1,
                          max: available,
                          'data-testid': `seller-mp-qty-${ln.product_id}`,
                        },
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      size="small"
                      color="error"
                      disabled={modalBusyEffective}
                      onClick={() => void deleteLine(ln.id)}
                      data-testid="seller-mp-line-delete"
                    >
                      Удалить
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
            {detail.lines.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9}>
                  <Typography variant="body2" color="text.secondary">
                    Добавьте товары кнопкой «Добавить товары».
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  ) : null

  // Сколько штук товара лежит в коробах отгрузки — считается из состава коробов, отдельного счётчика нет.
  const inBoxesByProduct = new Map<string, number>()
  for (const box of detail?.boxes ?? []) {
    for (const ln of box.lines) {
      inBoxesByProduct.set(ln.product_id, (inBoxesByProduct.get(ln.product_id) ?? 0) + ln.quantity)
    }
  }

  const readOnlyLinesTable =
    detail && !isDraft && detail.lines.length > 0 ? (
      <TableContainer>
        <Table size="small" data-testid="seller-mp-lines-table-readonly">
          <TableHead>
            <TableRow sx={{ '& th': { whiteSpace: 'nowrap' } }}>
              <TableCell>Артикул</TableCell>
              <TableCell>Товар</TableCell>
              <TableCell align="right">Кол-во</TableCell>
              <TableCell align="right">Подобрано</TableCell>
              <TableCell align="right">В коробах</TableCell>
              <TableCell align="right">КИЗ</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {detail.lines.map((ln) => {
              const kizOpen = kizOpenLineIds.has(ln.id)
              const lineCodes = (markingItems ?? []).filter((item) => item.line_id === ln.id)
              return (
                <Fragment key={ln.id}>
                  <TableRow data-testid={`seller-mp-line-readonly-${ln.id}`}>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{ln.sku_code}</TableCell>
                    <TableCell sx={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>
                      {ln.product_name}
                    </TableCell>
                    <TableCell align="right">{ln.quantity}</TableCell>
                    <TableCell align="right" data-testid={`seller-mp-line-picked-${ln.id}`}>
                      {ln.picked_qty ?? 0}
                    </TableCell>
                    <TableCell align="right" data-testid={`seller-mp-line-in-boxes-${ln.id}`}>
                      {inBoxesByProduct.get(ln.product_id) ?? 0}
                    </TableCell>
                    <TableCell align="right">
                      {ln.requires_honest_sign ? (
                        <Button
                          size="small"
                          color="inherit"
                          onClick={() => toggleKizList(ln.id)}
                          endIcon={kizOpen ? <ExpandLessOutlined /> : <ExpandMoreOutlined />}
                          aria-expanded={kizOpen}
                          aria-label={`КИЗ: ${ln.kiz_count ?? 0}. ${kizOpen ? 'Скрыть список' : 'Показать список'}`}
                          sx={{ fontWeight: 700, fontSize: '1.05rem', minWidth: 0 }}
                          data-testid={`seller-mp-kiz-toggle-${ln.id}`}
                        >
                          {ln.kiz_count ?? 0}
                        </Button>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                  </TableRow>
                  {ln.requires_honest_sign && kizOpen ? (
                    <TableRow data-testid={`seller-mp-kiz-list-${ln.id}`}>
                      <TableCell colSpan={6} sx={{ bgcolor: 'action.hover', py: 1 }}>
                        {markingError ? (
                          <Typography variant="body2" color="error">
                            {markingError}
                          </Typography>
                        ) : markingItems === null ? (
                          <Typography variant="body2" color="text.secondary">
                            Загрузка…
                          </Typography>
                        ) : lineCodes.length === 0 ? (
                          <Typography variant="body2" color="text.secondary">
                            КИЗ пока не привязаны.
                          </Typography>
                        ) : (
                          <Stack spacing={0.5}>
                            {lineCodes.map((item) => (
                              <Typography
                                key={item.marking_code_id}
                                variant="body2"
                                sx={{ wordBreak: 'break-all' }}
                                data-testid="seller-mp-kiz-code"
                              >
                                <Box
                                  component="span"
                                  sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}
                                >
                                  {item.cis_code}
                                </Box>
                                {item.intake_document_number
                                  ? ` · приёмка №${item.intake_document_number}`
                                  : ''}
                              </Typography>
                            ))}
                          </Stack>
                        )}
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              )
            })}
          </TableBody>
        </Table>
      </TableContainer>
    ) : null

  // Короба селлер видит только на чтение: состав и внутренний ШК, без действий над ними.
  // Порядок и отбор те же, что в окне ФФ: сначала короба с товаром, затем пустые со ШК.
  const visibleBoxes = (detail?.boxes ?? []).filter(
    (box) => box.lines.length > 0 || Boolean(box.internal_barcode?.trim()),
  )
  const orderedBoxes = [
    ...visibleBoxes.filter((box) => box.lines.length > 0),
    ...visibleBoxes.filter((box) => box.lines.length === 0),
  ]

  const readOnlyBoxes =
    orderedBoxes.length > 0 ? (
      <Box sx={{ mt: 2 }} data-testid="seller-mp-boxes">
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
          Короба
        </Typography>
        <Stack spacing={1.5}>
          {orderedBoxes.map((box, index) => {
            const barcode = box.internal_barcode?.trim()
            return (
              <Paper
                key={box.id}
                variant="outlined"
                sx={{ borderRadius: 1, overflow: 'hidden' }}
                data-testid={`seller-mp-box-${box.id}`}
              >
                <Box sx={{ px: 1.25, py: 1, bgcolor: 'action.hover' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.25 }}>
                    Короб {index + 1}
                  </Typography>
                  {barcode ? (
                    <Typography
                      variant="caption"
                      color="text.disabled"
                      sx={{
                        display: 'block',
                        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                      }}
                      data-testid={`seller-mp-box-barcode-${box.id}`}
                    >
                      {barcode}
                    </Typography>
                  ) : null}
                </Box>
                {box.lines.length > 0 ? (
                  <Table size="small" data-testid={`seller-mp-box-lines-${box.id}`}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Артикул</TableCell>
                        <TableCell>Товар</TableCell>
                        <TableCell align="right">В коробе</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {box.lines.map((ln) => (
                        <TableRow key={ln.id}>
                          <TableCell>{ln.sku_code}</TableCell>
                          <TableCell sx={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>
                            {ln.product_name}
                          </TableCell>
                          <TableCell align="right">{ln.quantity}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : null}
              </Paper>
            )
          })}
        </Stack>
      </Box>
    ) : null

  return (
    <>
      <Dialog open={open} onClose={onClose} fullScreen data-testid="seller-mp-unload-dialog">
        <DialogTitle>Отгрузка на маркетплейс</DialogTitle>
        <DialogContent dividers data-testid="seller-mp-plan-only">
          {modalError ? (
            <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-mp-unload-error">
              {modalError}
            </Alert>
          ) : null}
          {detail ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Склад ФФ: {detail.warehouse_name} · {statusRu(detail.status)}
              {detail.planned_shipment_date ? ` · отгрузка ${detail.planned_shipment_date}` : ''}
            </Typography>
          ) : null}
          {detail && !isDraft ? (
            <Box sx={{ mb: 2 }} data-testid="seller-mp-doc-actions">
              <ActionGroup>
                {detail.marketplace === 'wb' && WB_EXPORT_STATUSES.includes(detail.status) ? (
                  <SecondaryAction
                    onClick={() => void downloadWbExport()}
                    disabledReason={wbExportBusy ? 'Файл формируется' : undefined}
                    data-testid="seller-mp-wb-fbw-export"
                  >
                    Скачать XLSX для WB
                  </SecondaryAction>
                ) : null}
                <SecondaryAction onClick={() => setPassOpen(true)} data-testid="seller-mp-pass-open">
                  Пропуск
                </SecondaryAction>
              </ActionGroup>
              {wbExportError ? (
                <Alert severity="error" sx={{ mt: 1.5 }} data-testid="seller-mp-wb-fbw-export-error">
                  {wbExportError}
                </Alert>
              ) : null}
              {wbExportWarning ? (
                <Alert severity="warning" sx={{ mt: 1.5 }} data-testid="seller-mp-wb-fbw-export-warning">
                  {wbExportWarning}
                </Alert>
              ) : null}
            </Box>
          ) : null}
          {isSubmitted ? (
            <Alert severity="info" sx={{ mb: 2 }} data-testid="seller-mp-ff-handoff-hint">
              Дальше заявку обрабатывает фулфилмент.
            </Alert>
          ) : null}
          {isDraft ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} sx={{ mb: 2 }}>
              <FormControl size="small" sx={{ minWidth: 280 }}>
                <InputLabel id="seller-mp-wb-warehouse">Склад WB (маркетплейс)</InputLabel>
                <Select
                  labelId="seller-mp-wb-warehouse"
                  label="Склад WB (маркетплейс)"
                  value={detail?.wb_mp_warehouse_id ?? ''}
                  onChange={(e) => {
                    const v = Number(e.target.value)
                    if (Number.isInteger(v) && v > 0) {
                      void setWbWarehouse(v)
                    }
                  }}
                  data-testid="seller-mp-wb-warehouse-select"
                  disabled={modalBusyEffective}
                >
                  <MenuItem value="">
                    <em>Не выбран</em>
                  </MenuItem>
                  {wbWarehouses.map((w) => (
                    <MenuItem key={w.wb_warehouse_id} value={w.wb_warehouse_id}>
                      {w.name} ({w.wb_warehouse_id})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <WmsDateField
                label="Дата отгрузки на МП"
                value={plannedDate}
                onChange={(iso) => void patchPlannedDate(iso)}
                disabled={modalBusyEffective}
                required
                testId="seller-mp-planned-date"
                slotProps={{ textField: { fullWidth: false, sx: { minWidth: 220 } } }}
              />
            </Stack>
          ) : null}

          {draftLinesTable}
          {readOnlyLinesTable}
          {readOnlyBoxes}
        </DialogContent>
        <DialogActions>
          {isDraft ? (
            <Button
              variant="contained"
              disabled={
                modalBusyEffective ||
                detail?.wb_mp_warehouse_id == null ||
                !plannedDate ||
                (detail?.lines.length ?? 0) < 1
              }
              onClick={() => void plan()}
              data-testid="seller-mp-plan"
            >
              Запланировать
            </Button>
          ) : null}
          {isSubmitted ? (
            <Button
              variant="outlined"
              disabled={modalBusyEffective}
              onClick={() => void unplan()}
              data-testid="seller-mp-unplan"
            >
              Вернуть в черновик
            </Button>
          ) : null}
          <Button onClick={onClose} data-testid="seller-mp-close">
            Закрыть
          </Button>
        </DialogActions>
      </Dialog>

      <FboPassDialog
        open={open && passOpen}
        token={token}
        authHeaders={authHeaders}
        requestId={requestId}
        mode="seller"
        marketplace={detail?.marketplace ?? null}
        onClose={() => setPassOpen(false)}
      />

      <SellerWbProductPickerDialog
        open={pickerOpen}
        busy={modalBusyEffective}
        catalog={catalog}
        disabledProductIds={lineProductIds}
        testIdPrefix="seller-mp-picker"
        qtyColumnLabel="К отгрузке"
        showAvailableColumn
        getAvailable={pickerGetAvailable}
        filterRow={pickerFilterRow}
        emptyMessage="Нет доступного остатка по этому селлеру"
        onClose={() => setPickerOpen(false)}
        onApply={applyPicker}
      />
    </>
  )
}
