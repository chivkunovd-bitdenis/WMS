import { useCallback, useEffect, useRef, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert,
  Badge,
  Box,
  Button,
  Checkbox,
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
import { PageHeader } from '../../ui/PageHeader'
import {
  fetchPendingMarking,
  pendingMarkingLineCount,
  type PendingMarkingLine,
} from '../../utils/pendingMarkingApi'
import { useMarkingCodePrint, type PrintLineArgs } from '../../utils/useMarkingCodePrint'

type Props = {
  token: string
}

function rowPrintable(row: PendingMarkingLine): boolean {
  return row.marking_available_count >= 1
}

export function FfPendingMarkingPage({ token }: Props) {
  const [rows, setRows] = useState<PendingMarkingLine[]>([])
  const [lineCount, setLineCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const printQueueRef = useRef<PendingMarkingLine[]>([])
  const { openPrint, dialog: markingPrintDialog } = useMarkingCodePrint()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const body = await fetchPendingMarking(token)
      setRows(body.rows)
      setLineCount(pendingMarkingLineCount(body))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить список')
      setRows([])
      setLineCount(0)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  const printableRows = rows.filter(rowPrintable)
  const selectedPrintableCount = printableRows.filter(
    (row) => selected[row.packaging_task_line_id],
  ).length
  const allPrintableSelected =
    printableRows.length > 0 && selectedPrintableCount === printableRows.length
  const somePrintableSelected =
    selectedPrintableCount > 0 && selectedPrintableCount < printableRows.length

  const buildPrintArgs = useCallback(
    (row: PendingMarkingLine, onDone: () => void): PrintLineArgs => ({
      token,
      lineId: row.packaging_task_line_id,
      productId: row.product_id,
      documentNumber: row.document_number,
      qtyNeedPack: row.qty_remaining,
      markingAvailable: row.marking_available_count,
      qtyMarkingPrinted: row.qty_marking_printed,
      requiresHonestSign: true,
      skuCode: row.sku_code,
      productName: row.product_name,
      onPrinted: () => {
        void load()
        // MarkingPrintDialog closes after onPrinted; defer queue so the next dialog stays open.
        window.setTimeout(() => onDone(), 0)
      },
    }),
    [load, token],
  )

  const openNextInQueue = useCallback(() => {
    const next = printQueueRef.current.shift()
    if (!next) {
      setSelected({})
      return
    }
    window.setTimeout(() => {
      openPrint(buildPrintArgs(next, openNextInQueue))
    }, 100)
  }, [buildPrintArgs, openPrint])

  const openRowPrint = (row: PendingMarkingLine) => {
    printQueueRef.current = []
    openPrint(buildPrintArgs(row, () => {}))
  }

  const openSelectedPrint = () => {
    const queue = rows.filter(
      (row) => selected[row.packaging_task_line_id] && rowPrintable(row),
    )
    if (queue.length < 1) {
      return
    }
    const [first, ...rest] = queue
    printQueueRef.current = rest
    openPrint(buildPrintArgs(first!, openNextInQueue))
  }

  const toggleRowSelected = (lineId: string, checked: boolean) => {
    setSelected((prev) => ({ ...prev, [lineId]: checked }))
  }

  const toggleSelectAllPrintable = (checked: boolean) => {
    if (!checked) {
      setSelected({})
      return
    }
    const next: Record<string, boolean> = {}
    for (const row of printableRows) {
      next[row.packaging_task_line_id] = true
    }
    setSelected(next)
  }

  return (
    <Box data-testid="ff-pending-marking-page">
      <PageHeader
        title="Осталось промаркировать"
        description="Строки заданий на упаковку, где ЧЗ ещё не напечатаны полностью."
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2, alignItems: 'center', flexWrap: 'wrap' }} useFlexGap>
        <Link component={RouterLink} to="/app/ff/packaging" variant="body2" data-testid="ff-pending-marking-back">
          ← К упаковке
        </Link>
        <Chip
          size="small"
          label={`${lineCount} строк`}
          data-testid="ff-pending-marking-count"
        />
        {rows.length > 0 ? (
          <Button
            size="small"
            variant="contained"
            disabled={selectedPrintableCount < 1}
            onClick={openSelectedPrint}
            data-testid="ff-pending-marking-print-selected"
          >
            Печать выбранных ({selectedPrintableCount})
          </Button>
        ) : null}
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
                <TableCell padding="checkbox" sx={{ width: 48 }}>
                  <Checkbox
                    checked={allPrintableSelected}
                    indeterminate={somePrintableSelected}
                    disabled={printableRows.length < 1}
                    onChange={(e) => toggleSelectAllPrintable(e.target.checked)}
                    data-testid="ff-pending-marking-select-all"
                  />
                </TableCell>
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
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={Boolean(selected[row.packaging_task_line_id])}
                      disabled={!rowPrintable(row)}
                      onChange={(e) =>
                        toggleRowSelected(row.packaging_task_line_id, e.target.checked)
                      }
                      data-testid={`ff-pending-marking-row-select-${row.packaging_task_line_id}`}
                    />
                  </TableCell>
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
                      disabled={!rowPrintable(row)}
                      onClick={() => openRowPrint(row)}
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
