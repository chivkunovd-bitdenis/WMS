import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  LinearProgress,
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
  TableSortLabel,
  TextField,
  Typography,
} from '@mui/material'
import { PageHeader } from '../../ui/PageHeader'
import {
  filterReceptionQueue,
  filterSortingQueue,
  type InboundQueueRow,
} from '../../utils/inboundQueues'
import {
  inboundQueueBoxesLabel,
  inboundQueueDocumentLabel,
  inboundQueueUnitsLabel,
  inboundStatusRu,
  isDoneStatus,
  isReceivingStatus,
  isSortingStatus,
  type InboundSummaryRef,
} from './inboundReceivingHelpers'
import type { InboundOperationType } from '../../utils/inboundOperationType'

export type InboundWorkspace = 'reception' | 'sorting'

type Props = {
  workspace: InboundWorkspace
  rows: InboundQueueRow[]
  onOpen: (id: string) => void
  onCreateDraft?: (operationType: InboundOperationType, sellerId: string) => void | Promise<void>
  creatingDraft?: boolean
  sellers?: { id: string; name: string }[]
  loading?: boolean
  error?: string | null
  onRetry?: () => void | Promise<void>
}

type SortKey = 'date' | 'number'
type SortDirection = 'asc' | 'desc'

function statusColor(
  status: string,
): 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'info' {
  if (status === 'draft') return 'default'
  if (status === 'submitted') return 'info'
  if (isReceivingStatus(status)) return 'warning'
  if (isSortingStatus(status)) return 'secondary'
  if (isDoneStatus(status)) return 'success'
  return 'primary'
}

function sortValue(row: InboundQueueRow, key: SortKey): string {
  if (key === 'date') return row.planned_delivery_date ?? row.created_at ?? ''
  return row.display_number ?? row.document_number ?? row.waybill_number ?? ''
}

// Решение заказчика 17.08.2026: подсветки строки нет вообще (ни заливки, ни полосы слева). Красным
// помечается расхождение по количеству принятых штук (has_discrepancy) — только текст в колонке
// «Состав». Расхождение по числу коробов не подсвечивается.
function rowHasDiscrepancy(row: InboundQueueRow): boolean {
  return row.has_discrepancy === true
}

function compositionSx(row: InboundQueueRow) {
  return rowHasDiscrepancy(row) ? { color: 'error.main' } : undefined
}

function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = value.slice(0, 10)
  const [year, month, day] = date.split('-')
  if (!year || !month || !day) return date
  return `${day}.${month}.${year}`
}

function compositionLabel(row: InboundQueueRow & InboundSummaryRef): string {
  const boxes = inboundQueueBoxesLabel(row)
  return `${boxes} — ${inboundQueueUnitsLabel(row)}`
}

