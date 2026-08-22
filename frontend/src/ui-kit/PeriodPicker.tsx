import { TextField } from '@mui/material'

export type PeriodPickerProps = {
  label?: string
  value: string
  onChange: (value: string) => void
  min?: string
  max?: string
  disabled?: boolean
  error?: string
  testId?: string
}

export function PeriodPicker({
  label = 'Месяц',
  value,
  onChange,
  min,
  max,
  disabled = false,
  error,
  testId,
}: PeriodPickerProps) {
  return (
    <TextField
      label={label}
      type="month"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      inputProps={{ min, max, 'data-testid': testId }}
      disabled={disabled}
      error={Boolean(error)}
      helperText={error}
      size="small"
    />
  )
}
