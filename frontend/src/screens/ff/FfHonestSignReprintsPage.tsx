import { useCallback, useEffect, useState } from 'react'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
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

  const resolveRequest = async (requestId: string, action: 'replace' | 'approve-reprint' | 'reject') => {
    setBusyId(requestId)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marking-codes/reprint-requests/${requestId}/${action}`),
        {
          method: 'POST',
          headers: authHeaders,
          body: action === 'reject' ? JSON.stringify({ reason: 'Отклонено старшим' }) : undefined,
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      await load()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Box data-testid={testId}>
      <Typography variant="h5" gutterBottom>
        Перепечатка КМ
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
                <TableCell>КМ</TableCell>
                <TableCell>Причина</TableCell>
                <TableCell>Документ</TableCell>
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
                        onClick={() => void resolveRequest(row.id, 'reject')}
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
    </Box>
  )
}
