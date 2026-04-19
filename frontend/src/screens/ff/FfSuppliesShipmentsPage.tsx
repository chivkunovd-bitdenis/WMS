import { useCallback, useEffect, useMemo, useState } from 'react'
import { DeleteOutlineOutlined } from '@mui/icons-material'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import type { FfInboundSummary, FfOutboundSummary } from './FfDashboard'

export type FfMarketplaceUnloadSummary = {
  id: string
  warehouse_id: string
  warehouse_name: string
  status: string
  line_count: number
  seller_id: string | null
  seller_name: string | null
  created_at: string
}

export type FfDiscrepancyActSummary = {
  id: string
  status: string
  line_count: number
  inbound_intake_request_id: string | null
  seller_id: string | null
  seller_name: string | null
  created_at: string
}

type DocLineRow = {
  id: string
  sku_code: string
  product_name: string
  quantity: number
  inbound_intake_line_id?: string | null
}

type MarketplaceUnloadDetail = {
  id: string
  warehouse_name: string
  status: string
  lines: DocLineRow[]
}

type DiscrepancyActDetail = {
  id: string
  status: string
  inbound_intake_request_id: string | null
  lines: DocLineRow[]
}

type DocKind = 'inbound' | 'outbound' | 'marketplace_unload' | 'discrepancy_act'

type UnifiedRow = {
  kind: DocKind
  id: string
  plannedDate: string | null
  createdAt: string | null
  status: string
  lineCount: number
  sellerName: string | null
  extraLabel: string | null
}

function statusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'confirmed') return 'Утверждено'
  if (status === 'submitted') return 'Запланировано'
  if (status === 'primary_accepted') return 'Принято на складе'
  if (status === 'verifying') return 'Проверка'
  if (status === 'verified') return 'Проверено'
  if (status === 'posted') return 'Проведено'
  return status
}

function kindRu(kind: DocKind): string {
  if (kind === 'inbound') return 'Приёмка'
  if (kind === 'outbound') return 'Отгрузка'
  if (kind === 'marketplace_unload') return 'Выгрузка на МП'
  return 'Расхождение'
}

type ProductPick = { id: string; sku_code: string; name: string }

type Props = {
  busy: boolean
  error: string | null
  infoNotice: string | null
  onDismissInfoNotice: () => void
  token: string | null
  productPicklist: ProductPick[]
  onRefreshFfSupplyExtras: () => Promise<void>
  inboundSummaries: FfInboundSummary[]
  outboundSummaries: FfOutboundSummary[]
  marketplaceUnloadSummaries: FfMarketplaceUnloadSummary[]
  discrepancyActSummaries: FfDiscrepancyActSummary[]
  onOpenInbound: (id: string) => void
  onOpenOutbound: (id: string) => void
  onCreateMarketplaceDownload: () => void
  onCreateDiverge: () => void
}

