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
  ToggleButton,
  ToggleButtonGroup,
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
  status: string
  operation_type?: string | null
  line_count: number
  planned_delivery_date: string | null
}

type MpUnloadSummaryRow = {
  id: string
  status: string
  line_count: number
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
  status: string
  operation_type?: InboundOperationType
  line_count: number
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
  const [createOperationType, setCreateOperationType] = useState<InboundOperationType>('inbound')
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
        status: r.status,
        operation_type: normalizeInboundOperationType(r.operation_type),
        line_count: r.line_count,
      })),
      ...mpUnloadSummaries.map((r) => ({
        type: 'mp_unload' as const,
        id: r.id,
        date: r.created_at?.slice(0, 10) ?? null,
        status: r.status,
        line_count: r.line_count,
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
          <ToggleButtonGroup
            exclusive
            size="small"
            value={createOperationType}
            onChange={(_event, next: InboundOperationType | null) => {
              if (next) {
                setCreateOperationType(next)
              }
            }}
            aria-label="Тип заявки"
            data-testid="seller-inbound-operation-toggle"
            sx={{ alignSelf: { xs: 'stretch', sm: 'auto' } }}
          >
            <ToggleButton
              value="inbound"
              disabled={busy}
              data-testid="seller-inbound-operation-supply"
            >
              Поставка
            </ToggleButton>
            <ToggleButton
              value="return"
              disabled={busy}
              data-testid="seller-inbound-operation-return"
            >
              Возврат
            </ToggleButton>
          </ToggleButtonGroup>
          <Button
            variant="contained"
            data-testid="seller-create-inbound"
            disabled={busy}
            onClick={() => navigate(`../inbound/new?operation=${createOperationType}`)}
            sx={{ alignSelf: { xs: 'stretch', sm: 'auto' } }}
          >
            {createOperationType === 'return' ? 'Создать возврат' : 'Создать заявку на поставку'}
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
                  if (r.type === 'inbound') {
                    navigate(`../inbound/${r.id}`)
                  } else if (r.type === 'mp_unload') {
                    setMpDialogId(r.id)
                  }
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
                <TableCell colSpan={5}>
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
