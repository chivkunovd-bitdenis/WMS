import { useCallback, useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert,
  Badge,
  Box,
  Button,
  Chip,
  Link,
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
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { useMarkingCodePrint } from '../../utils/useMarkingCodePrint'

type PendingRow = {
  packaging_task_id: string
  packaging_task_line_id: string
  document_number: string | null
  product_id: string
  sku_code: string
  product_name: string
  storage_location_code: string
  qty_need: number
  qty_marking_printed: number
  qty_remaining: number
  marking_available_count: number
}

type Props = {
  token: string
}

export function FfPendingMarkingPage({ token }: Props) {
  const [rows, setRows] = useState<PendingRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const { openPrint, dialog: markingPrintDialog } = useMarkingCodePrint()

  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/operations/marking-codes/pending-marking'), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        setRows([])
        return
      }
      const body = (await res.json()) as { rows: PendingRow[] }
      setRows(body.rows)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <Box data-testid="ff-pending-marking-page">
      <PageHeader
        title="Осталось промаркировать"
        description="Строки заданий на упаковку, где ЧЗ ещё не напечатаны полностью."
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/app/ff/packaging" variant="body2" data-testid="ff-pending-marking-back">
          ← К упаковке
        </Link>
        <Chip
          size="small"
          label={`${rows.length} строк`}
          data-testid="ff-pending-marking-count"
        />
      </Stack>
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}
      {loading ? (
        <Typography variant="body2" color="text.secondary">
          Загрузка…
        </Typography>
      ) : rows.length < 1 ? (
        <Paper variant="outlined" sx={{ p: 3 }} data-testid="ff-pending-marking-empty">
          <Typography variant="body2" color="text.secondary">
            Все строки с ЧЗ промаркированы.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined" data-testid="ff-pending-marking-table">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Документ</TableCell>
                <TableCell>Товар</TableCell>
                <TableCell>Ячейка</TableCell>
                <TableCell align="right">Осталось</TableCell>
                <TableCell align="right">Доступно в пуле</TableCell>
                <TableCell align="right">Действия</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.packaging_task_line_id} data-testid="ff-pending-marking-row">
                  <TableCell>{row.document_number ?? '—'}</TableCell>
                  <TableCell>
                    {row.product_name}
                    <Typography variant="caption" sx={{ display: 'block' }} color="text.secondary">
                      {row.sku_code}
                    </Typography>
                  </TableCell>
                  <TableCell>{row.storage_location_code}</TableCell>
                  <TableCell align="right">
                    <Badge
                      badgeContent={row.qty_remaining}
                      color="warning"
                      data-testid={`ff-pending-marking-badge-${row.packaging_task_line_id}`}
                    >
                      <Typography variant="body2" component="span">
                        {row.qty_marking_printed}/{row.qty_need}
                      </Typography>
                    </Badge>
                  </TableCell>
                  <TableCell align="right">{row.marking_available_count}</TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={row.marking_available_count < 1}
                      onClick={() =>
                        openPrint({
                          token,
                          lineId: row.packaging_task_line_id,
                          productId: row.product_id,
                          documentNumber: row.document_number,
                          qtyNeedPack: row.qty_remaining,
                          markingAvailable: row.marking_available_count,
                          qtyMarkingPrinted: row.qty_marking_printed,
                          skuCode: row.sku_code,
                          productName: row.product_name,
                          onPrinted: () => {
                            void load()
                          },
                        })
                      }
                      data-testid={`ff-pending-marking-print-${row.packaging_task_line_id}`}
                    >
                      Печать
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {markingPrintDialog}
    </Box>
  )
}