export function FfSuppliesShipmentsPage({
  busy,
  error,
  infoNotice,
  onDismissInfoNotice,
  token,
  productPicklist,
  onRefreshFfSupplyExtras,
  inboundSummaries,
  outboundSummaries,
  marketplaceUnloadSummaries,
  discrepancyActSummaries,
  onOpenInbound,
  onOpenOutbound,
  onCreateMarketplaceDownload,
  onCreateDiverge,
}: Props) {
  const [kind, setKind] = useState<'all' | DocKind>('all')
  const [sellerFilter, setSellerFilter] = useState<string>('all')
  const [sortKey, setSortKey] = useState<'planned_desc' | 'planned_asc' | 'created_desc' | 'created_asc'>(
    'created_desc',
  )

  const [docModal, setDocModal] = useState<null | 'marketplace_unload' | 'discrepancy_act'>(null)
  const [docModalId, setDocModalId] = useState<string | null>(null)
  const [modalBusy, setModalBusy] = useState(false)
  const [modalError, setModalError] = useState<string | null>(null)
  const [unloadDetail, setUnloadDetail] = useState<MarketplaceUnloadDetail | null>(null)
  const [divergeDetail, setDivergeDetail] = useState<DiscrepancyActDetail | null>(null)
  const [lineProductId, setLineProductId] = useState<string>('')
  const [lineQty, setLineQty] = useState<string>('1')
  const [inboundRefLines, setInboundRefLines] = useState<
    { id: string; product_id: string; sku_code: string; product_name: string }[]
  >([])
  const [selectedInboundLineId, setSelectedInboundLineId] = useState<string>('')

  const authHeaders = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : null),
    [token],
  )

  const loadDocDetail = useCallback(async () => {
    if (!token || !authHeaders || !docModal || !docModalId) {
      setUnloadDetail(null)
      setDivergeDetail(null)
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      if (docModal === 'marketplace_unload') {
        const res = await fetch(apiUrl(`/operations/marketplace-unload-requests/${docModalId}`), {
          headers: authHeaders,
        })
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          setUnloadDetail(null)
          return
        }
        const j = (await res.json()) as {
          id: string
          warehouse_name: string
          status: string
          lines: { id: string; sku_code: string; product_name: string; quantity: number }[]
        }
        setUnloadDetail({
          id: j.id,
          warehouse_name: j.warehouse_name,
          status: j.status,
          lines: j.lines.map((ln) => ({
            id: ln.id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
            quantity: ln.quantity,
            inbound_intake_line_id: null,
          })),
        })
        setDivergeDetail(null)
      } else {
        const res = await fetch(apiUrl(`/operations/discrepancy-acts/${docModalId}`), {
          headers: authHeaders,
        })
        if (!res.ok) {
          setModalError(await readApiErrorMessage(res))
          setDivergeDetail(null)
          return
        }
        const j = (await res.json()) as {
          id: string
          status: string
          inbound_intake_request_id: string | null
          lines: {
            id: string
            sku_code: string
            product_name: string
            quantity: number
            inbound_intake_line_id?: string | null
          }[]
        }
        setDivergeDetail({
          id: j.id,
          status: j.status,
          inbound_intake_request_id: j.inbound_intake_request_id,
          lines: j.lines.map((ln) => ({
            id: ln.id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
            quantity: ln.quantity,
            inbound_intake_line_id: ln.inbound_intake_line_id ?? null,
          })),
        })
        setUnloadDetail(null)
      }
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось загрузить документ.')
      setUnloadDetail(null)
      setDivergeDetail(null)
    } finally {
      setModalBusy(false)
    }
  }, [token, authHeaders, docModal, docModalId])

  useEffect(() => {
    void loadDocDetail()
  }, [loadDocDetail])

  useEffect(() => {
    if (!token || !authHeaders || docModal !== 'discrepancy_act' || !divergeDetail?.inbound_intake_request_id) {
      setInboundRefLines([])
      setSelectedInboundLineId('')
      return
    }
    const rid = divergeDetail.inbound_intake_request_id
    void (async () => {
      try {
        const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${rid}`), {
          headers: authHeaders,
        })
        if (!res.ok) {
          setInboundRefLines([])
          return
        }
        const j = (await res.json()) as {
          lines: { id: string; product_id: string; sku_code: string; product_name: string }[]
        }
        setInboundRefLines(
          j.lines.map((ln) => ({
            id: ln.id,
            product_id: ln.product_id,
            sku_code: ln.sku_code,
            product_name: ln.product_name,
          })),
        )
      } catch {
        setInboundRefLines([])
      }
    })()
  }, [token, authHeaders, docModal, divergeDetail?.inbound_intake_request_id])

  const closeDocModal = () => {
    setDocModal(null)
    setDocModalId(null)
    setUnloadDetail(null)
    setDivergeDetail(null)
    setModalError(null)
    setLineProductId('')
    setLineQty('1')
    setInboundRefLines([])
    setSelectedInboundLineId('')
  }

  const submitDoc = async () => {
    if (!token || !authHeaders || !docModal || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const path =
        docModal === 'marketplace_unload'
          ? `/operations/marketplace-unload-requests/${docModalId}/submit`
          : `/operations/discrepancy-acts/${docModalId}/submit`
      const res = await fetch(apiUrl(path), {
        method: 'POST',
        headers: authHeaders,
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось оформить документ.')
    } finally {
      setModalBusy(false)
    }
  }

  const deleteDocLine = async (lineId: string) => {
    if (!token || !authHeaders || !docModal || !docModalId) {
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const path =
        docModal === 'marketplace_unload'
          ? `/operations/marketplace-unload-requests/${docModalId}/lines/${lineId}`
          : `/operations/discrepancy-acts/${docModalId}/lines/${lineId}`
      const res = await fetch(apiUrl(path), {
        method: 'DELETE',
        headers: authHeaders,
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось удалить строку.')
    } finally {
      setModalBusy(false)
    }
  }

  const submitLine = async () => {
    if (!token || !authHeaders || !docModal || !docModalId || !lineProductId) {
      return
    }
    const q = Number(lineQty)
    if (!Number.isInteger(q) || q < 1) {
      setModalError('Укажите целое количество ≥ 1.')
      return
    }
    setModalBusy(true)
    setModalError(null)
    try {
      const path =
        docModal === 'marketplace_unload'
          ? `/operations/marketplace-unload-requests/${docModalId}/lines`
          : `/operations/discrepancy-acts/${docModalId}/lines`
      const res = await fetch(apiUrl(path), {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          product_id: lineProductId,
          quantity: q,
          ...(docModal === 'discrepancy_act' && selectedInboundLineId
            ? { inbound_intake_line_id: selectedInboundLineId }
            : {}),
        }),
      })
      if (!res.ok) {
        setModalError(await readApiErrorMessage(res))
        return
      }
      await loadDocDetail()
      await onRefreshFfSupplyExtras()
      setLineQty('1')
      setSelectedInboundLineId('')
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Не удалось добавить строку.')
    } finally {
      setModalBusy(false)
    }
  }

  const sellerOptions = useMemo(() => {
    const s = new Set<string>()
    for (const r of inboundSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    for (const r of outboundSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    for (const r of marketplaceUnloadSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    for (const r of discrepancyActSummaries) {
      if (r.seller_name) {
        s.add(r.seller_name)
      }
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [
    inboundSummaries,
    outboundSummaries,
    marketplaceUnloadSummaries,
    discrepancyActSummaries,
  ])

  const rows = useMemo(() => {
    const all: UnifiedRow[] = [
      ...inboundSummaries.map((r) => ({
        kind: 'inbound' as const,
        id: r.id,
        plannedDate: r.planned_delivery_date,
        createdAt: r.created_at ?? null,
        status: r.status,
        lineCount: r.line_count,
        sellerName: r.seller_name ?? null,
        extraLabel: null,
      })),
      ...outboundSummaries.map((r) => ({
        kind: 'outbound' as const,
        id: r.id,
        plannedDate: r.planned_shipment_date ?? r.created_at?.slice(0, 10) ?? null,
        createdAt: r.created_at ?? null,
        status: r.status,
        lineCount: r.line_count,
        sellerName: r.seller_name ?? null,
        extraLabel: null,
      })),
      ...marketplaceUnloadSummaries.map((r) => ({
        kind: 'marketplace_unload' as const,
        id: r.id,
        plannedDate: null,
        createdAt: r.created_at,
        status: r.status,
        lineCount: r.line_count,
        sellerName: r.seller_name ?? null,
        extraLabel: r.warehouse_name,
      })),
      ...discrepancyActSummaries.map((r) => ({
        kind: 'discrepancy_act' as const,
        id: r.id,
        plannedDate: null,
        createdAt: r.created_at,
        status: r.status,
        lineCount: r.line_count,
        sellerName: r.seller_name ?? null,
        extraLabel: r.inbound_intake_request_id ? `приёмка ${r.inbound_intake_request_id.slice(0, 8)}…` : null,
      })),
    ]
    let filtered = kind === 'all' ? all : all.filter((x) => x.kind === kind)
    if (sellerFilter !== 'all') {
      filtered = filtered.filter((x) => x.sellerName === sellerFilter)
    }
    const sorted = [...filtered].sort((a, b) => {
      if (sortKey === 'planned_desc') {
        return (b.plannedDate ?? '').localeCompare(a.plannedDate ?? '')
      }
      if (sortKey === 'planned_asc') {
        return (a.plannedDate ?? '').localeCompare(b.plannedDate ?? '')
      }
      if (sortKey === 'created_desc') {
        return (b.createdAt ?? '').localeCompare(a.createdAt ?? '')
      }
      return (a.createdAt ?? '').localeCompare(b.createdAt ?? '')
    })
    return sorted
  }, [
    inboundSummaries,
    outboundSummaries,
    marketplaceUnloadSummaries,
    discrepancyActSummaries,
    kind,
    sellerFilter,
    sortKey,
  ])

  const docTitle =
    docModal === 'marketplace_unload'
      ? 'Выгрузка на склад МП'
      : docModal === 'discrepancy_act'
        ? 'Акт расхождения'
        : ''

  const draftDoc =
    (docModal === 'marketplace_unload' && unloadDetail?.status === 'draft') ||
    (docModal === 'discrepancy_act' && divergeDetail?.status === 'draft')

  return (
    <Box data-testid="ff-supplies-shipments-page">
      <Typography variant="h5" gutterBottom>
        Поставки и загрузки
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Единый список заявок на приёмку, отгрузку на склад МП, выгрузку на маркетплейс (download) и акты расхождения
        (diverge). Строки выгрузки и расхождения — клик по строке; приёмка/отгрузка открываются в операциях.
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}

      {infoNotice ? (
        <Alert severity="success" onClose={onDismissInfoNotice} sx={{ mb: 2 }} data-testid="ff-supplies-info-notice">
          {infoNotice}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="ff-supplies-create-actions">
        <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 700 }}>
          Новые документы
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <Button
            variant="contained"
            color="primary"
            disabled={busy}
            data-testid="ff-create-marketplace-download"
            onClick={onCreateMarketplaceDownload}
          >
            Создать выгрузку
          </Button>
          <Button
            variant="outlined"
            color="secondary"
            disabled={busy}
            data-testid="ff-create-diverge"
            onClick={onCreateDiverge}
          >
            Создать расхождение
          </Button>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1.5}
          sx={{ flexWrap: 'wrap', alignItems: { xs: 'stretch', md: 'center' } }}
        >
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Button
              size="small"
              variant={kind === 'all' ? 'contained' : 'outlined'}
              onClick={() => setKind('all')}
              data-testid="ff-docs-filter-all"
            >
              Все
            </Button>
            <Button
              size="small"
              variant={kind === 'inbound' ? 'contained' : 'outlined'}
              onClick={() => setKind('inbound')}
              data-testid="ff-docs-filter-inbound"
            >
              Поставки
            </Button>
            <Button
              size="small"
              variant={kind === 'outbound' ? 'contained' : 'outlined'}
              onClick={() => setKind('outbound')}
              data-testid="ff-docs-filter-outbound"
            >
              Отгрузки
            </Button>
            <Button
              size="small"
              variant={kind === 'marketplace_unload' ? 'contained' : 'outlined'}
              onClick={() => setKind('marketplace_unload')}
              data-testid="ff-docs-filter-mp-unload"
            >
              Выгрузки МП
            </Button>
            <Button
              size="small"
              variant={kind === 'discrepancy_act' ? 'contained' : 'outlined'}
              onClick={() => setKind('discrepancy_act')}
              data-testid="ff-docs-filter-diverge"
            >
              Расхождения
            </Button>
          </Stack>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="ff-seller-filter-label">Селлер</InputLabel>
            <Select
              labelId="ff-seller-filter-label"
              label="Селлер"
              value={sellerFilter}
              onChange={(e) => setSellerFilter(String(e.target.value))}
              data-testid="ff-docs-seller-filter"
            >
              <MenuItem value="all">Все</MenuItem>
              {sellerOptions.map((n) => (
                <MenuItem key={n} value={n}>
                  {n}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel id="ff-sort-label">Сортировка</InputLabel>
            <Select
              labelId="ff-sort-label"
              label="Сортировка"
              value={sortKey}
              onChange={(e) =>
                setSortKey(e.target.value as typeof sortKey)
              }
              data-testid="ff-docs-sort"
            >
              <MenuItem value="planned_desc">Плановая дата ↓</MenuItem>
              <MenuItem value="planned_asc">Плановая дата ↑</MenuItem>
              <MenuItem value="created_desc">Дата создания ↓</MenuItem>
              <MenuItem value="created_asc">Дата создания ↑</MenuItem>
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Тип</TableCell>
            <TableCell>Плановая дата</TableCell>
            <TableCell>Создано</TableCell>
            <TableCell>Статус</TableCell>
            <TableCell>Селлер</TableCell>
            <TableCell>Доп.</TableCell>
            <TableCell align="right">Строк</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7}>
                <Typography variant="body2" color="text.secondary">
                  Нет документов
                </Typography>
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow
                key={`${row.kind}-${row.id}`}
                hover
                sx={{
                  cursor: busy ? 'default' : 'pointer',
                }}
                onClick={() => {
                  if (busy) {
                    return
                  }
                  if (row.kind === 'inbound') {
                    onOpenInbound(row.id)
                  } else if (row.kind === 'outbound') {
                    onOpenOutbound(row.id)
                  } else if (row.kind === 'marketplace_unload') {
                    setUnloadDetail(null)
                    setDivergeDetail(null)
                    setModalError(null)
                    setSelectedInboundLineId('')
                    setLineProductId('')
                    setDocModal('marketplace_unload')
                    setDocModalId(row.id)
                  } else if (row.kind === 'discrepancy_act') {
                    setUnloadDetail(null)
                    setDivergeDetail(null)
                    setModalError(null)
                    setSelectedInboundLineId('')
                    setLineProductId('')
                    setDocModal('discrepancy_act')
                    setDocModalId(row.id)
                  }
                }}
                data-testid="ff-docs-row"
                data-doc-kind={row.kind}
              >
                <TableCell>{kindRu(row.kind)}</TableCell>
                <TableCell>{row.plannedDate ?? '—'}</TableCell>
                <TableCell>
                  {row.createdAt ? row.createdAt.slice(0, 19).replace('T', ' ') : '—'}
                </TableCell>
                <TableCell>{statusRu(row.status)}</TableCell>
                <TableCell>{row.sellerName ?? '—'}</TableCell>
                <TableCell sx={{ color: 'text.secondary', maxWidth: 200 }}>{row.extraLabel ?? '—'}</TableCell>
                <TableCell align="right">{row.lineCount}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      <Dialog open={docModal !== null && docModalId !== null} onClose={closeDocModal} maxWidth="sm" fullWidth>
        <DialogTitle>{docTitle}</DialogTitle>
        <DialogContent data-testid="ff-supplies-doc-dialog">
          {modalError ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              {modalError}
            </Alert>
          ) : null}
          {modalBusy && !unloadDetail && !divergeDetail ? (
            <Typography variant="body2" color="text.secondary">
              Загрузка…
            </Typography>
          ) : null}
          {unloadDetail ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Склад: {unloadDetail.warehouse_name} · {statusRu(unloadDetail.status)}
            </Typography>
          ) : null}
          {divergeDetail ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {statusRu(divergeDetail.status)}
              {divergeDetail.inbound_intake_request_id
                ? ` · приёмка ${divergeDetail.inbound_intake_request_id.slice(0, 8)}…`
                : ''}
            </Typography>
          ) : null}
          <Table size="small" data-testid="ff-supplies-doc-lines">
            <TableHead>
              <TableRow>
                <TableCell>Артикул</TableCell>
                <TableCell>Товар</TableCell>
                <TableCell>Строка приёмки</TableCell>
                <TableCell align="right">Кол-во</TableCell>
                {draftDoc ? <TableCell align="right" width={56} /> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {(() => {
                const lines = unloadDetail?.lines ?? divergeDetail?.lines ?? []
                const emptySpan = draftDoc ? 5 : 4
                if (lines.length === 0) {
                  return (
                    <TableRow>
                      <TableCell colSpan={emptySpan}>
                        <Typography variant="body2" color="text.secondary">
                          Пока нет строк
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )
                }
                return lines.map((ln) => (
                  <TableRow key={ln.id}>
                    <TableCell>{ln.sku_code}</TableCell>
                    <TableCell>{ln.product_name}</TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {ln.inbound_intake_line_id
                        ? `${ln.inbound_intake_line_id.slice(0, 8)}…`
                        : '—'}
                    </TableCell>
                    <TableCell align="right">{ln.quantity}</TableCell>
                    {draftDoc ? (
                      <TableCell align="right">
                        <Tooltip title="Удалить строку">
                          <IconButton
                            size="small"
                            aria-label="Удалить строку"
                            data-testid={`ff-supplies-line-delete-${ln.id}`}
                            disabled={modalBusy}
                            onClick={(e) => {
                              e.stopPropagation()
                              void deleteDocLine(ln.id)
                            }}
                          >
                            <DeleteOutlineOutlined fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))
              })()}
            </TableBody>
          </Table>
          {draftDoc && productPicklist.length > 0 ? (
            <Stack spacing={1.5} sx={{ mt: 2 }}>
              {docModal === 'discrepancy_act' && inboundRefLines.length > 0 ? (
                <FormControl fullWidth size="small">
                  <InputLabel id="ff-doc-inbound-line">Строка приёмки (опционально)</InputLabel>
                  <Select
                    labelId="ff-doc-inbound-line"
                    label="Строка приёмки (опционально)"
                    value={selectedInboundLineId}
                    onChange={(e) => {
                      const v = String(e.target.value)
                      setSelectedInboundLineId(v)
                      const pick = inboundRefLines.find((x) => x.id === v)
                      setLineProductId(pick ? pick.product_id : '')
                    }}
                    data-testid="ff-supplies-inbound-line"
                  >
                    <MenuItem value="">Без привязки к строке приёмки</MenuItem>
                    {inboundRefLines.map((ln) => (
                      <MenuItem key={ln.id} value={ln.id}>
                        {ln.sku_code} — план {ln.product_name.slice(0, 40)}
                        {ln.product_name.length > 40 ? '…' : ''}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              ) : null}
              <FormControl fullWidth size="small">
                <InputLabel id="ff-doc-line-product">Товар</InputLabel>
                <Select
                  labelId="ff-doc-line-product"
                  label="Товар"
                  value={lineProductId}
                  onChange={(e) => setLineProductId(String(e.target.value))}
                  data-testid="ff-supplies-line-product"
                  disabled={Boolean(selectedInboundLineId)}
                >
                  <MenuItem value="" disabled>
                    Выберите SKU
                  </MenuItem>
                  {productPicklist.map((p) => (
                    <MenuItem key={p.id} value={p.id}>
                      {p.sku_code} — {p.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                size="small"
                label="Количество"
                type="number"
                slotProps={{ htmlInput: { min: 1 } }}
                value={lineQty}
                onChange={(e) => setLineQty(e.target.value)}
                data-testid="ff-supplies-line-qty"
              />
              <Button
                variant="contained"
                disabled={modalBusy || !lineProductId}
                onClick={() => void submitLine()}
                data-testid="ff-supplies-line-add"
              >
                Добавить строку
              </Button>
            </Stack>
          ) : null}
          {draftDoc && productPicklist.length === 0 ? (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Добавьте товары в каталоге, чтобы оформить строки.
            </Typography>
          ) : null}
        </DialogContent>
        <DialogActions>
          {draftDoc ? (
            <Button
              variant="contained"
              color="secondary"
              disabled={modalBusy}
              onClick={() => void submitDoc()}
              data-testid="ff-supplies-doc-submit"
            >
              Утвердить
            </Button>
          ) : null}
          <Button onClick={closeDocModal}>Закрыть</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
