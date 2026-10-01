import { useEffect, useState } from 'react'
import { LabelSizeSelect } from '../../components/LabelSizeSelect'
import { loadLabelSizeId } from '../../utils/labelSize'
import { Alert, Box, Stack, TextField, Typography } from '@mui/material'
import { useScanIntake } from '../../hooks/useScanIntake'
import { playScanError, playScanSuccess } from '../../utils/scanFeedback'
import { fbsErrorText } from './fbsUx'
import { routePackingScan, type PackingScanController } from './fbsSequentialPacking'
import { FbsScanPrintToggles } from './FbsScanPrintToggles'
import { loadFbsScanPrintPreferences, saveFbsScanPrintPreferences } from './fbsScanAutoPrint'

export function FbsPackingScanBar({ controllers, enabled, token }: {
  controllers: PackingScanController[]; enabled: boolean; token: string
}) {
  const [value, setValue] = useState('')
  const [labelSizeId, setLabelSizeId] = useState(loadLabelSizeId)
  // WMS-631 R1, R3: the same saved checkboxes as the ordinary supply.
  const [printPreferences, setPrintPreferences] = useState(() => loadFbsScanPrintPreferences(token))
  const [error, setError] = useState<string | null>(null)
  const [undoing, setUndoing] = useState(false)
  // R19: the newest undoable scan across the supplies of this assembly.
  const undoTarget = controllers.reduce<PackingScanController | null>((best, one) => {
    const seq = one.lastStep?.() ?? null
    return seq !== null && (best === null || seq > (best.lastStep?.() ?? -1)) ? one : best
  }, null)
  const undoLast = () => {
    if (!undoTarget?.undo) return
    setUndoing(true)
    setError(null)
    void undoTarget.undo()
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
    onScan: async (raw) => {
      setError(null)
      try {
        await routePackingScan(controllers, raw)
        playScanSuccess()
      } catch (cause) {
        setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось обработать скан.')
        playScanError()
      }
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
      const waiting = controllers.find((one) => one.canCancel?.())
      if (!waiting?.cancel) return
      event.preventDefault()
      event.stopPropagation()
      setError(null)
      void waiting.cancel().catch((cause: unknown) => {
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
      <FbsScanPrintToggles value={printPreferences} onChange={(next) => {
        setPrintPreferences(next)
        saveFbsScanPrintPreferences(token, next)
      }} undo={{ disabled: !enabled || undoing || !undoTarget, onClick: undoLast }} />
      <LabelSizeSelect value={labelSizeId} onChange={(size) => setLabelSizeId(size.id)} />
      {active ? <Typography variant="body2" sx={{ minWidth: 160 }}>
        {active.name}{active.needsKiz ? ' · сканируйте ЧЗ' : ' · завершение упаковки'}
      </Typography> : null}
    </Stack>
    {error ? <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert> : null}
  </Box>
}
