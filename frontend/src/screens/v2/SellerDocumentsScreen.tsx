import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
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
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { SellerMarketplaceUnloadDialog } from '../../components/SellerMarketplaceUnloadDialog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import {
  inboundOperationTypeLabel,
  normalizeInboundOperationType,
  type InboundOperationType,
} from '../../utils/inboundOperationType'

type DocType = 'inbound' | 'mp_unload' | 'correction'
type DocumentFilterType = DocType | 'return' | 'all'
const UNKNOWN_DOCUMENT_STATUS_LABEL = 'Статус уточняется'

type InboundSummaryRow = {
  id: string
  waybill_number?: string | null
  warehouse_id: string
  warehouse_name?: string | null
  status: string
  operation_type?: string | null
  line_count: number
  goods_qty_total?: number
  planned_delivery_date: string | null
  planned_box_count?: number | null
}

type MpUnloadSummaryRow = {
  id: string
  warehouse_id?: string
  warehouse_name?: string | null
  status: string
  line_count: number
  goods_qty_total?: number
  planned_shipment_date?: string | null
  created_at?: string
}

export function sellerDocumentStatusRu(status: string, docType: DocType): string {
  if (docType === 'mp_unload') {
    if (status === 'draft') return 'Черновик'
    if (status === 'submitted') return 'Запланировано'
    if (status === 'confirmed') return 'Подтверждено'
    if (status === 'collecting') return 'На сборке'
    if (status === 'shipped') return 'Отгружено'
    if (status === 'cancelled') return 'Отменено'
    return UNKNOWN_DOCUMENT_STATUS_LABEL
  }
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Передано на склад'
  if (status === 'receiving') return 'Принимается на складе'
  if (status === 'sorting') return 'В сортировке'
  if (status === 'done') return 'Проведено'
  if (status === 'primary_accepted') return 'Принято на складе'
  if (status === 'verifying') return 'Проверка на складе'
  if (status === 'verified') return 'Проверено на складе'
  if (status === 'posted') return 'Оприходовано'
  return UNKNOWN_DOCUMENT_STATUS_LABEL
}

type DocumentRow = {
  type: DocType
  id: string
  date: string | null
  waybill_number?: string | null
  warehouse_name?: string | null
  status: string
  operation_type?: InboundOperationType
  line_count: number
  goods_qty_total: number
}

type CalendarRow = DocumentRow & {
  label: string
}

type Props = {
  busy: boolean
  error: string | null
  token: string | null
  catalogScopeKey?: string
  authHeaders: (t: string) => Record<string, string>
  warehouseId: string | null
  inboundSummaries: InboundSummaryRow[]
  mpUnloadSummaries: MpUnloadSummaryRow[]
  onCreateCorrection: () => void
  onCreateMpUnload: () => Promise<string | null>
  onRefreshInboundList: () => Promise<void>
  onRefreshMpUnloadList: () => Promise<void>
}

