import PrintOutlined from '@mui/icons-material/PrintOutlined'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useBarcodeScanner } from '../hooks/useBarcodeScanner'
import {
  loadKizReprints,
  mergeKizReprintRow,
  saveKizReprint,
  type KizReprintRow,
} from '../utils/kizReprintApi'
import { printKizHistory, printScannedKiz } from '../utils/kizReprintPrint'
import { printMarkingCodeLabels } from '../utils/printMarkingCodeLabel'
import { randomId } from '../utils/randomId'

type Props = {
  open: boolean
  token: string
  sellerId: string | null | undefined
  onClose: () => void
  testId?: string
}

/** The shared FF dialog for return reception and the FF Honest Sign page. */
export function KizReprintDialog({
  open,
  token,
  sellerId,
  onClose,
  testId = 'kiz-reprint-dialog',
}: Props) {
  const [rows, setRows] = useState<KizReprintRow[]>([])
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [printing, setPrinting] = useState<string | null>(null)
  const idempotencyKeys = useRef(new Map<string, string>())

  const reload = useCallback(async () => {
    if (!sellerId) return
    setLoading(true)
    setError(null)
    try {
      setRows(await loadKizReprints(token, sellerId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить перепечатанные КИЗ.')
    } finally {
      setLoading(false)
    }
  }, [sellerId, token])

  useEffect(() => {
    if (open) void reload()
  }, [open, reload])

  const printRows = useCallback(async (target: KizReprintRow[]) => {
    if (target.length === 0) return
    setPrinting(target.map((row) => row.id).join(','))
    setError(null)
    try {
      await printKizHistory(target, (codes) => printMarkingCodeLabels(codes, { duplicateCopies: 1 }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось открыть печать КИЗ.')
    } finally {
      setPrinting(null)
    }
  }, [])

  const scan = useCallback(async (rawKiz: string) => {
    // Barcode wedges often add a newline.  Do not use String.trim(): KIZ may
    // contain the ASCII GS separator (0x1D), which is part of the printed code.
    const kiz = rawKiz.replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, '')
    if (!sellerId || !kiz || loading || printing !== null) return
    const idempotencyKey = idempotencyKeys.current.get(kiz) ?? randomId()
    idempotencyKeys.current.set(kiz, idempotencyKey)
    setInput('')
    setError(null)
    setLoading(true)
    try {
      const row = await saveKizReprint(token, { sellerId, kiz, idempotencyKey })
      setRows((current) => mergeKizReprintRow(current, row))
      await printScannedKiz(row, (codes) => printMarkingCodeLabels(codes, { duplicateCopies: 1 }))
      idempotencyKeys.current.delete(kiz)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось сохранить КИЗ для печати.')
    } finally {
      setLoading(false)
    }
  }, [loading, printing, sellerId, token])

  useBarcodeScanner({ enabled: open && Boolean(sellerId) && !loading && printing === null, onScan: scan })

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid={testId}>
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <Typography component="span" variant="h6">Перепечатать ЧЗ</Typography>
          <Button
            size="small"
            variant="outlined"
            startIcon={<PrintOutlined />}
            disabled={rows.length === 0 || printing !== null}
            onClick={() => void printRows(rows)}
            data-testid={`${testId}-print-all`}
          >
            Печать всё
          </Button>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ pt: '8px !important' }}>
        <TextField
          autoFocus
          fullWidth
          size="small"
          value={input}
          disabled={!sellerId || loading || printing !== null}
          placeholder="Сканируйте КИЗ"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.defaultPrevented) {
              event.preventDefault()
              void scan(input)
            }
          }}
          slotProps={{ htmlInput: { 'data-testid': `${testId}-scan-input` } }}
        />
        {error ? <Alert severity="error" sx={{ mt: 1 }} data-testid={`${testId}-error`}>{error}</Alert> : null}
        <Stack spacing={0.5} sx={{ mt: 1.5 }} data-testid={`${testId}-history`}>
          {rows.map((row) => (
            <Stack
              key={row.id}
              direction="row"
              spacing={1}
              sx={{ alignItems: 'center', justifyContent: 'space-between', minWidth: 0 }}
              data-testid={`${testId}-row-${row.id}`}
            >
              <Box sx={{ minWidth: 0, flex: 1, overflowWrap: 'anywhere' }}>
                <Typography variant="body2">Честный знак {row.kiz} успешно перепечатан</Typography>
              </Box>
              <Tooltip title="Печать КИЗ">
                <IconButton
                  size="small"
                  aria-label="Печать КИЗ"
                  disabled={printing !== null}
                  onClick={() => void printRows([row])}
                  data-testid={`${testId}-print-${row.id}`}
                >
                  <PrintOutlined fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} data-testid={`${testId}-done`}>Готово</Button>
      </DialogActions>
    </Dialog>
  )
}
