import { Checkbox, FormControlLabel, IconButton, TextField, Tooltip } from '@mui/material'
import UndoOutlinedIcon from '@mui/icons-material/UndoOutlined'
import {
  FBS_CHZ_COPIES_MAX, FBS_CHZ_COPIES_MIN, normalizeFbsChzCopies, type FbsScanPrintPreferences,
} from './fbsScanAutoPrint'

/** WMS-633: number of KIZ labels printed by one scan, shown next to its checkbox. */
function CopiesField({ value, onChange, label, testId }: {
  value: number | undefined
  onChange: (next: number) => void
  label: string
  testId: string
}) {
  return (
    <TextField
      type="number"
      size="small"
      value={normalizeFbsChzCopies(value)}
      onChange={(event) => {
        // An emptied field keeps the last count; arrows and typing give 1…10.
        if (event.target.value.trim() === '') return
        onChange(normalizeFbsChzCopies(event.target.value))
      }}
      slotProps={{ htmlInput: { min: FBS_CHZ_COPIES_MIN, max: FBS_CHZ_COPIES_MAX, step: 1, 'aria-label': label, 'data-testid': testId } }}
      sx={{ width: 56, flexShrink: 0, '& input': { px: 1 } }}
    />
  )
}

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
    {value.printChz ? (
      <CopiesField value={value.printChzCopies} label="Экземпляров ЧЗ" testId="fbs-scan-print-chz-copies"
        onChange={(next) => onChange({ ...value, printChzCopies: next })} />
    ) : null}
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
    {value.reprintChz ? (
      <CopiesField value={value.reprintChzCopies} label="Экземпляров перепечати ЧЗ" testId="fbs-scan-reprint-chz-copies"
        onChange={(next) => onChange({ ...value, reprintChzCopies: next })} />
    ) : null}
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