export function SellerDocumentsScreen({
  busy,
  error,
  token,
  catalogScopeKey = '',
  authHeaders,
  warehouseId,
  inboundSummaries,
  mpUnloadSummaries,
  onCreateCorrection,
  onCreateMpUnload,
  onRefreshInboundList,
  onRefreshMpUnloadList,
}: Props) {
  const navigate = useNavigate()
  const [type, setType] = useState<DocumentFilterType>('all')
  const [sort, setSort] = useState<'date_desc' | 'date_asc'>('date_desc')
  const [mpDialogId, setMpDialogId] = useState<string | null>(null)
  const [deleteBusyKey, setDeleteBusyKey] = useState<string | null>(null)
  const [deleteConfirmRow, setDeleteConfirmRow] = useState<DocumentRow | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteOk, setDeleteOk] = useState<string | null>(null)

  const rows = useMemo(() => {
    const all: DocumentRow[] = [
      ...inboundSummaries.map((r) => ({
        type: 'inbound' as const,
        id: r.id,
        date: r.planned_delivery_date,
        waybill_number: r.waybill_number ?? null,
        warehouse_name: r.warehouse_name ?? null,
        status: r.status,
        operation_type: normalizeInboundOperationType(r.operation_type),
        line_count: r.line_count,
        goods_qty_total: r.goods_qty_total ?? 0,
      })),
      ...mpUnloadSummaries.map((r) => ({
        type: 'mp_unload' as const,
        id: r.id,
        date: r.planned_shipment_date ?? r.created_at?.slice(0, 10) ?? null,
        warehouse_name: r.warehouse_name ?? null,
        status: r.status,
        line_count: r.line_count,
        goods_qty_total: r.goods_qty_total ?? 0,
      })),
    ]
    const filtered =
      type === 'all'
        ? all
        : type === 'inbound' || type === 'return'
          ? all.filter((r) => r.type === 'inbound' && r.operation_type === type)
          : all.filter((r) => r.type === type)
    const sign = sort === 'date_desc' ? -1 : 1
    return filtered.sort((a, b) => {
      const ad = a.date ?? ''
      const bd = b.date ?? ''
      if (ad === bd) {
        return a.id.localeCompare(b.id)
      }
      return ad.localeCompare(bd) * sign
    })
  }, [inboundSummaries, mpUnloadSummaries, sort, type])

  const shipmentCalendar = useMemo(() => {
    const today = new Date()
    const todayIso = today.toISOString().slice(0, 10)
    const tomorrow = new Date(today)
    tomorrow.setDate(today.getDate() + 1)
    const tomorrowIso = tomorrow.toISOString().slice(0, 10)
    const sourceRows: CalendarRow[] = [
      ...inboundSummaries.map((r) => ({
        type: 'inbound' as const,
        id: r.id,
        date: r.planned_delivery_date,
        waybill_number: r.waybill_number ?? null,
        warehouse_name: r.warehouse_name ?? null,
        status: r.status,
        operation_type: normalizeInboundOperationType(r.operation_type),
        line_count: r.line_count,
        goods_qty_total: r.goods_qty_total ?? 0,
        label: inboundOperationTypeLabel(normalizeInboundOperationType(r.operation_type)),
      })),
      ...mpUnloadSummaries.map((r) => ({
        type: 'mp_unload' as const,
        id: r.id,
        date: r.planned_shipment_date ?? null,
        warehouse_name: r.warehouse_name ?? null,
        status: r.status,
        line_count: r.line_count,
        goods_qty_total: r.goods_qty_total ?? 0,
        label: 'Отгрузка на МП',
      })),
    ]
    const byDate = (iso: string) =>
      sourceRows
        .filter((row) => row.date === iso)
        .sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id))
    return {
      today: byDate(todayIso),
      tomorrow: byDate(tomorrowIso),
    }
  }, [inboundSummaries, mpUnloadSummaries])

  function openDocument(row: DocumentRow): void {
    if (row.type === 'inbound') {
      navigate(`../inbound/${row.id}`)
    } else if (row.type === 'mp_unload') {
      setMpDialogId(row.id)
    }
  }

  function renderCalendarColumn(title: string, items: CalendarRow[]) {
    return (
      <Box sx={{ flex: '1 1 280px', minWidth: 0 }} data-testid={`seller-shipments-${title === 'Сегодня' ? 'today' : 'tomorrow'}`}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          {title}
        </Typography>
        {items.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Нет документов с плановой датой.
          </Typography>
        ) : (
          <Stack spacing={0.75}>
            {items.map((item) => (
              <Button
                key={`${item.type}:${item.id}`}
                variant="outlined"
                color="inherit"
                onClick={() => openDocument(item)}
                data-testid="seller-shipments-row"
                sx={{
                  justifyContent: 'space-between',
                  gap: 1,
                  textAlign: 'left',
                  textTransform: 'none',
                  alignItems: 'flex-start',
                }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                    {item.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                    {item.warehouse_name ?? 'Склад ФФ'} · {item.line_count} строк · {item.goods_qty_total} шт
                  </Typography>
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ flex: '0 0 auto' }}>
                  {sellerDocumentStatusRu(item.status, item.type)}
                </Typography>
              </Button>
            ))}
          </Stack>
        )}
      </Box>
    )
  }

  async function deleteDraftDocument(row: DocumentRow): Promise<void> {
    if (!token || row.status !== 'draft') {
      return
    }
    const key = `${row.type}:${row.id}`
    const path =
      row.type === 'inbound'
        ? `/operations/inbound-intake-requests/${row.id}`
        : row.type === 'mp_unload'
          ? `/operations/marketplace-unload-requests/${row.id}`
          : null
    if (!path) {
      return
    }
    setDeleteBusyKey(key)
    setDeleteError(null)
    setDeleteOk(null)
    try {
      const res = await fetch(apiUrl(path), {
        method: 'DELETE',
        headers: authHeaders(token),
      })
      if (!res.ok) {
        setDeleteError(await readApiErrorMessage(res))
        return
      }
      if (row.type === 'inbound') {
        await onRefreshInboundList()
      } else {
        await onRefreshMpUnloadList()
      }
      setDeleteOk('Черновик удалён.')
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'Не удалось удалить черновик.')
    } finally {
      setDeleteBusyKey(null)
    }
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Документы
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Поставки на ФФ и отгрузки на маркетплейс
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-documents-error">
          {error}
        </Alert>
      ) : null}
      {deleteError ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-documents-delete-error">
          {deleteError}
        </Alert>
      ) : null}
      {deleteOk ? (
        <Alert severity="success" sx={{ mb: 2 }} data-testid="seller-documents-delete-ok">
          {deleteOk}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-documents-actions">
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1.5}
          sx={{ alignItems: { xs: 'stretch', sm: 'center' } }}
        >
          <Button
            variant="outlined"
            color="secondary"
            data-testid="seller-create-correction"
            disabled={busy}
            onClick={onCreateCorrection}
            sx={{ alignSelf: { xs: 'stretch', sm: 'auto' } }}
          >
            Создать акт расхождений
          </Button>
          <Button
            variant="contained"
            data-testid="seller-create-inbound"
            disabled={busy}
            onClick={() => navigate('../inbound/new?operation=inbound')}
            sx={{ alignSelf: { xs: 'stretch', sm: 'auto' } }}
          >
            Создать заявку на поставку
          </Button>
          <Button
            variant="contained"
            data-testid="seller-create-return"
            disabled={busy}
            onClick={() => navigate('../inbound/new?operation=return')}
            sx={{ alignSelf: { xs: 'stretch', sm: 'auto' } }}
          >
            Создать заявку на возврат
          </Button>
          <Button
            variant="contained"
            color="secondary"
            data-testid="seller-create-mp-unload"
            disabled={busy || !warehouseId}
            onClick={() => {
              void (async () => {
                const id = await onCreateMpUnload()
                if (id) {
                  setMpDialogId(id)
                }
              })()
            }}
            sx={{ alignSelf: { xs: 'stretch', sm: 'auto' } }}
          >
            Создать отгрузку на МП
          </Button>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-shipments-calendar">
        <Stack spacing={1.5}>
          <Box>
            <Typography variant="subtitle1">Сегодня / Завтра</Typography>
            <Typography variant="body2" color="text.secondary">
              По плановой дате документов селлера. Отсечка рейса не настроена.
            </Typography>
          </Box>
          {shipmentCalendar.today.length === 0 && shipmentCalendar.tomorrow.length === 0 ? (
            <Alert severity="info" data-testid="seller-shipments-empty">
              На сегодня и завтра нет документов с плановой датой. Календарь рейсов фулфилмента не настроен.
            </Alert>
          ) : (
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              {renderCalendarColumn('Сегодня', shipmentCalendar.today)}
              {renderCalendarColumn('Завтра', shipmentCalendar.tomorrow)}
            </Stack>
          )}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="seller-documents-filters">
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <FormControl sx={{ minWidth: 220 }}>
            <InputLabel id="seller-documents-type-label">Тип документа</InputLabel>
            <Select
              labelId="seller-documents-type-label"
              label="Тип документа"
              value={type}
              onChange={(e) => setType(e.target.value as DocumentFilterType)}
              data-testid="seller-documents-type"
            >
              <MenuItem value="all">Все</MenuItem>
              <MenuItem value="inbound">Поставка</MenuItem>
              <MenuItem value="return">Возврат</MenuItem>
              <MenuItem value="mp_unload">Отгрузка на МП</MenuItem>
              <MenuItem value="correction">Акт расхождений</MenuItem>
            </Select>
          </FormControl>
          <FormControl sx={{ minWidth: 240 }}>
            <InputLabel id="seller-documents-sort-label">Сортировка</InputLabel>
            <Select
              labelId="seller-documents-sort-label"
              label="Сортировка"
              value={sort}
              onChange={(e) => setSort(e.target.value as 'date_desc' | 'date_asc')}
              data-testid="seller-documents-sort"
            >
              <MenuItem value="date_desc">Дата (новые сверху)</MenuItem>
              <MenuItem value="date_asc">Дата (старые сверху)</MenuItem>
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      <TableContainer component={Paper} variant="outlined" data-testid="seller-documents-list">
        <Table size="small" data-testid="seller-documents-table">
          <TableHead>
            <TableRow>
              <TableCell>Тип</TableCell>
              <TableCell>Дата</TableCell>
              <TableCell>Накладная</TableCell>
              <TableCell>Статус</TableCell>
              <TableCell align="right">Строк</TableCell>
              <TableCell align="right">Действия</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow
                key={`${r.type}:${r.id}`}
                hover
                data-testid="seller-documents-row"
                data-doc-type={r.type}
                data-doc-operation-type={r.operation_type ?? ''}
                data-doc-id={r.id}
                sx={{
                  cursor: r.type === 'inbound' || r.type === 'mp_unload' ? 'pointer' : 'default',
                }}
                onClick={() => {
                  openDocument(r)
                }}
              >
                <TableCell>
                  {r.type === 'inbound'
                    ? inboundOperationTypeLabel(r.operation_type)
                    : r.type === 'mp_unload'
                      ? 'Отгрузка на МП'
                      : 'Акт расхождений'}
                </TableCell>
                <TableCell sx={{ color: 'text.secondary' }}>{r.date ?? '—'}</TableCell>
                <TableCell sx={{ color: r.waybill_number ? 'text.primary' : 'text.secondary' }}>
                  {r.waybill_number ?? '—'}
                </TableCell>
                <TableCell>{sellerDocumentStatusRu(r.status, r.type)}</TableCell>
                <TableCell align="right">{r.line_count}</TableCell>
                <TableCell align="right">
                  {r.status === 'draft' && (r.type === 'inbound' || r.type === 'mp_unload') ? (
                    <Button
                      size="small"
                      variant="outlined"
                      color="error"
                      disabled={deleteBusyKey === `${r.type}:${r.id}`}
                      data-testid="seller-delete-draft"
                      onClick={(e) => {
                        e.stopPropagation()
                        setDeleteError(null)
                        setDeleteOk(null)
                        setDeleteConfirmRow(r)
                      }}
                    >
                      Удалить
                    </Button>
                  ) : (
                    <Typography variant="body2" color="text.disabled">
                      —
                    </Typography>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary">
                    Пока нет документов.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>

      {token ? (
        <Dialog
          open={deleteConfirmRow !== null}
          onClose={() => setDeleteConfirmRow(null)}
          data-testid="seller-delete-draft-confirm-dialog"
        >
          <DialogTitle>Удалить черновик?</DialogTitle>
          <DialogContent>
            <DialogContentText>
              Черновик исчезнет из списка. Документы в работе остаются в истории.
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button
              onClick={() => setDeleteConfirmRow(null)}
              data-testid="seller-delete-draft-cancel"
            >
              Отмена
            </Button>
            <Button
              color="error"
              variant="contained"
              onClick={() => {
                const row = deleteConfirmRow
                if (!row) {
                  return
                }
                setDeleteConfirmRow(null)
                void deleteDraftDocument(row)
              }}
              data-testid="seller-delete-draft-confirm"
            >
              Удалить
            </Button>
          </DialogActions>
        </Dialog>
      ) : null}

      {token ? (
        <SellerMarketplaceUnloadDialog
          open={mpDialogId !== null}
          requestId={mpDialogId}
          token={token}
          catalogScopeKey={catalogScopeKey}
          authHeaders={authHeaders}
          warehouseId={warehouseId}
          busy={busy}
          onClose={() => setMpDialogId(null)}
          onRefreshList={onRefreshMpUnloadList}
        />
      ) : null}
    </Box>
  )
}
