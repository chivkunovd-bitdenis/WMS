import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { LabelSizeSelect } from '../../components/LabelSizeSelect'
import { loadLabelSizeId } from '../../utils/labelSize'
import { Alert, Box, InputAdornment, Stack, TextField, Typography } from '@mui/material'
import { useScanIntake } from '../../hooks/useScanIntake'
import { playScanError, playScanSuccess } from '../../utils/scanFeedback'
import { fbsErrorText } from './fbsUx'
import {
  createPackingSerialQueue, routePackingScan, type PackingScanController, type PackingSerialQueue,
} from './fbsSequentialPacking'
import { FbsScanPrintToggles } from './FbsScanPrintToggles'
import { FbsRejectedKizTriangle, type FbsRejectedKizFilter } from './FbsRejectedKizFilter'
import { loadFbsScanPrintPreferences, saveFbsScanPrintPreferences } from './fbsScanAutoPrint'

// The host DOM node is the lifetime of one visible packing surface. A temporary
// bar remount (for example, switching to boxes and back) reuses its FIFO, while
// another screen has another host and never waits for the previous screen.
const surfaceSerialQueues = new WeakMap<HTMLElement, Map<string, PackingSerialQueue>>()

function serialQueueForSurface(host: HTMLElement, contextKey: string): PackingSerialQueue {
  let contexts = surfaceSerialQueues.get(host)
  if (!contexts) {
    contexts = new Map()
    surfaceSerialQueues.set(host, contexts)
  }
  const existing = contexts.get(contextKey)
  if (existing) return existing
  const queue = createPackingSerialQueue()
  contexts.set(contextKey, queue)
  return queue
}

