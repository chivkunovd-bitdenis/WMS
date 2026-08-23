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
  const helperTextId = testId ? `${testId}-helper` : undefined

  return (
    <TextField
      label={label}
      type="month"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      slotProps={{
        htmlInput: {
          min,
          max,
          'data-testid': testId,
          'aria-invalid': Boolean(error),
          'aria-describedby': helperTextId,
        },
        formHelperText: { id: helperTextId },
      }}
      disabled={disabled}
      error={Boolean(error)}
      helperText={error}
      size="small"
    />
  )
}
