import { useEffect, useState } from 'react'
import { LabelSizeSelect } from '../../components/LabelSizeSelect'
import { loadLabelSizeId } from '../../utils/labelSize'
import { Alert, Box, Stack, TextField, Typography } from '@mui/material'
import { useScanIntake } from '../../hooks/useScanIntake'
import { playScanError, playScanSuccess } from '../../utils/scanFeedback'
import { fbsErrorText } from './fbsUx'
import { packingSerialBusy, routePackingScan, runPackingSerial, type PackingScanController } from './fbsSequentialPacking'
import { FbsScanPrintToggles } from './FbsScanPrintToggles'
import type { FbsRejectedKizFilter } from './FbsRejectedKizFilter'
import { loadFbsScanPrintPreferences, saveFbsScanPrintPreferences } from './fbsScanAutoPrint'

export function FbsPackingScanBar({ controllers, enabled, token, rejected }: {
  controllers: PackingScanController[]; enabled: boolean; token: string
  /** WMS-636: the filter of the whole assembly (N summed over its WB supplies). */
  rejected?: FbsRejectedKizFilter
}) {
  const [value, setValue] = useState('')
  const [labelSizeId, setLabelSizeId] = useState(loadLabelSizeId)
  // WMS-631 R1, R3: the same saved checkboxes as the ordinary supply.
  const [printPreferences, setPrintPreferences] = useState(() => loadFbsScanPrintPreferences(token))
  const [error, setError] = useState<string | null>(null)
  const [undoing, setUndoing] = useState(false)
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
    // N4: the newest step is chosen when its turn comes, after the scans before it.
    void runPackingSerial(async () => {
      const target = newestStep(list)
      return target?.undo ? target.undo() : null
    })
      .then((warning) => { if (warning) setError(warning) })
      .catch((cause: unknown) => {
        setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось отменить скан.')
        playScanError()
      })
      .finally(() => setUndoing(false))
  }
  const active = (controllers.find((one) => one.hasSelectedRow?.()) ?? controllers.find((one) => one.hasPending()))?.view()
  const intake = useScanIntake({
    enabled,
    emitRaw: true,
    onScan: (raw) => {
      setError(null)
      // N4: the scan joins the one packing queue at once, in the order it was read,
      // so a later Escape or «Назад» never overtakes it.
      void routePackingScan(controllers, raw)
        .then(() => playScanSuccess())
        .catch((cause: unknown) => {
          setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось обработать скан.')
          playScanError()
        })
    },
    onReceived: () => setValue(''),
    isScanOnlyField: (element) => element instanceof HTMLInputElement && element.dataset.packingScan === 'true',
  })
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
      if (!packingSerialBusy() && !controllers.some((one) => one.canCancel?.())) return
      event.preventDefault()
      event.stopPropagation()
      setError(null)
      const list = controllers
      // N4: Escape acts on the supply whose scan is in work when its turn comes.
      void runPackingSerial(async () => {
        const waiting = list.find((one) => one.canCancel?.())
        return waiting?.cancel ? waiting.cancel() : false
      }).catch((cause: unknown) => {
        setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось снять выбор.')
        playScanError()
      })
    }
    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [enabled, controllers])
  return <Box ref={intake.bindRoot} sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider', bgcolor: 'action.hover' }} data-testid="fbs-unified-scan">
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <TextField size="small" fullWidth autoFocus value={value} disabled={!enabled} autoComplete="off"
        placeholder={active?.needsKiz ? 'Сканируйте Честный знак' : 'Сканируйте штрихкод товара'}
        onChange={(event) => setValue(event.target.value)}
        slotProps={{ htmlInput: { 'data-packing-scan': 'true' } }}
        onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); intake.submit(value); setValue('') } }} />
      {/* WB only: an Ozon-only assembly keeps its bar exactly as before (R16). */}
      {controllers.length > 0 ? <FbsScanPrintToggles value={printPreferences} onChange={(next) => {
        setPrintPreferences(next)
        saveFbsScanPrintPreferences(token, next)
      }} undo={{ disabled: !enabled || undoing || !undoTarget, onClick: undoLast }} rejected={rejected} /> : null}
      <LabelSizeSelect value={labelSizeId} onChange={(size) => setLabelSizeId(size.id)} />
      {active ? <Typography variant="body2" sx={{ minWidth: 160 }}>
        {active.name}{active.needsKiz ? ' · сканируйте ЧЗ' : ' · завершение упаковки'}
      </Typography> : null}
    </Stack>
    {error ? <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert> : null}
  </Box>
}
