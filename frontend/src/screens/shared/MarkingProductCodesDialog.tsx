import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { maskCisCode, printMarkingCodeLabels } from '../../utils/printMarkingCodeLabel'

type CodeRow = {
  id: string
  cis_code: string
  status: string
  created_at: string
}

type Props = {
  open: boolean
  token: string
  productId: string | null
  productLabel: string
  testIdPrefix: string
  onClose: () => void
}

const STATUS_LABEL: Record<string, string> = {
  available: 'Доступен',
  printed: 'Напечатан',
  void: 'Аннулирован',
}

export function MarkingProductCodesDialog({
  open,
  token,
  productId,
  productLabel,
  testIdPrefix,
  onClose,
}: Props) {
  const [rows, setRows] = useState<CodeRow[]>([])
  const [busy, setBusy] = useState(false)
  const [printBusy, setPrintBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [duplicateCopies, setDuplicateCopies] = useState(true)

  const loadCodes = useCallback(async () => {
    if (!productId) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/operations/marking-codes/products/${productId}/codes`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setRows((await res.json()) as CodeRow[])
    } finally {
      setBusy(false)
    }
  }, [productId, token])

  useEffect(() => {
    if (open && productId) {
      void loadCodes()
    } else {
      setRows([])
      setError(null)
    }
  }, [open, productId, loadCodes])

  const printCodes = async (codes: string[]) => {
    if (codes.length === 0) {
      return
    }
    setPrintBusy(true)
    setError(null)
    try {
      await printMarkingCodeLabels(codes, duplicateCopies ? 2 : 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать.')
    } finally {
      setPrintBusy(false)
    }
  }

  const availableCodes = rows.filter((r) => r.status === 'available').map((r) => r.cis_code)

  return (
    <Dialog
      open={open}
      onClose={() => !printBusy && onClose()}
      fullWidth
      maxWidth="md"
      data-testid={`${testIdPrefix}-codes-dialog`}
    >
      <DialogTitle>Коды ЧЗ — {productLabel}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 0.5 }}>
          <FormControlLabel
            control={
              <Checkbox
                checked={duplicateCopies}
                onChange={(e) => setDuplicateCopies(e.target.checked)}
                data-testid={`${testIdPrefix}-codes-duplicate`}
              />
            }
            label="В двух экземплярах"
          />
          {error ? (
            <Alert severity="error" data-testid={`${testIdPrefix}-codes-error`}>
              {error}
            </Alert>
          ) : null}
          <TableContainer>
            <Table size="small" data-testid={`${testIdPrefix}-codes-table`}>
              <TableHead>
                <TableRow>
                  <TableCell>Код (КИЗ)</TableCell>
                  <TableCell>Статус</TableCell>
                  <TableCell align="right">Печать</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3}>
                      <Typography variant="body2" color="text.secondary">
                        {busy ? 'Загрузка…' : 'Кодов пока нет.'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((r) => (
                    <TableRow key={r.id} data-testid={`${testIdPrefix}-code-row-${r.id}`}>
                      <TableCell>
                        <Typography variant="body2" component="span" title={r.cis_code}>
                          {maskCisCode(r.cis_code)}
                        </Typography>
                      </TableCell>
                      <TableCell>{STATUS_LABEL[r.status] ?? r.status}</TableCell>
                      <TableCell align="right">
                        <IconButton
                          size="small"
                          aria-label="Печать кода"
                          disabled={printBusy}
                          onClick={() => void printCodes([r.cis_code])}
                          data-testid={`${testIdPrefix}-code-print-${r.id}`}
                        >
                          <PrintOutlined fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={printBusy}>
          Закрыть
        </Button>
        <Button
          variant="contained"
          startIcon={<PrintOutlined />}
          disabled={printBusy || availableCodes.length === 0}
          onClick={() => void printCodes(availableCodes)}
          data-testid={`${testIdPrefix}-codes-print-all`}
        >
          Печать доступных ({availableCodes.length})
        </Button>
      </DialogActions>
    </Dialog>
  )
}
