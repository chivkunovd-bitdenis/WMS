import { useCallback, useEffect, useMemo, useState } from 'react'
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

type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }

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
  distribution_completed_at: string | null
  lines: InboundLine[]
}

type DistributionLineOut = {
  id: string
  product_id: string
  storage_location_id: string
  storage_location_code: string
  quantity: number
  created_at: string
}

type DistributionLineDraft = {
  product_id: string
  storage_location_id: string
  quantity: string
}

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

type Props = {
  token: string
  requestId: string
  isFulfillmentAdmin: boolean
  onClose: () => void
}

function statusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Передано на склад'
  if (status === 'primary_accepted') return 'Принято на складе'
  if (status === 'verifying') return 'Проверка на складе'
  if (status === 'verified') return 'Проверено на складе'
  if (status === 'posted') return 'Оприходовано'
  return status
}

export function FfInboundRequestView({ token, requestId, isFulfillmentAdmin, onClose }: Props) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const [detail, setDetail] = useState<InboundDetail | null>(null)
  const [catalog, setCatalog] = useState<WbCatalogRow[] | null>(null)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actualDraftByLineId, setActualDraftByLineId] = useState<Record<string, string>>({})

  const [distOpen, setDistOpen] = useState(false)
  const [distBusy, setDistBusy] = useState(false)
  const [distError, setDistError] = useState<string | null>(null)
  const [distLines, setDistLines] = useState<DistributionLineDraft[]>([])

  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerSearch, setPickerSearch] = useState('')
  const [pickerCategory, setPickerCategory] = useState<string>('__all__')
  const [pickerQtyByProduct, setPickerQtyByProduct] = useState<Record<string, number>>({})

  const [plannedDateDraft, setPlannedDateDraft] = useState<string>('')

  const loadDetail = useCallback(async () => {
    const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
      headers: authHeaders,
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    setDetail((await res.json()) as InboundDetail)
  }, [authHeaders, requestId])

  const loadCatalog = useCallback(async () => {
    const res = await fetch(apiUrl('/products/wb-catalog'), { headers: authHeaders })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    setCatalog((await res.json()) as WbCatalogRow[])
  }, [authHeaders])

  const loadLocations = useCallback(
    async (warehouseId: string) => {
      const res = await fetch(apiUrl(`/warehouses/${warehouseId}/locations`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setLocations([])
        return
      }
      setLocations((await res.json()) as LocationRow[])
    },
    [authHeaders],
  )

  const loadDistribution = useCallback(async () => {
    if (!detail) return
    setDistError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
        { headers: authHeaders },
      )
      if (!res.ok) {
        setDistLines([])
        return
      }
      const rows = (await res.json()) as DistributionLineOut[]
      setDistLines(
        rows.map((r) => ({
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
    } catch (e) {
      setDistLines([])
      setDistError(e instanceof Error ? e.message : 'Не удалось загрузить распределение.')
    }
  }, [authHeaders, detail, requestId])

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    setError(null)
    void (async () => {
      try {
        await loadDetail()
        if (!cancelled) {
          setBusy(false)
        }
      } catch (e) {
        if (!cancelled) {
          setBusy(false)
          setError(e instanceof Error ? e.message : 'Не удалось загрузить заявку.')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadDetail])

  useEffect(() => {
    setPlannedDateDraft(detail?.planned_delivery_date ?? '')
  }, [detail?.planned_delivery_date])

  useEffect(() => {
    if (!detail) {
      setActualDraftByLineId({})
      return
    }
    // Keep drafts for lines that exist; default to actual if present, else expected.
    setActualDraftByLineId((prev) => {
      const next: Record<string, string> = {}
      for (const ln of detail.lines) {
        const existing = prev[ln.id]
        if (existing !== undefined) {
          next[ln.id] = existing
        } else {
          const v = ln.actual_qty ?? ln.expected_qty
          next[ln.id] = String(v)
        }
      }
      return next
    })
  }, [detail])

  useEffect(() => {
    if (!detail) {
      setLocations([])
      return
    }
    // For verified stage we need the cell directory to assign storage locations.
    if (!detail.warehouse_id) {
      setLocations([])
      return
    }
    void loadLocations(detail.warehouse_id)
  }, [detail?.warehouse_id, loadLocations, detail])

  useEffect(() => {
    if (!detail) {
      setDistOpen(false)
      setDistLines([])
      return
    }
    if (!isFulfillmentAdmin) {
      setDistOpen(false)
      setDistLines([])
      return
    }
    if (!['verified'].includes(detail.status)) {
      setDistOpen(false)
      setDistLines([])
      return
    }
    void loadDistribution()
  }, [detail, isFulfillmentAdmin, loadDistribution])

  const catalogById = useMemo(() => {
    const m = new Map<string, WbCatalogRow>()
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

  const categories = useMemo(() => {
    if (!catalog) return []
    const s = new Set<string>()
    for (const r of catalog) {
      const c = r.wb_subject_name?.trim()
      if (c) s.add(c)
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [catalog])

  const filteredPickerRows = useMemo(() => {
    if (!catalog) return []
    const q = pickerSearch.trim().toLowerCase()
    return catalog.filter((r) => {
      if (pickerCategory !== '__all__') {
        const sub = (r.wb_subject_name ?? '').trim()
        if (sub !== pickerCategory) return false
      }
      if (!q) return true
      const nm = r.wb_nm_id != null ? String(r.wb_nm_id) : ''
      const barcodes = r.wb_barcodes.join(' ').toLowerCase()
      const hay = `${r.sku_code} ${r.wb_vendor_code ?? ''} ${r.name} ${nm} ${barcodes}`.toLowerCase()
      return hay.includes(q)
    })
  }, [catalog, pickerCategory, pickerSearch])

  const draftLocked = detail != null && detail.status !== 'draft'

  const acceptedQtyByProductId = useMemo(() => {
    const m = new Map<string, number>()
    if (!detail) return m
    for (const ln of detail.lines) {
      const accepted = ln.actual_qty ?? ln.expected_qty
      m.set(ln.product_id, accepted)
    }
    return m
  }, [detail])

  const distributableProducts = useMemo(() => {
    if (!detail) return []
    const rows = detail.lines
      .map((ln) => ({
        product_id: ln.product_id,
        sku_code: ln.sku_code,
        product_name: ln.product_name,
        accepted_qty: ln.actual_qty ?? ln.expected_qty,
      }))
      .filter((x) => x.accepted_qty > 0)
    const seen = new Set<string>()
    const uniq: typeof rows = []
    for (const r of rows) {
      if (seen.has(r.product_id)) continue
      seen.add(r.product_id)
      uniq.push(r)
    }
    return uniq.sort((a, b) => a.sku_code.localeCompare(b.sku_code))
  }, [detail])

  const distSumByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const r of distLines) {
      const pid = r.product_id
      if (!pid) continue
      const q = Math.floor(Number(r.quantity))
      if (!Number.isFinite(q) || q <= 0) continue
      m.set(pid, (m.get(pid) ?? 0) + q)
    }
    return m
  }, [distLines])

  const distRemainingByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of distributableProducts) {
      const accepted = p.accepted_qty
      const used = distSumByProductId.get(p.product_id) ?? 0
      m.set(p.product_id, Math.max(accepted - used, 0))
    }
    return m
  }, [distributableProducts, distSumByProductId])

  const distributionCompleted = Boolean(detail?.distribution_completed_at)
  const distributionEditable = isFulfillmentAdmin && !distributionCompleted

  const saveDistribution = async () => {
    if (!detail) return
    setDistBusy(true)
    setDistError(null)
    try {
      const payload = distLines
        .filter((r) => r.product_id && r.storage_location_id && r.quantity)
        .map((r) => ({
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: Math.floor(Number(r.quantity)),
        }))
        .filter((r) => Number.isFinite(r.quantity) && r.quantity > 0)
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-lines`),
        {
          method: 'PUT',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      if (!res.ok) {
        setDistError(await readApiErrorMessage(res))
        return
      }
      const rows = (await res.json()) as DistributionLineOut[]
      setDistLines(
        rows.map((r) => ({
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
    } catch (e) {
      setDistError(e instanceof Error ? e.message : 'Не удалось сохранить распределение.')
    } finally {
      setDistBusy(false)
    }
  }

  const completeDistribution = async () => {
    if (!detail) return
    setDistBusy(true)
    setDistError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/distribution-complete`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setDistError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
      await loadDistribution()
      setDistOpen(true)
    } catch (e) {
      setDistError(e instanceof Error ? e.message : 'Не удалось завершить распределение.')
    } finally {
      setDistBusy(false)
    }
  }

  const patchPlannedDate = async (isoDate: string) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${requestId}`), {
        method: 'PATCH',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ planned_delivery_date: isoDate }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setDetail((await res.json()) as InboundDetail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить дату.')
    } finally {
      setBusy(false)
    }
  }

  const openPicker = async () => {
    setError(null)
    try {
      if (catalog == null) {
        await loadCatalog()
      }
      setPickerOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
    }
  }

  const applyPicker = async () => {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      const lineByProduct = new Map(detail.lines.map((ln) => [ln.product_id, ln]))
      for (const [productId, rawQty] of Object.entries(pickerQtyByProduct)) {
        const addQty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (addQty <= 0) continue
        const existing = lineByProduct.get(productId)
        if (existing) {
          const next = existing.expected_qty + addQty
          const res = await fetch(
            apiUrl(
              `/operations/inbound-intake-requests/${requestId}/lines/${existing.id}/expected`,
            ),
            {
              method: 'PATCH',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ expected_qty: next }),
            },
          )
          if (!res.ok) {
            setError(await readApiErrorMessage(res))
            return
          }
        } else {
          const res = await fetch(
            apiUrl(`/operations/inbound-intake-requests/${requestId}/lines`),
            {
              method: 'POST',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ product_id: productId, expected_qty: addQty }),
            },
          )
          if (!res.ok) {
            setError(await readApiErrorMessage(res))
            return
          }
        }
      }
      setPickerQtyByProduct({})
      setPickerOpen(false)
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось добавить товары.')
    } finally {
      setBusy(false)
    }
  }

  const submitToWarehouse = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/submit`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось передать на склад.')
    } finally {
      setBusy(false)
    }
  }

  const primaryAccept = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/primary-accept`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await loadDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить первичную приёмку.')
    } finally {
      setBusy(false)
    }
  }

  const setLineActual = async (lineId: string, actualQty: number) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/lines/${lineId}/actual`),
        {
          method: 'PATCH',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ actual_qty: actualQty }),
        },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setError(msg === 'actual_missing' ? 'Укажите факт по всем строкам.' : msg)
        return
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить факт.')
    } finally {
      setBusy(false)
    }
  }

  const ensureActualsSaved = async () => {
    if (!detail) {
      return
    }
    // Save actuals for all lines (required by backend before verify).
    // Important: do not rely on onBlur — user can click "Завершить" while focus is in the field.
    for (const ln of detail.lines) {
      const raw = actualDraftByLineId[ln.id]
      const v = Number(raw)
      if (!Number.isFinite(v) || v < 0) {
        throw new Error('Укажите факт по всем строкам (целое число ≥ 0).')
      }
      // Avoid redundant patches when already saved and unchanged.
      if (ln.actual_qty != null && v === ln.actual_qty) {
        continue
      }
      // Backend accepts patch only for verifying stage; still, patching here matches the UX intent.
      await setLineActual(ln.id, Math.floor(v))
    }
    await loadDetail()
  }

  const completeVerify = async () => {
    setBusy(true)
    setError(null)
    try {
      await ensureActualsSaved()
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${requestId}/verify`),
        { method: 'POST', headers: authHeaders },
      )
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setError(msg === 'actual_missing' ? 'Укажите факт по всем строкам.' : msg)
        return
      }
      await loadDetail()
      setDistOpen(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось завершить пересчёт.')
    } finally {
      setBusy(false)
    }
  }

  if (busy && !detail) {
    return (
      <Stack sx={{ py: 6, alignItems: 'center' }} data-testid="ff-inbound-doc-loading">
        <CircularProgress />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Загрузка…
        </Typography>
      </Stack>
    )
  }

  return (
    <Box data-testid="ff-inbound-doc-root">
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-inbound-doc-error">
          {error}
        </Alert>
      ) : null}

      {!detail ? (
        <Alert severity="warning">Заявка не найдена или недоступна.</Alert>
      ) : (
        <Paper variant="outlined" sx={{ p: 2, minHeight: '38vh' }}>
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
                if ((plannedDateDraft || '') !== (detail.planned_delivery_date ?? '')) {
                  void patchPlannedDate(plannedDateDraft)
                }
              }}
              slotProps={{
                inputLabel: { shrink: true },
                htmlInput: { 'data-testid': 'ff-inbound-planned-date' },
              }}
            />
            <Chip
              label={statusRu(detail.status)}
              color={detail.status === 'draft' ? 'default' : 'primary'}
              data-testid="ff-inbound-status-chip"
            />
            <Box sx={{ flexGrow: 1 }} />

            {detail.status === 'draft' ? (
              <>
                <Button
                  variant="outlined"
                  disabled={draftLocked || busy}
                  onClick={() => void openPicker()}
                  data-testid="ff-inbound-add-products"
                >
                  Добавить товары
                </Button>
                <Button
                  variant="contained"
                  color="secondary"
                  disabled={busy || detail.lines.length === 0}
                  onClick={() => void submitToWarehouse()}
                  data-testid="ff-inbound-submit-warehouse"
                >
                  Передать на склад
                </Button>
              </>
            ) : null}

            <Button variant="outlined" disabled={busy} onClick={onClose} data-testid="ff-inbound-close">
              Закрыть
            </Button>
          </Stack>

          <TableContainer sx={{ width: '100%', overflowX: 'hidden' }}>
            <Table
              size="small"
              data-testid="ff-inbound-lines-table"
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
                      data-testid="ff-inbound-line-row"
                      sx={{
                        '& td': { px: 1.25 },
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
                      <TableCell sx={{ whiteSpace: 'nowrap', pl: 2 }} title={ln.sku_code}>
                        {ln.sku_code}
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }} title={barcode}>
                        {barcode}
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
                      <TableCell align="right" sx={{ minWidth: 120 }}>
                        {ln.expected_qty}
                      </TableCell>
                    </TableRow>
                  )
                })}
                {detail.lines.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <Typography variant="body2" color="text.secondary">
                        Пока нет строк. Добавьте товары.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>

          {isFulfillmentAdmin ? (
            <Box sx={{ mt: 2 }}>
              {detail.status === 'submitted' ? (
                <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-admin-submitted">
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                    Действия фулфилмента
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    Привоз принят без пересчёта.
                  </Typography>
                  <Button
                    variant="contained"
                    disabled={busy}
                    onClick={() => void primaryAccept()}
                    data-testid="ff-inbound-primary-accept"
                  >
                    Принято первично
                  </Button>
                </Paper>
              ) : null}

              {detail.status === 'primary_accepted' || detail.status === 'verifying' || detail.status === 'verified' ? (
                <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-admin-verify">
                  <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1 }}>
                    Пересчёт (факт)
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {detail.status === 'verified'
                      ? 'Факт зафиксирован. Данные доступны только для просмотра.'
                      : 'Укажи факт по строкам, затем заверши пересчёт.'}
                  </Typography>
                  <Stack spacing={1.25} sx={{ mb: 2 }}>
                    {detail.lines.map((ln) => (
                      <Stack
                        key={ln.id}
                        direction={{ xs: 'column', sm: 'row' }}
                        spacing={1}
                        sx={{ alignItems: { sm: 'center' } }}
                      >
                        <Typography variant="body2" sx={{ minWidth: 220 }}>
                          {ln.sku_code} · план {ln.expected_qty}
                        </Typography>
                        <TextField
                          type="number"
                          size="small"
                          label="Факт"
                          disabled={busy || detail.status === 'verified'}
                          value={actualDraftByLineId[ln.id] ?? String(ln.actual_qty ?? ln.expected_qty)}
                          onChange={(e) =>
                            setActualDraftByLineId((prev) => ({ ...prev, [ln.id]: e.target.value }))
                          }
                          slotProps={{ htmlInput: { min: 0, 'data-testid': 'ff-inbound-line-actual' } }}
                          onBlur={() => {
                            const raw = actualDraftByLineId[ln.id]
                            const v = Number(raw)
                            if (!Number.isFinite(v) || v < 0) return
                            if (ln.actual_qty != null && v === ln.actual_qty) return
                            void setLineActual(ln.id, Math.floor(v))
                          }}
                        />
                      </Stack>
                    ))}
                  </Stack>
                  {detail.status !== 'verified' ? (
                    <Button
                      variant="contained"
                      disabled={busy}
                      onClick={() => void completeVerify()}
                      data-testid="ff-inbound-verify-complete"
                    >
                      Завершить пересчёт
                    </Button>
                  ) : null}
                </Paper>
              ) : null}

              {detail.status === 'verified' ? (
                <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-admin-distribution">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                        Распределение по ячейкам
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Доступно после завершения пересчёта. Нераспределённый остаток попадёт в «Без ячейки».
                      </Typography>
                    </Box>
                    <Button
                      variant="contained"
                      disabled={distBusy || distributionCompleted}
                      onClick={() => setDistOpen(true)}
                      data-testid="ff-inbound-distribute-open"
                    >
                      Распределить по ячейкам
                    </Button>
                  </Stack>

                  {distError ? (
                    <Alert severity="error" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-error">
                      {distError}
                    </Alert>
                  ) : null}

                  {distOpen || distributionCompleted ? (
                    <Box sx={{ mt: 2 }}>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1.5, alignItems: { sm: 'center' } }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          Таблица распределения {distributionCompleted ? ' (зафиксировано)' : ''}
                        </Typography>
                        <Box sx={{ flexGrow: 1 }} />
                        {distributionEditable ? (
                          <>
                            <Button
                              variant="outlined"
                              disabled={distBusy}
                              onClick={() =>
                                setDistLines((prev) => [...prev, { product_id: '', storage_location_id: '', quantity: '' }])
                              }
                              data-testid="ff-inbound-distribution-add-row"
                            >
                              Добавить строку
                            </Button>
                            <Button
                              variant="outlined"
                              disabled={distBusy}
                              onClick={() => void saveDistribution()}
                              data-testid="ff-inbound-distribution-save"
                            >
                              Сохранить
                            </Button>
                            <Button
                              variant="contained"
                              disabled={distBusy}
                              onClick={() => void completeDistribution()}
                              data-testid="ff-inbound-distribution-complete"
                            >
                              Завершить распределение
                            </Button>
                          </>
                        ) : null}
                      </Stack>

                      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
                        <Table size="small" data-testid="ff-inbound-distribution-table">
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ width: 420 }}>Товар</TableCell>
                              <TableCell align="right" sx={{ width: 140 }}>Кол-во</TableCell>
                              <TableCell sx={{ width: 260 }}>Ячейка</TableCell>
                              {distributionEditable ? <TableCell align="right" sx={{ width: 84 }} /> : null}
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {distLines.map((row, idx) => {
                              const accepted = acceptedQtyByProductId.get(row.product_id) ?? 0
                              const usedOther = (distSumByProductId.get(row.product_id) ?? 0) - (Math.floor(Number(row.quantity)) || 0)
                              const maxForRow = Math.max(accepted - usedOther, 0)
                              return (
                                <TableRow key={idx} data-testid="ff-inbound-distribution-row">
                                  <TableCell>
                                    <FormControl size="small" fullWidth>
                                      <InputLabel id={`ff-dist-prod-${idx}`}>Товар</InputLabel>
                                      <Select
                                        labelId={`ff-dist-prod-${idx}`}
                                        label="Товар"
                                        value={row.product_id}
                                        disabled={distBusy || !distributionEditable}
                                        onChange={(e) => {
                                          const v = String(e.target.value)
                                          setDistLines((prev) =>
                                            prev.map((r, i) => (i === idx ? { ...r, product_id: v } : r)),
                                          )
                                        }}
                                        data-testid="ff-inbound-distribution-product"
                                      >
                                        <MenuItem value="">
                                          <em>Выберите товар</em>
                                        </MenuItem>
                                        {distributableProducts.map((p) => (
                                          <MenuItem key={p.product_id} value={p.product_id}>
                                            {p.sku_code} · {p.product_name} (принято {p.accepted_qty})
                                          </MenuItem>
                                        ))}
                                      </Select>
                                    </FormControl>
                                  </TableCell>
                                  <TableCell align="right">
                                    <TextField
                                      type="number"
                                      size="small"
                                      value={row.quantity}
                                      disabled={distBusy || !distributionEditable}
                                      onChange={(e) =>
                                        setDistLines((prev) =>
                                          prev.map((r, i) => (i === idx ? { ...r, quantity: e.target.value } : r)),
                                        )
                                      }
                                      slotProps={{ htmlInput: { min: 1, max: maxForRow, 'data-testid': 'ff-inbound-distribution-qty' } }}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <FormControl size="small" fullWidth>
                                      <InputLabel id={`ff-dist-loc-${idx}`}>Ячейка</InputLabel>
                                      <Select
                                        labelId={`ff-dist-loc-${idx}`}
                                        label="Ячейка"
                                        value={row.storage_location_id}
                                        disabled={distBusy || !distributionEditable || locations.length === 0}
                                        onChange={(e) => {
                                          const v = String(e.target.value)
                                          setDistLines((prev) =>
                                            prev.map((r, i) => (i === idx ? { ...r, storage_location_id: v } : r)),
                                          )
                                        }}
                                        data-testid="ff-inbound-distribution-location"
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
                                  </TableCell>
                                  {distributionEditable ? (
                                    <TableCell align="right">
                                      <Button
                                        variant="text"
                                        color="error"
                                        disabled={distBusy}
                                        onClick={() => setDistLines((prev) => prev.filter((_, i) => i !== idx))}
                                        data-testid="ff-inbound-distribution-remove-row"
                                      >
                                        Удалить
                                      </Button>
                                    </TableCell>
                                  ) : null}
                                </TableRow>
                              )
                            })}
                            {distLines.length === 0 ? (
                              <TableRow>
                                <TableCell colSpan={distributionEditable ? 4 : 3}>
                                  <Typography variant="body2" color="text.secondary">
                                    Пока нет строк распределения.
                                  </Typography>
                                </TableCell>
                              </TableRow>
                            ) : null}
                          </TableBody>
                        </Table>
                      </TableContainer>

                      <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-distribution-no-cell">
                        <Typography variant="body2" sx={{ fontWeight: 700, mb: 1 }}>
                          Остаток «Без ячейки»
                        </Typography>
                        <Stack spacing={0.5}>
                          {distributableProducts
                            .map((p) => {
                              const rem = distRemainingByProductId.get(p.product_id) ?? p.accepted_qty
                              return { ...p, remaining: rem }
                            })
                            .filter((p) => p.remaining > 0)
                            .map((p) => (
                              <Typography key={p.product_id} variant="body2" color="text.secondary">
                                {p.sku_code} · {p.product_name}: {p.remaining}
                              </Typography>
                            ))}
                          {distributableProducts.every((p) => (distRemainingByProductId.get(p.product_id) ?? p.accepted_qty) <= 0) ? (
                            <Typography variant="body2" color="text.secondary">
                              Остатков нет.
                            </Typography>
                          ) : null}
                        </Stack>
                      </Paper>
                    </Box>
                  ) : null}
                </Paper>
              ) : null}
            </Box>
          ) : null}
        </Paper>
      )}

      <Dialog
        open={pickerOpen}
        onClose={() => (busy ? undefined : setPickerOpen(false))}
        maxWidth={false}
        fullWidth
        slotProps={{ paper: { sx: { width: 'min(1200px, 96vw)', maxHeight: '92vh' } } }}
        data-testid="ff-inbound-picker"
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
              slotProps={{ htmlInput: { 'data-testid': 'ff-inbound-picker-search' } }}
            />
            <FormControl size="small" sx={{ minWidth: 260 }}>
              <InputLabel id="ff-picker-cat-label">Категория (WB)</InputLabel>
              <Select
                labelId="ff-picker-cat-label"
                label="Категория (WB)"
                value={pickerCategory}
                onChange={(e) => setPickerCategory(String(e.target.value))}
                data-testid="ff-inbound-picker-category"
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
              data-testid="ff-inbound-picker-table"
              sx={{ tableLayout: 'fixed', width: '100%' }}
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
                      sx={{ opacity: inDraft ? 0.45 : 1 }}
                      data-testid="ff-inbound-picker-row"
                      data-in-draft={inDraft ? '1' : '0'}
                    >
                      <TableCell>
                        <Avatar variant="rounded" src={r.wb_primary_image_url ?? undefined} sx={{ width: 44, height: 44 }} />
                      </TableCell>
                      <TableCell sx={{ pl: 2 }} title={r.sku_code}>
                        {r.sku_code}
                      </TableCell>
                      <TableCell title={r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}>
                        {r.wb_primary_barcode ?? (r.wb_barcodes[0] ?? '—')}
                      </TableCell>
                      <TableCell title={r.wb_vendor_code ?? '—'}>{r.wb_vendor_code ?? '—'}</TableCell>
                      <TableCell sx={{ pr: 2 }}>{r.wb_nm_id ?? '—'}</TableCell>
                      <TableCell sx={{ pl: 2 }} title={r.name}>
                        <Typography variant="body2" noWrap>
                          {r.name}
                        </Typography>
                        {inDraft ? (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }} noWrap>
                            Товар уже добавлен в заявку
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          type="number"
                          size="small"
                          disabled={inDraft || busy}
                          value={qty || ''}
                          onChange={(e) =>
                            setPickerQtyByProduct((prev) => ({
                              ...prev,
                              [r.id]: Number(e.target.value),
                            }))
                          }
                          slotProps={{ htmlInput: { min: 0, 'data-testid': 'ff-inbound-picker-qty' } }}
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
          <Button onClick={() => setPickerOpen(false)} disabled={busy} data-testid="ff-inbound-picker-cancel">
            Отмена
          </Button>
          <Button variant="contained" onClick={() => void applyPicker()} disabled={busy} data-testid="ff-inbound-picker-apply">
            Добавить в заявку
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

