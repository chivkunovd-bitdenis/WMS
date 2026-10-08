import { Checkbox, FormControlLabel } from '@mui/material'
import type { FboPackingPrintPreferences } from './fboPackingPrefs'

/**
 * Две галки печати упаковки FBO. Вид и MUI-элементы те же, что у FbsScanPrintToggles,
 * но без «Печатать QR» и «Перепечатывать ЧЗ»; сам компонент FBS не затронут.
 */
export function FboScanPrintToggles({ value, onChange, disabled = false }: {
  value: FboPackingPrintPreferences
  onChange: (next: FboPackingPrintPreferences) => void
  disabled?: boolean
}) {
  return <>
    <FormControlLabel
      data-testid="fbo-scan-print-barcode-toggle"
      sx={{ m: 0, flexShrink: 0, whiteSpace: 'nowrap' }}
      control={
        <Checkbox
          size="small"
          checked={value.printBarcode}
          disabled={disabled}
          onChange={(event) => onChange({ ...value, printBarcode: event.target.checked })}
        />
      }
      label="Печатать ШК"
    />
    <FormControlLabel
      data-testid="fbo-scan-print-chz-toggle"
      sx={{ m: 0, flexShrink: 0, whiteSpace: 'nowrap' }}
      control={
        <Checkbox
          size="small"
          checked={value.printChz}
          disabled={disabled}
          onChange={(event) => onChange({ ...value, printChz: event.target.checked })}
        />
      }
      label="Печатать ЧЗ"
    />
  </>
}
