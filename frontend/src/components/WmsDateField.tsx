import dayjs, { type Dayjs } from 'dayjs'
import { Box } from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'

type Props = {
  label: string
  value: string | null
  onChange: (isoDate: string | null) => void
  disabled?: boolean
  required?: boolean
  minDate?: string | null
  testId?: string
  slotProps?: {
    textField?: { size?: 'small' | 'medium'; fullWidth?: boolean; sx?: object }
  }
}

function parseIso(value: string | null): Dayjs | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null
  }
  const d = dayjs(value, 'YYYY-MM-DD', true)
  return d.isValid() ? d : null
}

export function WmsDateField({
  label,
  value,
  onChange,
  disabled = false,
  required = false,
  minDate = null,
  testId,
  slotProps,
}: Props) {
  const picker = (
    <DatePicker
      label={label}
      value={parseIso(value)}
      disabled={disabled}
      minDate={minDate ? parseIso(minDate) ?? undefined : undefined}
      onChange={(next) => {
        if (next == null || !next.isValid()) {
          onChange(null)
          return
        }
        onChange(next.format('YYYY-MM-DD'))
      }}
      slotProps={{
        textField: {
          size: slotProps?.textField?.size ?? 'small',
          fullWidth: slotProps?.textField?.fullWidth ?? true,
          required,
          sx: slotProps?.textField?.sx,
        },
      }}
    />
  )

  if (testId) {
    return (
      <Box data-testid={testId}>
        {picker}
      </Box>
    )
  }

  return picker
}
