import { useMemo } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
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
  type InboundSummaryRef,
} from './inboundReceivingHelpers'

export type InboundWorkspace = 'reception' | 'sorting'

type Props = {
  workspace: InboundWorkspace
  rows: InboundQueueRow[]
  onOpen: (id: string) => void
  onCreateDraft?: () => void | Promise<void>
  creatingDraft?: boolean
}

function statusLabel(status: string, workspace: InboundWorkspace): string {
  if (workspace === 'sorting' && (status === 'verified' || status === 'sorting')) return 'В сортировке'
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Передано'
  if (status === 'primary_accepted') return 'Принято первично'
  if (status === 'verifying') return 'Пересчёт'
  if (status === 'receiving') return 'В работе'
  if (status === 'done') return 'Проведён'
  return status
}

function statusColor(status: string): 'default' | 'info' | 'success' | 'warning' {
  if (status === 'done') return 'success'
  if (status === 'sorting' || status === 'verified') return 'warning'
  if (status === 'receiving' || status === 'primary_accepted' || status === 'verifying') return 'info'
  return 'default'
}

export function FfInboundQueuePage({
  workspace,
  rows,
  onOpen,
  onCreateDraft,
  creatingDraft = false,
}: Props) {
  const filtered = useMemo(
    () => (workspace === 'reception' ? filterReceptionQueue(rows) : filterSortingQueue(rows)),
    [rows, workspace],
  )

  const title = workspace === 'reception' ? 'Приёмка' : 'Сортировка'
  const subtitle =
    workspace === 'reception'
      ? 'Приёмки до завершения поштучного пересчёта. После «Завершить пересчёт» заявка уходит в сортировку, остаток появляется у ФФ.'
      : 'Разложение принятого товара по ячейкам хранения. Доступно к резерву только то, что уже разложено.'

  return (
    <Box data-testid={workspace === 'reception' ? 'ff-reception-page' : 'ff-sorting-page'}>
      <PageHeader title={title} description={subtitle} />

      {workspace === 'reception' && onCreateDraft ? (
        <Stack direction="row" sx={{ mb: 2, justifyContent: 'flex-end' }}>
          <Button
            variant="contained"
            disabled={creatingDraft}
            onClick={() => void onCreateDraft()}
            data-testid="ff-inbound-create"
          >
            Создать приёмку
          </Button>
        </Stack>
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
                <TableCell>№ документа</TableCell>
                <TableCell>Селлер</TableCell>
                <TableCell>Состав</TableCell>
                <TableCell align="right">Короба</TableCell>
                {workspace === 'sorting' ? (
                  <TableCell align="right">Осталось, шт</TableCell>
                ) : null}
                <TableCell>Статус</TableCell>
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
                  >
                    <TableCell data-testid="ff-inbound-queue-document">
                      {inboundQueueDocumentLabel(summary)}
                    </TableCell>
                    <TableCell>{row.seller_name ?? '—'}</TableCell>
                    <TableCell data-testid="ff-inbound-queue-composition">
                      {row.line_count} поз. · {inboundQueueUnitsLabel(summary)}
                    </TableCell>
                    <TableCell align="right" data-testid="ff-inbound-queue-boxes">
                      {inboundQueueBoxesLabel(summary)}
                    </TableCell>
                    {workspace === 'sorting' ? (
                      <TableCell align="right" data-testid="ff-inbound-queue-sorting-qty">
                        {row.sorting_remaining_qty ?? 0}
                      </TableCell>
                    ) : null}
                    <TableCell>
                      <Chip
                        size="small"
                        label={statusLabel(row.status, workspace)}
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
