import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Drawer,
  Link,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type ReprintRequest = {
  id: string
  code_id: string
  status: string
  reason: string | null
  created_at: string
  requested_by_email: string
  product_name: string
  product_sku: string
  cis_masked: string
  document_number: string | null
  packaging_task_id: string
  pool_id: string | null
}

type CodeHistoryEvent = {
  id: string
  created_at: string
  event_type: string
  document_number: string | null
  actor_email: string | null
}

type Props = {
  token: string
  testId?: string
}

const APPROVE_REPRINT_HINT =
  'Разрешить повторную печать того же кода маркировки (КМ). Код в системе не меняется, в журнале — событие «перепечатка». Выбирайте, если этикетка испорчена при печати, а сам КМ ещё годен.'

const REPLACE_REPRINT_HINT =
  'Списать текущий КМ как брак и выдать новый из пула. Старый код станет «заменён», остаток пула уменьшится на 1. Выбирайте, если КМ повреждён или не годится к нанесению.'

export function FfHonestSignReprintsPage({
  token,
  testId = 'ff-honest-sign-reprints-page',
}: Props) {
  const [rows, setRows] = useState<ReprintRequest[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [rejectTargetId, setRejectTargetId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [historyCodeId, setHistoryCodeId] = useState<string | null>(null)
  const [historyCisMasked, setHistoryCisMasked] = useState<string | null>(null)
  const [history, setHistory] = useState<CodeHistoryEvent[]>([])
  const [historyBusy, setHistoryBusy] = useState(false)

  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/operations/marking-codes/reprint-requests'), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        setRows([])
        return
      }
      const body = (await res.json()) as { requests: ReprintRequest[] }
      setRows(body.requests)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  const closeRejectDialog = () => {
    if (busyId) {
      return
    }
    setRejectTargetId(null)
    setRejectReason('')
  }

  const openCodeHistory = async (codeId: string, cisMasked: string) => {
    setHistoryCodeId(codeId)
    setHistoryCisMasked(cisMasked)
    setHistory([])
    setHistoryBusy(true)
    try {
      const res = await fetch(apiUrl(`/operations/marking-codes/codes/${codeId}/history`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        setHistory((await res.json()) as CodeHistoryEvent[])
      }
    } finally {
      setHistoryBusy(false)
    }
  }

  const closeCodeHistory = () => {
    setHistoryCodeId(null)
    setHistoryCisMasked(null)
    setHistory([])
  }

  const resolveRequest = async (
    requestId: string,
    action: 'replace' | 'approve-reprint' | 'reject',
    reason?: string,
  ) => {
    setBusyId(requestId)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marking-codes/reprint-requests/${requestId}/${action}`),
        {
          method: 'POST',
          headers: authHeaders,
          body:
            action === 'reject'
              ? JSON.stringify({ reason: reason?.trim() || null })
              : undefined,
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      if (action === 'reject') {
        setRejectTargetId(null)
        setRejectReason('')
      }
      await load()
    } finally {
      setBusyId(null)
    }
  }

  const confirmReject = async () => {
    const trimmed = rejectReason.trim()
    if (!rejectTargetId || !trimmed) {
      return
    }
    await resolveRequest(rejectTargetId, 'reject', trimmed)
  }

  return (
    <Box data-testid={testId}>
      <Typography variant="h5" gutterBottom>
        Перепечатки ЧЗ
      </Typography>
      <Alert
        severity="info"
        icon={<InfoOutlinedIcon fontSize="inherit" />}
        sx={{ mb: 2 }}
        data-testid={`${testId}-actions-help`}
      >
        <Typography variant="body2" component="span" sx={{ display: 'block', mb: 0.5 }}>
          <strong>Подтвердить</strong> — {APPROVE_REPRINT_HINT}
        </Typography>
        <Typography variant="body2" component="span" sx={{ display: 'block' }}>
          <strong>Заменить</strong> — {REPLACE_REPRINT_HINT}
        </Typography>
      </Alert>
      {error ? (
        <Typography color="error" data-testid={`${testId}-error`}>
          {error}
        </Typography>
      ) : null}
      {loading ? (
        <Typography variant="body2" color="text.secondary">
          Загрузка…
        </Typography>
      ) : rows.length < 1 ? (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="body2" color="text.secondary" data-testid={`${testId}-empty`}>
            Нет ожидающих запросов на перепечатку.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined" data-testid={`${testId}-table`}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Время</TableCell>
                <TableCell>Кто</TableCell>
                <TableCell>Товар</TableCell>
                <TableCell>Код</TableCell>
                <TableCell>Причина</TableCell>
                <TableCell>Документ</TableCell>
                <TableCell>Контекст</TableCell>
                <TableCell align="right">Действия</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id} data-testid={`${testId}-row-${row.id}`}>
                  <TableCell>{new Date(row.created_at).toLocaleString('ru-RU')}</TableCell>
                  <TableCell>{row.requested_by_email}</TableCell>
                  <TableCell>
                    {row.product_name} ({row.product_sku})
                  </TableCell>
                  <TableCell>{row.cis_masked}</TableCell>
                  <TableCell>{row.reason?.trim() || '—'}</TableCell>
                  <TableCell>{row.document_number ?? '—'}</TableCell>
                  <TableCell data-testid={`${testId}-context-${row.id}`}>
                    <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                      <Link
                        component={RouterLink}
                        to="/app/ff/packaging"
                        state={{ taskId: row.packaging_task_id }}
                        variant="body2"
                        data-testid={`${testId}-context-task-${row.id}`}
                      >
                        Задание
                      </Link>
                      {row.pool_id ? (
                        <Link
                          component={RouterLink}
                          to={`/app/ff/honest-sign/pool/${row.pool_id}`}
                          variant="body2"
                          data-testid={`${testId}-context-pool-${row.id}`}
                        >
                          Пул
                        </Link>
                      ) : null}
                      <Link
                        component="button"
                        type="button"
                        variant="body2"
                        onClick={() => void openCodeHistory(row.code_id, row.cis_masked)}
                        sx={{ verticalAlign: 'baseline' }}
                        data-testid={`${testId}-context-history-${row.id}`}
                      >
                        История кода
                      </Link>
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} sx={{ justifyContent: 'flex-end' }}>
                      <Tooltip title={APPROVE_REPRINT_HINT} arrow placement="top">
                        <span>
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={busyId === row.id}
                            onClick={() => void resolveRequest(row.id, 'approve-reprint')}
                            data-testid={`${testId}-approve-${row.id}`}
                            aria-label={`Подтвердить: ${APPROVE_REPRINT_HINT}`}
                          >
                            Подтвердить
                          </Button>
                        </span>
                      </Tooltip>
                      <Tooltip title={REPLACE_REPRINT_HINT} arrow placement="top">
                        <span>
                          <Button
                            size="small"
                            variant="contained"
                            disabled={busyId === row.id}
                            onClick={() => void resolveRequest(row.id, 'replace')}
                            data-testid={`${testId}-replace-${row.id}`}
                            aria-label={`Заменить: ${REPLACE_REPRINT_HINT}`}
                          >
                            Заменить
                          </Button>
                        </span>
                      </Tooltip>
                      <Button
                        size="small"
                        color="inherit"
                        disabled={busyId === row.id}
                        onClick={() => {
                          setRejectTargetId(row.id)
                          setRejectReason('')
                        }}
                        data-testid={`${testId}-reject-${row.id}`}
                      >
                        Отклонить
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <Dialog
        open={rejectTargetId !== null}
        onClose={closeRejectDialog}
        maxWidth="sm"
        fullWidth
        data-testid={`${testId}-reject-dialog`}
      >
        <DialogTitle>Отклонить запрос на перепечатку</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            multiline
            minRows={2}
            label="Причина отклонения"
            placeholder="Укажите, почему запрос отклонён — это увидит заявитель"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            disabled={busyId !== null}
            slotProps={{ htmlInput: { maxLength: 512 } }}
            helperText="Обязательное поле"
            sx={{ mt: 0.5 }}
            data-testid={`${testId}-reject-reason`}
          />
        </DialogContent>
        <DialogActions>
          <Button
            onClick={closeRejectDialog}
            disabled={busyId !== null}
            data-testid={`${testId}-reject-cancel`}
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={busyId !== null || rejectReason.trim().length < 1}
            onClick={() => void confirmReject()}
            data-testid={`${testId}-reject-confirm`}
          >
            Отклонить
          </Button>
        </DialogActions>
      </Dialog>
      <Drawer
        anchor="right"
        open={historyCodeId != null}
        onClose={closeCodeHistory}
        data-testid={`${testId}-history-drawer`}
      >
        <Box sx={{ width: 360, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 0.5 }}>
            История кода
          </Typography>
          {historyCisMasked ? (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {historyCisMasked}
            </Typography>
          ) : null}
          {historyBusy ? (
            <Skeleton height={80} />
          ) : history.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Событий пока нет.
            </Typography>
          ) : (
            <Stack spacing={1.5}>
              {history.map((ev) => (
                <Paper key={ev.id} variant="outlined" sx={{ p: 1.5 }}>
                  <Typography variant="subtitle2">{ev.event_type}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(ev.created_at).toLocaleString('ru-RU')}
                  </Typography>
                  {ev.document_number ? (
                    <Typography variant="body2">Документ: {ev.document_number}</Typography>
                  ) : null}
                  {ev.actor_email ? (
                    <Typography variant="body2">{ev.actor_email}</Typography>
                  ) : null}
                </Paper>
              ))}
            </Stack>
          )}
        </Box>
      </Drawer>
    </Box>
  )
}