export function FbsPackingScanBar({ controllers, enabled, token, contextKey = token, rejected, qrDisabled = false }: {
  controllers: PackingScanController[]; enabled: boolean; token: string
  /** Stable identity of the assembly/supply served by this mounted bar. */
  contextKey?: string
  qrDisabled?: boolean
  /** WMS-636: the filter of the whole assembly (N summed over its WB supplies). */
  rejected?: FbsRejectedKizFilter
}) {
  const [value, setValue] = useState('')
  const [labelSizeId, setLabelSizeId] = useState(loadLabelSizeId)
  // WMS-631 R1, R3: the same saved checkboxes as the ordinary supply.
  const [printPreferences, setPrintPreferences] = useState(() => loadFbsScanPrintPreferences(token))
  const [error, setError] = useState<string | null>(null)
  const [undoing, setUndoing] = useState(false)
  const fallbackSerialQueue = useRef<PackingSerialQueue | null>(null)
  if (!fallbackSerialQueue.current) fallbackSerialQueue.current = createPackingSerialQueue()
  const serialQueueRef = useRef(fallbackSerialQueue.current)
  const queueGeneration = useRef(0)
  // Fence feedback and state writes from a bar that was unmounted/replaced.
  // The surface queue itself keeps accepted scans: a tab switch must not
  // discard the second scan of a rapid sequence.
  useLayoutEffect(() => {
    queueGeneration.current += 1
    return () => {
      queueGeneration.current += 1
    }
  }, [contextKey])
  // R19: the newest undoable scan across the supplies of this assembly.
  const newestStep = (list: PackingScanController[]) => list.reduce<PackingScanController | null>((best, one) => {
    const seq = one.lastStep?.() ?? null
    return seq !== null && (best === null || seq > (best.lastStep?.() ?? -1)) ? one : best
  }, null)
  const undoTarget = newestStep(controllers)
  const undoLast = () => {
    if (!undoTarget?.undo) return
    setUndoing(true)
    setError(null)
    const list = controllers
    const serialQueue = serialQueueRef.current
    // N4: the newest step is chosen when its turn comes, after the scans before it.
    const generation = queueGeneration.current
    void serialQueue.run(async () => {
      const target = newestStep(list)
      return target?.undo ? target.undo() : null
    })
      .then((warning) => { if (generation === queueGeneration.current && warning) setError(warning) })
      .catch((cause: unknown) => {
        if (generation !== queueGeneration.current) return
        setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось отменить скан.')
        playScanError()
      })
      .finally(() => { if (generation === queueGeneration.current) setUndoing(false) })
  }
  const active = (controllers.find((one) => one.hasSelectedRow?.()) ?? controllers.find((one) => one.hasPending()))?.view()
  const intake = useScanIntake({
    enabled,
    emitRaw: true,
    // This bar owns its serial queue, so enqueue at physical receipt time.
    // useScanIntake's render-paced queue remains useful to other screens, but
    // must not postpone the third rapid scan until after a box/context change.
    onScan: () => undefined,
    onReceived: (raw) => {
      setValue('')
      setError(null)
      // Snapshot supply-local context before this scan waits behind earlier
      // work in the shared serial queue.
      for (const controller of controllers) controller.onReceived?.(raw)
      // N4: the scan joins the one packing queue at once, in the order it was read,
      // so a later Escape or «Назад» never overtakes it.
      const generation = queueGeneration.current
      const serialQueue = serialQueueRef.current
      void routePackingScan(controllers, raw, 'сборке', serialQueue)
        .then(() => { if (generation === queueGeneration.current) playScanSuccess() })
        .catch((cause: unknown) => {
          if (generation !== queueGeneration.current) return
          setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось обработать скан.')
          playScanError()
        })
    },
    isScanOnlyField: (element) => element instanceof HTMLInputElement && element.dataset.packingScan === 'true',
  })
  const bindRoot = useCallback((node: HTMLElement | null) => {
    intake.bindRoot(node)
    if (node) serialQueueRef.current = serialQueueForSurface(node.parentElement ?? node, contextKey)
  }, [contextKey, intake.bindRoot])
  useEffect(() => {
    if (!intake.listening) return
    const acceptRow = (event: Event) => intake.submit((event as CustomEvent<string>).detail)
    document.addEventListener('fbs-packing-row-scan', acceptRow)
    return () => document.removeEventListener('fbs-packing-row-scan', acceptRow)
  }, [intake.listening, intake.submit])
  // R20: Escape drops a started scan before the window's own Escape handling.
  useEffect(() => {
    if (!enabled) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      const serialQueue = serialQueueRef.current
      if (!serialQueue.busy() && !controllers.some((one) => one.canCancel?.())) return
      event.preventDefault()
      event.stopPropagation()
      setError(null)
      const list = controllers
      // N4: Escape acts on the supply whose scan is in work when its turn comes.
      const generation = queueGeneration.current
      void serialQueue.run(async () => {
        const waiting = list.find((one) => one.canCancel?.())
        return waiting?.cancel ? waiting.cancel() : false
      }).catch((cause: unknown) => {
        if (generation !== queueGeneration.current) return
        setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось снять выбор.')
        playScanError()
      })
    }
    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [enabled, controllers])
  return <Box ref={bindRoot} sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider', bgcolor: 'action.hover' }} data-testid="fbs-unified-scan">
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <TextField size="small" fullWidth autoFocus value={value} disabled={!enabled} autoComplete="off"
        placeholder={active?.needsKiz ? 'Сканируйте Честный знак' : 'Сканируйте штрихкод товара'}
        onChange={(event) => setValue(event.target.value)}
        slotProps={{
          htmlInput: { 'data-packing-scan': 'true' },
          // WMS-635 Д4: inside the field, so nothing in the bar moves when it appears.
          input: rejected && rejected.count > 0 ? {
            endAdornment: <InputAdornment position="end"><FbsRejectedKizTriangle filter={rejected} /></InputAdornment>,
          } : undefined,
        }}
        onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); intake.submit(value); setValue('') } }} />
      {/* WB only: an Ozon-only assembly keeps its bar exactly as before (R16). */}
      {controllers.length > 0 ? <FbsScanPrintToggles value={printPreferences} qrDisabled={qrDisabled} onChange={(next) => {
        setPrintPreferences(next)
        saveFbsScanPrintPreferences(token, next)
      }} undo={{ disabled: !enabled || undoing || !undoTarget, onClick: undoLast }} /> : null}
      <LabelSizeSelect value={labelSizeId} onChange={(size) => setLabelSizeId(size.id)} />
      {active ? <Typography variant="body2" sx={{ minWidth: 160 }}>
        {active.name}{active.needsKiz ? ' · сканируйте ЧЗ' : ' · завершение упаковки'}
      </Typography> : null}
    </Stack>
    {error ? <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert> : null}
  </Box>
}
