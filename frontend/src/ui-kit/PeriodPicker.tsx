import dayjs from 'dayjs'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'

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
  const current = dayjs(`${value}-01`)
  const minDate = min ? dayjs(`${min}-01`) : undefined
  const maxDate = max ? dayjs(`${max}-01`) : undefined

  return (
    <DatePicker
      label={label}
      views={['year', 'month']}
      openTo="month"
      format="MMMM YYYY"
      value={current.isValid() ? current : null}
      minDate={minDate}
      maxDate={maxDate}
      onChange={(next) => {
        if (!next?.isValid()) return
        const nextValue = next.format('YYYY-MM')
        if (min && nextValue < min) return
        if (max && nextValue > max) return
        onChange(nextValue)
      }}
      disabled={disabled}
      slotProps={{
        textField: {
          disabled,
          error: Boolean(error),
          helperText: error,
          size: 'small',
          sx: {
            '& .MuiPickersSectionList-sectionContent': { textTransform: 'capitalize' },
          },
          slotProps: {
            htmlInput: {
              'data-testid': testId,
              'aria-invalid': Boolean(error),
              'aria-describedby': helperTextId,
              style: { textTransform: 'capitalize' },
            } as {
              'data-testid': string | undefined
              'aria-invalid': boolean
              'aria-describedby': string | undefined
              style: { textTransform: 'capitalize' }
            },
            formHelperText: { id: helperTextId },
          },
        },
      }}
    />
  )
}
