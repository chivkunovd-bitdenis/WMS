import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { useScanIntake } from '../../../hooks/useScanIntake'
import { playScanError, playScanSuccess } from '../../../utils/scanFeedback'
import { FboScanPrintToggles } from './FboScanPrintToggles'
import type { FboPackingController } from './useFboPacking'

/**
 * Компактная серая строка скана упаковки FBO (по образцу FbsPackingScanBar):
 * поле «ШК товара или ЧЗ», две галки печати, «Печать накладной».
 * Сканер принимается сырым (emitRaw): GS не заменяется, разбор КИЗ — на сервере.
 */
export function FboPackingScanBar({ controller, disabled = false }: {
  controller: FboPackingController
  disabled?: boolean
}) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const intake = useScanIntake({
    enabled: !disabled,
    emitRaw: true,
    onReceived: () => {
      setError(null)
      setNotice(null)
    },
    onScan: async (code) => {
      try {
        const neutral = await controller.handleScan(code)
        if (!mounted.current) return
        // Введённое руками очищается только после успеха; отказ оставляет текст в поле.
        setValue((current) => (current.trim() === code.trim() ? '' : current))
        if (neutral) setNotice(neutral)
        playScanSuccess()
      } catch (cause) {
        if (!mounted.current) return
        setError(cause instanceof Error && cause.message ? cause.message : 'Не удалось обработать скан.')
        playScanError()
      }
    },
    isScanOnlyField: (element) => element instanceof HTMLInputElement && element.dataset.fboPackingScan === 'true',
  })

  return (
    <Box
      ref={intake.bindRoot}
      data-testid="fbo-packing-scan"
      sx={{ px: 1.5, py: 0.75, border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'action.hover' }}
    >
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 0.5 }}>
        <TextField
          size="small"
          autoFocus
          autoComplete="off"
          value={value}
          disabled={disabled}
          placeholder="ШК товара или ЧЗ"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return
            event.preventDefault()
            if (value.trim()) intake.submit(value)
          }}
          slotProps={{ htmlInput: { 'data-fbo-packing-scan': 'true', 'data-testid': 'fbo-packing-scan-input' } }}
          sx={{ flex: '1 1 220px', minWidth: 200, '& .MuiInputBase-input': { py: 0.75 } }}
        />
        <FboScanPrintToggles value={controller.prefs} onChange={controller.setPrefs} disabled={disabled} />
        <Button
          size="small"
          variant="outlined"
          startIcon={<PrintOutlined fontSize="small" />}
          onClick={controller.printWaybill}
          data-testid="ff-packaging-print-sheet"
          sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}
        >
          Печать накладной
        </Button>
      </Stack>
      {error ? (
        <Alert severity="error" sx={{ mt: 0.75, py: 0 }} data-testid="fbo-packing-scan-error">{error}</Alert>
      ) : null}
      {notice && !error ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }} data-testid="fbo-packing-scan-notice">
          {notice}
        </Typography>
      ) : null}
    </Box>
  )
}
