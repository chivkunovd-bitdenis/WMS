import { useState } from 'react'
import { LabelSizeSelect } from '../../components/LabelSizeSelect'
import { loadLabelSizeId } from '../../utils/labelSize'
import { Alert, Box, Stack, TextField, Typography } from '@mui/material'
import { useScanIntake } from '../../hooks/useScanIntake'
import { playScanError, playScanSuccess } from '../../utils/scanFeedback'
import { fbsErrorText } from './fbsUx'
import { routePackingScan, type PackingScanController } from './fbsSequentialPacking'

export function FbsPackingScanBar({ controllers, enabled }: {
  controllers: PackingScanController[]; enabled: boolean
}) {
  const [value, setValue] = useState('')
  const [labelSizeId, setLabelSizeId] = useState(loadLabelSizeId)
  const [error, setError] = useState<string | null>(null)
  const active = controllers.find((one) => one.hasPending())?.view()
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
  return <Box ref={intake.bindRoot} sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider', bgcolor: 'action.hover' }} data-testid="fbs-unified-scan">
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <TextField size="small" fullWidth autoFocus value={value} disabled={!enabled} autoComplete="off"
        placeholder={active?.needsKiz ? 'Сканируйте Честный знак' : 'Сканируйте штрихкод товара'}
        onChange={(event) => setValue(event.target.value)}
        slotProps={{ htmlInput: { 'data-packing-scan': 'true' } }}
        onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); intake.submit(value); setValue('') } }} />
      <LabelSizeSelect value={labelSizeId} onChange={(size) => setLabelSizeId(size.id)} />
      {active ? <Typography variant="body2" sx={{ minWidth: 160 }}>
        {active.name}{active.needsKiz ? ' · сканируйте ЧЗ' : ' · завершение упаковки'}
      </Typography> : null}
    </Stack>
    {error ? <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert> : null}
  </Box>
}
