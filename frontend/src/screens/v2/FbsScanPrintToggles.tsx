import type { MouseEvent } from 'react'
import { Box, Checkbox, FormControlLabel, IconButton, Tooltip, Typography } from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import RemoveIcon from '@mui/icons-material/Remove'
import UndoOutlinedIcon from '@mui/icons-material/UndoOutlined'
import {
  FBS_CHZ_COPIES_MAX, FBS_CHZ_COPIES_MIN, normalizeFbsChzCopies, type FbsScanPrintPreferences,
} from './fbsScanAutoPrint'

/**
 * WMS-633: number of KIZ labels printed by one scan, «− N +» next to its checkbox.
 * Nothing here takes focus: a scanner burst and its Enter always reach the scan field.
 */
function CopiesField({ value, onChange, label, testId }: {
  value: number | undefined
  onChange: (next: number) => void
  label: string
  testId: string
}) {
  const count = normalizeFbsChzCopies(value)
  const keepFocus = (event: MouseEvent) => event.preventDefault()
  return (
    <Box data-testid={testId} aria-label={label} sx={{ display: 'inline-flex', alignItems: 'center', flexShrink: 0 }}>
      <IconButton size="small" tabIndex={-1} aria-label={`${label}: меньше`} disabled={count <= FBS_CHZ_COPIES_MIN}
        onMouseDown={keepFocus} onClick={() => onChange(normalizeFbsChzCopies(count - 1))}
        data-testid={`${testId}-minus`} sx={{ p: 0.25 }}>
        <RemoveIcon fontSize="small" />
      </IconButton>
      <Typography variant="body2" data-testid={`${testId}-value`} sx={{ minWidth: 18, textAlign: 'center' }}>{count}</Typography>
      <IconButton size="small" tabIndex={-1} aria-label={`${label}: больше`} disabled={count >= FBS_CHZ_COPIES_MAX}
        onMouseDown={keepFocus} onClick={() => onChange(normalizeFbsChzCopies(count + 1))}
        data-testid={`${testId}-plus`} sx={{ p: 0.25 }}>
        <AddIcon fontSize="small" />
      </IconButton>
    </Box>
  )
}

/** The three scan-print checkboxes of WB packing, shared by the supply and the assembly (WMS-631 R1). */
export function FbsScanPrintToggles({ value, onChange, undo, qrDisabled = false }: {
  value: FbsScanPrintPreferences
  onChange: (next: FbsScanPrintPreferences) => void
  /** Ozon has no WB order QR. Keep the shared control visible without overwriting the saved WB preference. */
  qrDisabled?: boolean
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
          checked={qrDisabled ? false : value.printQr}
          disabled={qrDisabled}
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
