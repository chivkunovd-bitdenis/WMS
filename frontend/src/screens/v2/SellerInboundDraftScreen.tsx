import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
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
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type WbCatalogRow = {
  id: string
  name: string
  sku_code: string
  wb_nm_id: number | null
  wb_vendor_code: string | null
  wb_subject_name: string | null
  wb_primary_image_url: string | null
  wb_barcodes: string[]
  wb_primary_barcode: string | null
}

type InboundLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  expected_qty: number
  actual_qty: number | null
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type InboundDetail = {
  id: string
  warehouse_id: string
  status: string
  planned_delivery_date: string | null
  has_discrepancy: boolean
  lines: InboundLine[]
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  warehouseId: string | null
  onRefreshInboundList: () => void | Promise<void>
}

function statusRu(status: string): string {
  if (status === 'draft') {
    return 'Черновик'
  }
  if (status === 'submitted') {
    return 'Передано на склад'
  }
  if (status === 'primary_accepted') {
    return 'Принято на складе'
  }
  if (status === 'verifying') {
    return 'Проверка на складе'
  }
  if (status === 'verified') {
    return 'Проверено на складе'
  }
  if (status === 'posted') {
    return 'Оприходовано'
  }
  return status
}

export function SellerInboundDraftScreen({
  token,
  authHeaders,
  warehouseId,
  onRefreshInboundList,
}: Props) {
  const navigate = useNavigate()
  const params = useParams()
  const routeRequestId = (params as { requestId?: string }).requestId ?? null
  const createOnceRef = useRef<Promise<string> | null>(null)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [detail, setDetail] = useState<InboundDetail | null>(null)
  const [catalog, setCatalog] = useState<WbCatalogRow[] | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerCategory, setPickerCategory] = useState<string>('__all__')
  const [pickerQtyByProduct, setPickerQtyByProduct] = useState<Record<string, number>>({})
  const [plannedDateDraft, setPlannedDateDraft] = useState<string>('')

  const loadDetail = useCallback(
    async (rid: string) => {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${rid}`), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      setDetail((await res.json()) as InboundDetail)
    },
    [authHeaders, token],
  )

  useEffect(() => {
    if (!token || !warehouseId) {
      return
    }
    if (routeRequestId) {
      setRequestId(routeRequestId)
      void loadDetail(routeRequestId)
      return
    }
    if (!createOnceRef.current) {
      createOnceRef.current = (async () => {
        const today = new Date().toISOString().slice(0, 10)
        const res = await fetch(apiUrl('/operations/inbound-intake-requests'), {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            warehouse_id: warehouseId,
            planned_delivery_date: today,
          }),
        })
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res))
        }
        const j = (await res.json()) as { id: string }
        return j.id
      })()
    }
    let cancelled = false
    void (async () => {
      try {
        const id = await createOnceRef.current
        if (cancelled || !id) {
          return
        }
        setRequestId(id)
        await loadDetail(id)
      } catch (e) {
        if (!cancelled) {
          setLocalError(e instanceof Error ? e.message : 'Не удалось создать заявку.')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, loadDetail, routeRequestId, token, warehouseId])

  useEffect(() => {
    setPlannedDateDraft(detail?.planned_delivery_date ?? '')
  }, [detail?.planned_delivery_date])

  const catalogById = useMemo(() => {
    const m = new Map<string, WbCatalogRow>()
    if (catalog) {
      for (const r of catalog) {
        m.set(r.id, r)
      }
    }
    return m
  }, [catalog])

  const lineProductIds = useMemo(() => new Set(detail?.lines.map((l) => l.product_id) ?? []), [detail])

  useEffect(() => {
    if (!token) {
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
        const rows = (await res.json()) as WbCatalogRow[]
        if (!cancelled) {
          setCatalog(rows)
        }
      } catch {
        // silent: photos are optional; picker will show explicit error if user opens it
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, catalog, token])

  const openPicker = async () => {
    setLocalError(null)
    if (catalog === null) {
      try {
        const res = await fetch(apiUrl('/products/wb-catalog'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          setLocalError(await readApiErrorMessage(res))
          return
        }
        setCatalog((await res.json()) as WbCatalogRow[])
      } catch (e) {
        setLocalError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
        return
      }
    }
    setPickerOpen(true)
  }

  const categories = useMemo(() => {
    if (!catalog) {
      return []
    }
    const s = new Set<string>()
    for (const r of catalog) {
      const c = r.wb_subject_name?.trim()
      if (c) {
        s.add(c)
      }
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [catalog])

  const filteredPickerRows = useMemo(() => {
    if (!catalog) {
      return []
    }
    const q = pickerSearch.trim().toLowerCase()
    return catalog.filter((r) => {
      if (pickerCategory !== '__all__') {
        const sub = (r.wb_subject_name ?? '').trim()
        if (sub !== pickerCategory) {
          return false
        }
      }
      if (!q) {
        return true
      }
      const nm = r.wb_nm_id != null ? String(r.wb_nm_id) : ''
      const barcodes = r.wb_barcodes.join(' ').toLowerCase()
      const hay = `${r.sku_code} ${r.wb_vendor_code ?? ''} ${r.name} ${nm} ${barcodes}`.toLowerCase()
      return hay.includes(q)
    })
  }, [catalog, pickerCategory, pickerSearch])

  const setPickerQty = (productId: string, qty: number) => {
    setPickerQtyByProduct((prev) => ({ ...prev, [productId]: qty }))
  }

  const applyPicker = async () => {
    if (!requestId || !detail) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const lineByProduct = new Map(detail.lines.map((ln) => [ln.product_id, ln]))
      for (const [productId, rawQty] of Object.entries(pickerQtyByProduct)) {
        const addQty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (addQty <= 0) {
          continue
        }
        const existing = lineByProduct.get(productId)
        if (existing) {
          const next = existing.expected_qty + addQty
          const res = await fetch(
            apiUrl(
              `/operations/inbound-intake-requests/${requestId}/lines/${existing.id}/expected`,
            ),
            {
              method: 'PATCH',
              headers: {
                ...authHeaders(token),
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ expected_qty: next }),
            },
          )
          if (!res.ok) {
            setLocalError(await readApiErrorMessage(res))
            setBusy(false)
            return
          }
        } else {
          const res = await fetch(
            apiUrl(`/operations/inbound-intake-requests/${requestId}/lines`),
            {
              method: 'POST',
              headers: {
                ...authHeaders(token),
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ product_id: productId, expected_qty: addQty }),
            },
          )
          if (!res.ok) {
            setLocalError(await readApiErrorMessage(res))
            setBusy(false)
            return
          }
        }
      }
      setPickerQtyByProduct({})
      setPickerOpen(false)
      await loadDetail(requestId)
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось добавить товары.')
    } finally {
      setBusy(false)
    }
  }

  const patchPlannedDate = async (isoDate: string) => {
    if (!requestId) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ planned_delivery_date: isoDate }),
      })
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      setDetail((await res.json()) as InboundDetail)
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось сохранить дату.')
    } finally {
      setBusy(false)
    }
  }

  const patchLineQty = async (lineId: string, expectedQty: number) => {
    if (!requestId) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/lines/${lineId}/expected`),
        {
          method: 'PATCH',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ expected_qty: expectedQty }),
        },
      )
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail(requestId)
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось сохранить количество.')
    } finally {
      setBusy(false)
    }
  }

  const deleteLine = async (lineId: string) => {
    if (!requestId) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/lines/${lineId}`),
        {
          method: 'DELETE',
          headers: { ...authHeaders(token) },
        },
      )
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      await loadDetail(requestId)
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось удалить строку.')
    } finally {
      setBusy(false)
    }
  }

  const submitToWarehouse = async () => {
    if (!requestId) {
      return
    }
    setBusy(true)
    setLocalError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/submit`),
        {
          method: 'POST',
          headers: { ...authHeaders(token) },
        },
      )
      if (!res.ok) {
        setLocalError(await readApiErrorMessage(res))
        return
      }
      await onRefreshInboundList()
      navigate('/documents')
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : 'Не удалось передать на склад.')
    } finally {
      setBusy(false)
    }
  }

  if (!warehouseId) {
    return (
      <Alert severity="warning" data-testid="seller-inbound-no-warehouse">
        Нет доступного склада для создания заявки. Обратитесь к фулфилменту.
      </Alert>
    )
  }

  const onSaveAndClose = async () => {
    setLocalError(null)
    try {
      await onRefreshInboundList()
    } finally {
      navigate('/documents')
    }
  }

  const draftLocked = detail != null && detail.status !== 'draft'

  return (
    <Box data-testid="seller-inbound-draft-root">
      <Typography variant="h5" gutterBottom>
        Новая заявка на поставку
      </Typography>
      {localError ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-inbound-draft-error">
          {localError}
        </Alert>
      ) : null}

      {!requestId || !detail ? (
        <Stack sx={{ py: 4, alignItems: 'center' }}>
          <CircularProgress data-testid="seller-inbound-draft-loading" />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Создаём черновик…
          </Typography>
        </Stack>
      ) : (
        <Paper
          variant="outlined"
          sx={{ p: 2, minHeight: '38vh' }}
          data-testid="seller-inbound-draft-form"
        >
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={2}
            sx={{ mb: 2, alignItems: { md: 'center' } }}
          >
            <TextField
              label="Дата поставки (план)"
              type="date"
              size="small"
              disabled={draftLocked || busy}
              value={plannedDateDraft}
              onChange={(e) => setPlannedDateDraft(e.target.value)}
              onBlur={() => {
                if (!detail) return
                if ((plannedDateDraft || '') !== (detail.planned_delivery_date ?? '')) {
                  void patchPlannedDate(plannedDateDraft)
                }
              }}
              slotProps={{
                inputLabel: { shrink: true },
                htmlInput: { 'data-testid': 'seller-inbound-planned-date' },
              }}
            />
            <Chip
              label={statusRu(detail.status)}
              color={detail.status === 'draft' ? 'default' : 'primary'}
              data-testid="seller-inbound-status-chip"
            />
            <Box sx={{ flexGrow: 1 }} />
            <Button
              variant="outlined"
              disabled={draftLocked || busy}
              onClick={() => void openPicker()}
              data-testid="seller-inbound-add-products"
            >
              Добавить товары
            </Button>
            <Button
              variant="outlined"
              disabled={busy}
              onClick={() => void onSaveAndClose()}
              data-testid="seller-inbound-save-draft"
            >
              Сохранить
            </Button>
            <Button
              variant="contained"
              color="secondary"
              disabled={draftLocked || busy || detail.lines.length === 0}
              onClick={() => void submitToWarehouse()}
              data-testid="seller-inbound-submit-warehouse"
            >
              Передать на склад
            </Button>
          </Stack>

          <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
            <Table
              size="small"
              data-testid="seller-inbound-lines-table"
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
                  <TableCell align="right" sx={{ width: 120 }}>
                    Кол-во
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
                    (cat?.wb_barcodes.length ? cat.wb_barcodes.join(', ') : '—')
                  return (
                    <TableRow
                      key={ln.id}
                      hover
                      data-testid="seller-inbound-line-row"
                      sx={{
                        '& td': {
                          px: 1.25,
                        },
                        '& td:first-of-type': { pl: 1 },
                        '& td:last-of-type': { pr: 1 },
                      }}
                    >
                      <TableCell>
                        <Avatar
                          variant="rounded"
                          src={img}
                          alt=""
                          sx={{ width: 44, height: 44 }}
                          slotProps={{ img: { loading: 'lazy' } }}
                        />
                      </TableCell>
                      <TableCell
                        sx={{
                          whiteSpace: 'nowrap',
                          pl: 2,
                        }}
                        title={ln.sku_code}
                      >
                        {ln.sku_code}
                      </TableCell>
                      <TableCell
                        sx={{
                          whiteSpace: 'nowrap',
                        }}
                        title={barcode}
                      >
                        {barcode}
                      </TableCell>
                      <TableCell
                        sx={{
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
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
                      <TableCell align="right" sx={{ minWidth: 120 }}>
                        <TextField
                          type="number"
                          size="small"
                          disabled={draftLocked || busy}
                          defaultValue={ln.expected_qty}
                          key={`${ln.id}-${ln.expected_qty}`}
                          onBlur={(e) => {
                            const v = Number(e.target.value)
                            if (!Number.isFinite(v) || v < 1) {
                              return
                            }
                            if (v !== ln.expected_qty) {
                              void patchLineQty(ln.id, v)
                            }
                          }}
                          slotProps={{ htmlInput: { min: 1, 'data-testid': 'seller-inbound-line-qty' } }}
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          size="small"
                          color="error"
                          disabled={draftLocked || busy}
                          onClick={() => void deleteLine(ln.id)}
                          data-testid="seller-inbound-line-delete"
                        >
                          Удалить
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {detail.lines.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography variant="body2" color="text.secondary">
                        Добавьте товары кнопкой «Добавить товары».
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      <Dialog
        open={pickerOpen}
        onClose={() => (busy ? undefined : setPickerOpen(false))}
        maxWidth={false}
        fullWidth
        slotProps={{ paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } } }}
        data-testid="seller-inbound-picker"
      >
        <DialogTitle>Выбор товаров</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mb: 2 }}>
            <TextField
              label="Поиск (артикул, ШК, nm, название, артикул продавца)"
              value={pickerSearch}
              onChange={(e) => setPickerSearch(e.target.value)}
              size="small"
              fullWidth
              slotProps={{ htmlInput: { 'data-testid': 'seller-inbound-picker-search' } }}
            />
            <FormControl size="small" sx={{ minWidth: 260 }}>
              <InputLabel id="picker-cat-label">Категория (WB)</InputLabel>
              <Select
                labelId="picker-cat-label"
                label="Категория (WB)"
                value={pickerCategory}
                onChange={(e) => setPickerCategory(e.target.value)}
                data-testid="seller-inbound-picker-category"
              >
                <MenuItem value="__all__">Все</MenuItem>
                {categories.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
          <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
            <Table
              size="small"
              data-testid="seller-inbound-picker-table"
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
                  <TableCell sx={{ width: 160, pl: 2 }}>Артикул</TableCell>
                  <TableCell sx={{ width: 190 }}>ШК</TableCell>
                  <TableCell sx={{ width: 150 }}>Артикул продавца</TableCell>
                  <TableCell sx={{ width: 120, pr: 2 }}>Артикул WB</TableCell>
                  <TableCell sx={{ pl: 2 }}>Наименование</TableCell>
                  <TableCell align="right" sx={{ width: 140 }}>
                    Кол-во в заявку
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredPickerRows.map((r) => {
                  const inDraft = lineProductIds.has(r.id)
                  const qty = pickerQtyByProduct[r.id] ?? 0
                  return (
                    <TableRow
                      key={r.id}
                      hover
                      sx={{
                        opacity: inDraft ? 0.45 : 1,
                        bgcolor: inDraft ? 'action.hover' : undefined,
                        '& td': { px: 1.25 },
                        '& td:first-of-type': { pl: 1 },
                        '& td:last-of-type': { pr: 1 },
                      }}
                      data-testid="seller-inbound-picker-row"
                      data-in-draft={inDraft ? '1' : '0'}
                    >
                      <TableCell>
                        <Avatar
                          variant="rounded"
                          src={r.wb_primary_image_url ?? undefined}
                          sx={{ width: 44, height: 44 }}
                        />
                      </TableCell>
                      <TableCell
                        sx={{
                          whiteSpace: 'normal',
                          wordBreak: 'break-word',
                          overflow: 'hidden',
                          pl: 2,
                        }}
                        title={r.sku_code}
                      >
                        {r.sku_code}
                      </TableCell>
                      <TableCell
                        sx={{ whiteSpace: 'normal', wordBreak: 'break-word', overflow: 'hidden' }}
                        title={r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}
                      >
                        {r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}
                      </TableCell>
                      <TableCell
                        sx={{ whiteSpace: 'normal', wordBreak: 'break-word', overflow: 'hidden' }}
                        title={r.wb_vendor_code ?? '—'}
                      >
                        {r.wb_vendor_code ?? '—'}
                      </TableCell>
                      <TableCell sx={{ pr: 2 }}>{r.wb_nm_id ?? '—'}</TableCell>
                      <TableCell
                        sx={{
                          pl: 2,
                          maxWidth: 440,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                        title={r.name}
                      >
                        <Typography variant="body2" sx={{ lineHeight: 1.25 }} noWrap>
                          {r.name}
                        </Typography>
                        {inDraft ? (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>
                            Товар уже добавлен в заявку
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right" sx={{ minWidth: 120 }}>
                        <TextField
                          type="number"
                          size="small"
                          disabled={inDraft || busy}
                          value={qty || ''}
                          onChange={(e) => setPickerQty(r.id, Number(e.target.value))}
                          slotProps={{
                            htmlInput: {
                              min: 0,
                              'data-testid': 'seller-inbound-picker-qty',
                            },
                          }}
                        />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPickerOpen(false)} disabled={busy} data-testid="seller-inbound-picker-cancel">
            Отмена
          </Button>
          <Button variant="contained" onClick={() => void applyPicker()} disabled={busy} data-testid="seller-inbound-picker-apply">
            Добавить в заявку
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