function rowMatchesSearch(row: InboundQueueRow & InboundSummaryRef, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  const haystack = [
    inboundQueueDocumentLabel(row),
    row.document_number,
    row.display_number,
    row.waybill_number,
    row.seller_name,
    ...(row.product_names ?? []),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(normalized)
}

export function FfInboundQueuePage({
  workspace,
  rows,
  onOpen,
  onCreateDraft,
  creatingDraft = false,
  sellers = [],
  loading = false,
  error = null,
  onRetry,
}: Props) {
  const [sellerFilter, setSellerFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('date')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [draftOperationType, setDraftOperationType] = useState<InboundOperationType | null>(null)
  const [draftSellerId, setDraftSellerId] = useState('')

  useEffect(() => {
    if (workspace === 'reception' && onRetry) {
      void onRetry()
    }
    // REC-11: refresh once when the route component enters the screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace])

  useEffect(() => {
    if (draftOperationType != null && !draftSellerId && sellers.length === 1) {
      setDraftSellerId(sellers[0].id)
    }
  }, [draftOperationType, draftSellerId, sellers])

  const baseRows = useMemo(
    () => (workspace === 'reception' ? filterReceptionQueue(rows) : filterSortingQueue(rows)),
    [rows, workspace],
  )
  const statusOptions = useMemo(
    () => Array.from(new Set(baseRows.map((row) => row.status))),
    [baseRows],
  )
  const sellerOptions = useMemo(() => {
    const fromRows = baseRows
      .filter((row) => row.seller_id && row.seller_name)
      .map((row) => ({ id: String(row.seller_id), name: String(row.seller_name) }))
    const byId = new Map<string, { id: string; name: string }>()
    for (const seller of [...sellers, ...fromRows]) byId.set(seller.id, seller)
    return Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }, [baseRows, sellers])
  const filtered = useMemo(
    () =>
      baseRows
        .filter((row) => sellerFilter === 'all' || row.seller_id === sellerFilter)
        .filter((row) => statusFilter === 'all' || row.status === statusFilter)
        .filter((row) => rowMatchesSearch(row as InboundQueueRow & InboundSummaryRef, search))
        .sort((a, b) => {
          const left = sortValue(a, sortKey)
          const right = sortValue(b, sortKey)
          const result = left.localeCompare(right, 'ru', { numeric: true })
          return sortDirection === 'asc' ? result : -result
        }),
    [baseRows, search, sellerFilter, sortDirection, sortKey, statusFilter],
  )
  const newCount = baseRows.filter((row) => row.status === 'submitted').length

  const title = workspace === 'reception' ? 'Приёмка на FF' : 'Сортировка'
  const subtitle =
    workspace === 'reception'
      ? 'Список документов для складской приёмки.'
      : 'Разложение принятого товара по ячейкам хранения. Доступно к резерву только то, что уже разложено.'

  const requestSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(key)
    setSortDirection('desc')
  }

  const openCreateDialog = (operationType: InboundOperationType) => {
    setDraftOperationType(operationType)
    setDraftSellerId(sellerOptions.length === 1 ? sellerOptions[0].id : '')
  }

  const closeCreateDialog = () => {
    setDraftOperationType(null)
    setDraftSellerId('')
  }

  const submitCreateDialog = async () => {
    if (!draftOperationType || !draftSellerId || !onCreateDraft) return
    await onCreateDraft(draftOperationType, draftSellerId)
    closeCreateDialog()
  }

  return (
    <Box data-testid={workspace === 'reception' ? 'ff-reception-page' : 'ff-sorting-page'}>
      <PageHeader title={title} description={subtitle} />

      {workspace === 'reception' && onCreateDraft ? (
        <Stack direction="row" spacing={1} sx={{ mb: 2, justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }} data-testid="ff-inbound-new-count">
            Новые приёмки: {newCount}
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              disabled={creatingDraft}
              onClick={() => openCreateDialog('inbound')}
              data-testid="ff-inbound-create"
            >
              Создать приёмку
            </Button>
            <Button
              variant="contained"
              color="secondary"
              disabled={creatingDraft}
              onClick={() => openCreateDialog('return')}
              data-testid="ff-inbound-create-return"
            >
              Создать возврат
            </Button>
          </Stack>
        </Stack>
      ) : null}

      {workspace === 'reception' ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="ff-inbound-seller-filter-label">Селлер</InputLabel>
            <Select
              labelId="ff-inbound-seller-filter-label"
              label="Селлер"
              value={sellerFilter}
              onChange={(event) => setSellerFilter(String(event.target.value))}
              data-testid="ff-inbound-seller-filter"
            >
              <MenuItem value="all">Все селлеры</MenuItem>
              {sellerOptions.map((seller) => (
                <MenuItem key={seller.id} value={seller.id}>
                  {seller.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel id="ff-inbound-status-filter-label">Статус</InputLabel>
            <Select
              labelId="ff-inbound-status-filter-label"
              label="Статус"
              value={statusFilter}
              onChange={(event) => setStatusFilter(String(event.target.value))}
              data-testid="ff-inbound-status-filter"
            >
              <MenuItem value="all">Все статусы</MenuItem>
              {statusOptions.map((status) => (
                <MenuItem key={status} value={status}>
                  {inboundStatusRu(status)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Поиск"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            slotProps={{ htmlInput: { 'data-testid': 'ff-inbound-search' } }}
            sx={{ minWidth: 260, flex: 1 }}
          />
        </Stack>
      ) : null}

      {error ? (
        <Alert
          severity="error"
          action={
            onRetry ? (
              <Button color="inherit" size="small" onClick={() => void onRetry()} data-testid="ff-inbound-retry">
                Повторить
              </Button>
            ) : undefined
          }
          sx={{ mb: 2 }}
          data-testid="ff-inbound-load-error"
        >
          {error}
        </Alert>
      ) : null}
      {loading ? <LinearProgress sx={{ mb: 2 }} data-testid="ff-inbound-loading" /> : null}

      {workspace === 'reception' && onCreateDraft ? (
        <Dialog open={draftOperationType != null} onClose={closeCreateDialog} data-testid="ff-inbound-create-dialog">
          <DialogTitle>
            {draftOperationType === 'return' ? 'Создать возврат' : 'Создать приёмку'}
          </DialogTitle>
          <DialogContent sx={{ minWidth: 360, pt: 1 }}>
            <FormControl fullWidth size="small" sx={{ mt: 1 }}>
              <InputLabel id="ff-inbound-create-seller-label">Селлер</InputLabel>
              <Select
                labelId="ff-inbound-create-seller-label"
                label="Селлер"
                value={draftSellerId}
                onChange={(event) => setDraftSellerId(String(event.target.value))}
                data-testid="ff-inbound-create-seller"
              >
                {sellerOptions.map((seller) => (
                  <MenuItem key={seller.id} value={seller.id}>
                    {seller.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </DialogContent>
          <DialogActions>
            <Button
              onClick={closeCreateDialog}
              disabled={creatingDraft}
              data-testid="ff-inbound-create-cancel"
            >
              Отмена
            </Button>
            <Button
              variant="contained"
              onClick={() => void submitCreateDialog()}
              disabled={creatingDraft || !draftSellerId}
              data-testid="ff-inbound-create-confirm"
            >
              Создать
            </Button>
          </DialogActions>
        </Dialog>
      ) : null}

      {filtered.length === 0 ? (
        <Alert severity="info" data-testid="ff-inbound-queue-empty">
          {workspace === 'reception'
            ? 'Нет приёмок в очереди.'
            : 'Нет приёмок в сортировке — всё разложено по ячейкам.'}
        </Alert>
      ) : (
        <TableContainer component={Paper} variant="outlined" data-testid="ff-inbound-queue-table">
          <Table size="small">
            <TableHead>
              <TableRow>
                {workspace === 'reception' ? (
                  <>
                    <TableCell>Селлер</TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={sortKey === 'number'}
                        direction={sortKey === 'number' ? sortDirection : 'asc'}
                        onClick={() => requestSort('number')}
                        data-testid="ff-inbound-sort-number"
                      >
                        Номер документа
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={sortKey === 'date'}
                        direction={sortKey === 'date' ? sortDirection : 'asc'}
                        onClick={() => requestSort('date')}
                        data-testid="ff-inbound-sort-date"
                      >
                        Дата
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>Состав</TableCell>
                    <TableCell>Статус</TableCell>
                  </>
                ) : (
                  <>
                    <TableCell>№ документа</TableCell>
                    <TableCell>Селлер</TableCell>
                    <TableCell>Состав</TableCell>
                    <TableCell align="right">Короба</TableCell>
                    <TableCell align="right">Осталось, шт</TableCell>
                    <TableCell>Статус</TableCell>
                  </>
                )}
              </TableRow>
            </TableHead>
            <TableBody>
              {filtered.map((row) => {
                const summary = row as InboundQueueRow & InboundSummaryRef
                return (
                  <TableRow
                    key={row.id}
                    hover
                    tabIndex={0}
                    sx={{
                      cursor: 'pointer',
                      '&:focus-visible': {
                        outline: (theme) => `2px solid ${theme.palette.primary.main}`,
                        outlineOffset: -2,
                      },
                    }}
                    onClick={() => onOpen(row.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        onOpen(row.id)
                      }
                    }}
                    data-testid="ff-inbound-queue-row"
                    data-request-id={row.id}
                    data-row-status={row.status}
                    data-row-discrepancy={rowHasDiscrepancy(row) ? 'yes' : 'no'}
                  >
                    {workspace === 'reception' ? (
                      <>
                        <TableCell data-testid="ff-inbound-queue-seller">{row.seller_name ?? '—'}</TableCell>
                        <TableCell data-testid="ff-inbound-queue-document">
                          <Stack spacing={0.25}>
                            <Typography variant="body2">{inboundQueueDocumentLabel(summary)}</Typography>
                            {summary.waybill_number?.trim() ? (
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                data-testid="ff-inbound-queue-waybill-number"
                              >
                                Накладная: {summary.waybill_number.trim()}
                              </Typography>
                            ) : null}
                          </Stack>
                        </TableCell>
                        <TableCell data-testid="ff-inbound-queue-date">
                          {formatDate(row.planned_delivery_date ?? row.created_at)}
                        </TableCell>
                        <TableCell data-testid="ff-inbound-queue-composition" sx={compositionSx(row)}>
                          {compositionLabel(summary)}
                        </TableCell>
                      </>
                    ) : (
                      <>
                        <TableCell data-testid="ff-inbound-queue-document">
                          <Stack spacing={0.25}>
                            <Typography variant="body2">{inboundQueueDocumentLabel(summary)}</Typography>
                            {summary.waybill_number?.trim() ? (
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                data-testid="ff-inbound-queue-waybill-number"
                              >
                                Накладная: {summary.waybill_number.trim()}
                              </Typography>
                            ) : null}
                          </Stack>
                        </TableCell>
                        <TableCell data-testid="ff-inbound-queue-seller">{row.seller_name ?? '—'}</TableCell>
                        <TableCell data-testid="ff-inbound-queue-composition">
                          {row.line_count} поз. · {inboundQueueUnitsLabel(summary)}
                        </TableCell>
                        <TableCell align="right" data-testid="ff-inbound-queue-boxes">
                          {inboundQueueBoxesLabel(summary)}
                        </TableCell>
                        <TableCell align="right" data-testid="ff-inbound-queue-sorting-qty">
                          {row.sorting_remaining_qty ?? 0}
                        </TableCell>
                      </>
                    )}
                    <TableCell>
                      <Chip
                        size="small"
                        label={inboundStatusRu(row.status)}
                        color={statusColor(row.status)}
                        data-testid="ff-inbound-queue-status"
                      />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {workspace === 'sorting' ? (
        <Stack sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Зона «Сортировка» — служебный буфер принятого товара до раскладки; как обычную полку хранения её не выбирают.
          </Typography>
        </Stack>
      ) : null}
    </Box>
  )
}
