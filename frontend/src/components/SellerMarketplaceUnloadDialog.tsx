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
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../api'
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
  onClose,
  onRefreshList,
}: Props) {
  const [modalBusy, setModalBusy] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)
  const [detail, setDetail] = useState<UnloadDetail | null>(null)
  const [stockRows, setStockRows] = useState<StockRow[]>([])
  const [qtyByProduct, setQtyByProduct] = useState<Record<string, string>>({})
  const [wbWarehouses, setWbWarehouses] = useState<WbWarehouse[]>([])

  const isDraft = detail?.status === 'draft'
  const isSubmitted = detail?.status === 'submitted'
  const modalBusyEffective = modalBusy || parentBusy

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
      const qtyMap: Record<string, string> = {}
      for (const ln of j.lines) {
        qtyMap[ln.product_id] = String(ln.quantity)
      }
      setQtyByProduct(qtyMap)
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

  const linePayload = useMemo(() => {
    return stockRows
      .map((row) => ({
        product_id: row.product_id,
        quantity: Number.parseInt(qtyByProduct[row.product_id] ?? '0', 10) || 0,
      }))
      .filter((x) => x.quantity > 0)
  }, [qtyByProduct, stockRows])

  const saveLines = async (): Promise<boolean> => {
    if (!token || !requestId) {
      return false
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${requestId}/lines`), {
        method: 'PUT',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines: linePayload }),
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

  const plan = async () => {
    if (!token || !requestId) {
      return
    }
    const saved = await saveLines()
    if (!saved) {
      return
    }
    setModalBusy(true)
    try {
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

  return (
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
          </Stack>
        ) : null}

        {isDraft ? (
          <Table size="small" data-testid="seller-mp-product-stock-table" sx={{ mb: 2 }}>
            <TableHead>
              <TableRow>
                <TableCell>Артикул</TableCell>
                <TableCell>Товар</TableCell>
                <TableCell align="right">Доступно на ФФ</TableCell>
                <TableCell align="right">К отгрузке</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {stockRows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography variant="body2" color="text.secondary">
                      Нет товаров с остатком на складе ФФ.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                stockRows.map((row) => (
                  <TableRow key={row.product_id}>
                    <TableCell>{row.sku_code}</TableCell>
                    <TableCell>{row.product_name}</TableCell>
                    <TableCell align="right">{row.available}</TableCell>
                    <TableCell align="right">
                      <TextField
                        size="small"
                        type="number"
                        slotProps={{ htmlInput: { min: 0, max: row.available } }}
                        value={qtyByProduct[row.product_id] ?? ''}
                        onChange={(e) =>
                          setQtyByProduct((prev) => ({
                            ...prev,
                            [row.product_id]: e.target.value,
                          }))
                        }
                        data-testid={`seller-mp-qty-${row.product_id}`}
                        disabled={modalBusyEffective}
                        sx={{ width: 96 }}
                      />
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        ) : null}

        {detail && detail.lines.length > 0 ? (
          <Table size="small" data-testid="seller-mp-lines-table">
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
        ) : null}
      </DialogContent>
      <DialogActions>
        {isDraft ? (
          <>
            <Button
              variant="outlined"
              disabled={modalBusyEffective}
              onClick={() => void saveLines()}
              data-testid="seller-mp-save"
            >
              Сохранить
            </Button>
            <Button
              variant="contained"
              disabled={
                modalBusyEffective ||
                detail?.wb_mp_warehouse_id == null ||
                linePayload.length < 1
              }
              onClick={() => void plan()}
              data-testid="seller-mp-plan"
            >
              Запланировать
            </Button>
          </>
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
  )
}
