import { Checkbox, FormControlLabel, IconButton, Tooltip } from '@mui/material'
import UndoOutlinedIcon from '@mui/icons-material/UndoOutlined'
import type { FbsScanPrintPreferences } from './fbsScanAutoPrint'

/** The three scan-print checkboxes of WB packing, shared by the supply and the assembly (WMS-631 R1). */
export function FbsScanPrintToggles({ value, onChange, undo }: {
  value: FbsScanPrintPreferences
  onChange: (next: FbsScanPrintPreferences) => void
  /** R19: «Назад» right after the checkboxes; absent where scans are not undoable. */
  undo?: { disabled: boolean; onClick: () => void }
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
    {undo ? (
      <Tooltip title="Отменить последний скан">
        <span>
          <IconButton size="small" aria-label="Отменить последний скан" disabled={undo.disabled}
            onClick={undo.onClick} data-testid="fbs-scan-undo">
            <UndoOutlinedIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
    ) : null}
  </>
}
