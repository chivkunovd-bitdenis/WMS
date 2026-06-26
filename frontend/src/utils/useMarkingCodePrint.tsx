import { useState } from 'react'
import {
  MarkingPrintDialog,
  type MarkingPrintContext,
} from '../components/MarkingPrintDialog'

export type PrintLineArgs = MarkingPrintContext

export function useMarkingCodePrint() {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [reprint, setReprint] = useState(false)
  const [ctx, setCtx] = useState<PrintLineArgs | null>(null)

  const openPrint = (args: PrintLineArgs, opts?: { reprint?: boolean }) => {
    setCtx(args)
    setReprint(Boolean(opts?.reprint))
    setOpen(true)
  }

  const close = () => {
    if (!busy) {
      setOpen(false)
      setCtx(null)
    }
  }

  const dialog = (
    <MarkingPrintDialog
      open={open}
      reprint={reprint}
      ctx={ctx}
      busy={busy}
      onBusyChange={setBusy}
      onClose={close}
    />
  )

  return { openPrint, dialog }
}
