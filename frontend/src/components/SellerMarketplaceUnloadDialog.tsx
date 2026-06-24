import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
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
import { apiUrl } from '../api'
import { ProductPhotoThumb } from './ProductPhotoThumb'
import { ProductBarcodeCell } from './ProductBarcodeCell'
import {
  SellerWbProductPickerDialog,
  type SellerWbCatalogRow,
} from './SellerWbProductPickerDialog'
import { WmsDateField } from './WmsDateField'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'

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
}

type UnloadDetail = {
  id: string
  warehouse_id: string
  warehouse_name: string
  status: string
  wb_mp_warehouse_id: number | null
  planned_shipment_date: string | null
  lines: UnloadLine[]
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

function statusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Запланировано'
  if (status === 'confirmed') return 'Подтверждено'
  if (status === 'shipped') return 'Отгружено'
  return status
}

export function SellerMarketplaceUnloadDialog({
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
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        setDetail(null)
        return
      }
      const j = (await res.json()) as UnloadDetail
      setDetail(j)
      setPlannedDate(j.planned_shipment_date ?? null)
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось загрузить заявку.')
    } finally {
      setModalBusy(false)
    }
  }, [authHeaders, requestId, token])

  const loadStock = useCallback(async () => {
    if (!token || !warehouseId) {
      setStockRows([])
      return
    }
    try {
      const res = await fetch(
        apiUrl(
          `/operations/inventory-balances/summary?warehouse_id=${encodeURIComponent(warehouseId)}`,
        ),
        { headers: authHeaders(token) },
      )
      if (!res.ok) {
        setStockRows([])
        return
      }
      const rows = (await res.json()) as StockRow[]
      setStockRows(rows)
    } catch {
      setStockRows([])
    }
  }, [authHeaders, token, warehouseId])

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
      return
    }
    void loadDetail()
    void loadStock()
    void loadWbWarehouses()
  }, [open, loadDetail, loadStock, loadWbWarehouses])

  useEffect(() => {
    setCatalog(null)
  }, [catalogScopeKey, token])

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
        const available = stockByProductId.get(productId)?.available ?? 0
        if (qty > available) {
          setModalError(`Недостаточно остатка: доступно ${available}.`)
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
        setModalError(await readApiErrorMessage(res))
        await loadDetail()
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
                          setModalError(`Недостаточно остатка: доступно ${available}.`)
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

  const readOnlyLinesTable =
    detail && !isDraft && detail.lines.length > 0 ? (
      <Table size="small" data-testid="seller-mp-lines-table-readonly">
        <TableHead>
          <TableRow>
            <TableCell>Артикул</TableCell>
            <TableCell>Товар</TableCell>
            <TableCell align="right">Кол-во</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {detail.lines.map((ln) => (
            <TableRow key={ln.id}>
              <TableCell>{ln.sku_code}</TableCell>
              <TableCell>{ln.product_name}</TableCell>
              <TableCell align="right">{ln.quantity}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    ) : null

  return (
    <>
      <Dialog open={open} onClose={onClose} fullScreen data-testid="seller-mp-unload-dialog">
        <DialogTitle>Отгрузка на маркетплейс</DialogTitle>
        <DialogContent dividers>
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
        emptyMessage="Нет товаров с остатком на складе ФФ."
        onClose={() => setPickerOpen(false)}
        onApply={applyPicker}
      />
    </>
  )
}
