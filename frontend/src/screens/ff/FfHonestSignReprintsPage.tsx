import { useCallback, useEffect, useState } from 'react'
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
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

export function FfHonestSignReprintsPage({
  token,
  testId = 'ff-honest-sign-reprints-page',
}: Props) {
  const [rows, setRows] = useState<ReprintRequest[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

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

  return (
    <Box data-testid={testId}>
      <Typography variant="h5" gutterBottom>
        Перепечатки ЧЗ
      </Typography>
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
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}
