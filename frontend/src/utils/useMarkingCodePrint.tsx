import { useRef, useState } from 'react'
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
  const completion = useRef<{ completed: boolean; onClose?: (completed: boolean) => void } | null>(null)

  const openPrint = (args: PrintLineArgs, opts?: { reprint?: boolean; onClose?: (completed: boolean) => void }) => {
    const current = { completed: false, onClose: opts?.onClose }
    completion.current = current
    setCtx(args.fbsTape ? {
      ...args,
      fbsTape: {
        ...args.fbsTape,
        onCompleted: () => {
          current.completed = true
          args.fbsTape?.onCompleted?.()
        },
      },
    } : args)
    setReprint(Boolean(opts?.reprint))
    setOpen(true)
  }

  const close = () => {
    const current = completion.current
    completion.current = null
    setOpen(false)
    setCtx(null)
    current?.onClose?.(current.completed)
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
