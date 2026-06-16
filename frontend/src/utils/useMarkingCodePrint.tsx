import { useState } from 'react'
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Typography,
} from '@mui/material'
import { apiUrl } from '../api'
import { readApiErrorMessage } from './readApiErrorMessage'
import { printMarkingCodeLabels } from './printMarkingCodeLabel'

type PrintLineArgs = {
  token: string
  lineId: string
  qtyNeedPack: number
  markingAvailable: number
  qtyMarkingPrinted: number
  skuCode: string
  onPrinted: () => void
}

export function useMarkingCodePrint() {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [duplicateCopies, setDuplicateCopies] = useState(true)
  const [reprint, setReprint] = useState(false)
  const [ctx, setCtx] = useState<PrintLineArgs | null>(null)
  const [previewQty, setPreviewQty] = useState(0)

  const openPrint = (args: PrintLineArgs, opts?: { reprint?: boolean }) => {
    setCtx(args)
    setReprint(Boolean(opts?.reprint))
    setDuplicateCopies(true)
    setError(null)
    setPreviewQty(opts?.reprint ? args.qtyMarkingPrinted : args.qtyNeedPack)
    setOpen(true)
  }

  const close = () => {
    if (!busy) {
      setOpen(false)
      setCtx(null)
    }
  }

  const confirmPrint = async () => {
    if (!ctx) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/marking-codes/packaging-lines/${ctx.lineId}/print`),
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${ctx.token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            duplicate_copies: duplicateCopies ? 2 : 1,
            reprint,
          }),
        },
      )
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as { codes: string[]; duplicate_copies: number }
      await printMarkingCodeLabels(data.codes, data.duplicate_copies)
      setOpen(false)
      setCtx(null)
      ctx.onPrinted()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось напечатать ЧЗ.')
    } finally {
      setBusy(false)
    }
  }

  const dialog = (
    <Dialog open={open} onClose={close} maxWidth="xs" fullWidth data-testid="marking-print-dialog">
      <DialogTitle>{reprint ? 'Повторная печать ЧЗ' : 'Печать ЧЗ'}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 0.5 }}>
          {ctx ? (
            <Typography variant="body2" data-testid="marking-print-qty">
              {reprint
                ? `Повторить ${previewQty} кодов для «${ctx.skuCode}».`
                : `Будет напечатано ${previewQty} уникальных кодов для «${ctx.skuCode}».`}
            </Typography>
          ) : null}
          <FormControlLabel
            control={
              <Checkbox
                checked={duplicateCopies}
                onChange={(e) => setDuplicateCopies(e.target.checked)}
                data-testid="marking-print-duplicate"
              />
            }
            label="В двух экземплярах (дубликат на упаковку)"
          />
          {error ? (
            <Alert severity="error" data-testid="marking-print-error">
              {error}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="contained"
          disabled={busy || previewQty < 1}
          onClick={() => void confirmPrint()}
          data-testid="marking-print-confirm"
        >
          Печать
        </Button>
      </DialogActions>
    </Dialog>
  )

  return { openPrint, dialog }
}
