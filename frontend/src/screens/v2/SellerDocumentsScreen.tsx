import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
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
import { SellerMarketplaceUnloadDialog } from '../../components/SellerMarketplaceUnloadDialog'

type DocType = 'inbound' | 'mp_unload' | 'correction'

type InboundSummaryRow = {
  id: string
  status: string
  line_count: number
  planned_delivery_date: string | null
}

type MpUnloadSummaryRow = {
  id: string
  status: string
  line_count: number
  created_at?: string
}

function statusRu(status: string, docType: DocType): string {
  if (docType === 'mp_unload') {
    if (status === 'draft') return 'Черновик'
    if (status === 'submitted') return 'Запланировано'
    if (status === 'confirmed') return 'Подтверждено'
    if (status === 'shipped') return 'Отгружено'
    return status
  }
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Передано на склад'
  if (status === 'primary_accepted') return 'Принято на складе'
  if (status === 'verifying') return 'Проверка на складе'
  if (status === 'verified') return 'Проверено на складе'
  if (status === 'posted') return 'Оприходовано'
  return status
}

type DocumentRow = {
  type: DocType
  id: string
  date: string | null
  status: string
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
  onRefreshMpUnloadList,
}: Props) {
  const navigate = useNavigate()
  const [type, setType] = useState<DocType | 'all'>('all')
  const [sort, setSort] = useState<'date_desc' | 'date_asc'>('date_desc')
  const [mpDialogId, setMpDialogId] = useState<string | null>(null)

  const rows = useMemo(() => {
    const all: DocumentRow[] = [
      ...inboundSummaries.map((r) => ({
        type: 'inbound' as const,
        id: r.id,
        date: r.planned_delivery_date,
        status: r.status,
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
    const filtered = type === 'all' ? all : all.filter((r) => r.type === type)
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
            onClick={() => navigate('/inbound/new')}
            sx={{ alignSelf: { xs: 'stretch', sm: 'auto' } }}
          >
            Создать заявку на поставку
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
              onChange={(e) => setType(e.target.value as DocType | 'all')}
              data-testid="seller-documents-type"
            >
              <MenuItem value="all">Все</MenuItem>
              <MenuItem value="inbound">Поставка</MenuItem>
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
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow
                key={`${r.type}:${r.id}`}
                hover
                data-testid="seller-documents-row"
                data-doc-type={r.type}
                data-doc-id={r.id}
                sx={{
                  cursor: r.type === 'inbound' || r.type === 'mp_unload' ? 'pointer' : 'default',
                }}
                onClick={() => {
                  if (r.type === 'inbound') {
                    navigate(`/inbound/${r.id}`)
                  } else if (r.type === 'mp_unload') {
                    setMpDialogId(r.id)
                  }
                }}
              >
                <TableCell>
                  {r.type === 'inbound'
                    ? 'Поставка'
                    : r.type === 'mp_unload'
                      ? 'Отгрузка на МП'
                      : 'Акт расхождений'}
                </TableCell>
                <TableCell sx={{ color: 'text.secondary' }}>{r.date ?? '—'}</TableCell>
                <TableCell>{statusRu(r.status, r.type)}</TableCell>
                <TableCell align="right">{r.line_count}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4}>
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
