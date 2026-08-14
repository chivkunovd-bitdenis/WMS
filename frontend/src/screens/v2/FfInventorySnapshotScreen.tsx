import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import AddchartOutlinedIcon from '@mui/icons-material/AddchartOutlined'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  canRunSnapshot?: boolean
}

type SnapshotRow = {
  id: string
  product_id: string
  product_name: string
  sku_code: string
  barcode: string | null
  snapshot_month: string
  quantity_total: number
  quantity_fbs: number
  quantity_reserved: number
  quantity_free_fbo: number
}

const MSK_TIME_ZONE = 'Europe/Moscow'

function currentMskMonthValue(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: MSK_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(new Date())
  const year = parts.find((p) => p.type === 'year')?.value ?? '1970'
  const month = parts.find((p) => p.type === 'month')?.value ?? '01'
  return `${year}-${month}`
}

function monthValueToApiDate(monthValue: string): string {
  return `${monthValue}-01`
}

function formatMonth(monthValue: string): string {
  const [year, month] = monthValue.split('-').map(Number)
  const d = new Date(Date.UTC(year, (month || 1) - 1, 1))
  return d.toLocaleDateString('ru-RU', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function FfInventorySnapshotScreen({
  token,
  authHeaders,
  canRunSnapshot = false,
}: Props) {
  const currentMonth = useMemo(() => currentMskMonthValue(), [])
  const [selectedMonth, setSelectedMonth] = useState(currentMonth)
  const [rows, setRows] = useState<SnapshotRow[]>([])
  const [busy, setBusy] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isCurrentMonth = selectedMonth === currentMonth
  const canRunSelectedMonth = canRunSnapshot && isCurrentMonth && rows.length === 0
  const emptyText = isCurrentMonth ? 'Снимок еще не сформирован' : 'За этот месяц снимка нет'

  const loadSnapshots = useCallback(
    async (monthValue: string) => {
      setBusy(true)
      setError(null)
      try {
        const res = await fetch(
          apiUrl(
            `/operations/inventory-balances/monthly-snapshots?month=${encodeURIComponent(
              monthValueToApiDate(monthValue),
            )}`,
          ),
          { headers: { ...authHeaders(token) } },
        )
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res))
        }
        setRows((await res.json()) as SnapshotRow[])
      } catch (e) {
        setRows([])
        setError(e instanceof Error ? e.message : 'Не удалось загрузить снимок остатков.')
      } finally {
        setBusy(false)
      }
    },
    [authHeaders, token],
  )

  useEffect(() => {
    void loadSnapshots(selectedMonth)
  }, [loadSnapshots, selectedMonth])

  const runSnapshot = useCallback(async () => {
    if (!canRunSelectedMonth) return
    setRunning(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/operations/inventory-balances/monthly-snapshots/run'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ month: monthValueToApiDate(selectedMonth) }),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setRows((await res.json()) as SnapshotRow[])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сформировать снимок остатков.')
    } finally {
      setRunning(false)
    }
  }, [authHeaders, canRunSelectedMonth, selectedMonth, token])

  return (
    <Box data-testid="ff-inventory-snapshot-screen">
      <Typography variant="h5" gutterBottom>
        Снимки остатков
      </Typography>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-inventory-snapshot-error">
          {error}
        </Alert>
      ) : null}

      {rows.length > 0 ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="ff-inventory-snapshot-saved">
          Показан сохраненный срез за {formatMonth(selectedMonth)}.
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="ff-inventory-snapshot-controls">
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1.5}
          sx={{ alignItems: { sm: 'center' } }}
        >
          <TextField
            size="small"
            label="Месяц"
            type="month"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            slotProps={{
              htmlInput: {
                'data-testid': 'ff-inventory-snapshot-month',
                max: currentMonth,
              },
            }}
            sx={{ width: { xs: '100%', sm: 220 } }}
          />
          <Button
            variant="contained"
            startIcon={<AddchartOutlinedIcon />}
            disabled={!canRunSelectedMonth || running}
            onClick={() => void runSnapshot()}
            data-testid="ff-inventory-snapshot-run"
          >
            Сформировать снимок
          </Button>
          {busy || running ? <CircularProgress size={20} data-testid="ff-inventory-snapshot-loading" /> : null}
        </Stack>
      </Paper>

      {rows.length > 0 ? (
        <TableContainer component={Paper} variant="outlined" data-testid="ff-inventory-snapshot-list">
          <Table size="small" data-testid="ff-inventory-snapshot-table">
            <TableHead>
              <TableRow>
                <TableCell>Товар</TableCell>
                <TableCell align="right" width={150}>
                  Общий остаток
                </TableCell>
                <TableCell align="right" width={130}>
                  FBS-пул
                </TableCell>
                <TableCell align="right" width={190}>
                  Резервы/направления
                </TableCell>
                <TableCell align="right" width={160}>
                  Свободный FBO
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, index) => (
                <TableRow key={row.id} hover data-testid="ff-inventory-snapshot-row">
                  <TableCell>
                    <Stack spacing={0.25}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {row.product_name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {row.sku_code}
                        {row.barcode ? ` / ${row.barcode}` : ''}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell align="right" data-testid={`ff-inventory-snapshot-total-${index}`}>
                    {row.quantity_total}
                  </TableCell>
                  <TableCell align="right" data-testid={`ff-inventory-snapshot-fbs-${index}`}>
                    {row.quantity_fbs}
                  </TableCell>
                  <TableCell align="right" data-testid={`ff-inventory-snapshot-reserved-${index}`}>
                    {row.quantity_reserved}
                  </TableCell>
                  <TableCell align="right" data-testid={`ff-inventory-snapshot-free-fbo-${index}`}>
                    {row.quantity_free_fbo}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ) : !busy ? (
        <Paper variant="outlined" sx={{ p: 3 }} data-testid="ff-inventory-snapshot-empty">
          <Typography variant="body2" color="text.secondary">
            {emptyText}
          </Typography>
        </Paper>
      ) : null}
    </Box>
  )
}
