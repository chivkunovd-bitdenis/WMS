import { Checkbox, FormControlLabel } from '@mui/material'
import type { FbsScanPrintPreferences } from './fbsScanAutoPrint'

/** The three scan-print checkboxes of WB packing, shared by the supply and the assembly (WMS-631 R1). */
export function FbsScanPrintToggles({ value, onChange }: {
  value: FbsScanPrintPreferences
  onChange: (next: FbsScanPrintPreferences) => void
}) {
  return <>
    <FormControlLabel
      data-testid="fbs-scan-print-qr-toggle"
      sx={{ m: 0, flexShrink: 0, whiteSpace: 'nowrap' }}
      control={
        <Checkbox
          size="small"
          checked={value.printQr}
          onChange={(event) => onChange({ ...value, printQr: event.target.checked })}
        />
      }
      label="Печатать QR"
    />
    <FormControlLabel
      data-testid="fbs-scan-print-chz-toggle"
      sx={{ m: 0, flexShrink: 0, whiteSpace: 'nowrap' }}
      control={
        <Checkbox
          size="small"
          checked={value.printChz}
          disabled={value.reprintChz}
          onChange={(event) => onChange({ ...value, printChz: event.target.checked })}
        />
      }
      label="Печатать ЧЗ"
    />
    <FormControlLabel
      data-testid="fbs-kiz-auto-reprint-toggle"
      sx={{ m: 0, flexShrink: 0, whiteSpace: 'nowrap' }}
      control={
        <Checkbox
          size="small"
          checked={value.reprintChz}
          disabled={value.printChz}
          onChange={(event) => onChange({ ...value, reprintChz: event.target.checked })}
        />
      }
      label="Перепечатывать ЧЗ"
    />
  </>
}
