import { useEffect, useState } from 'react'
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

function toIso(next: Dayjs | null): string | null {
  if (next == null || !next.isValid()) {
    return null
  }
  return next.format('YYYY-MM-DD')
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
  const [draft, setDraft] = useState<Dayjs | null>(() => parseIso(value))

  useEffect(() => {
    setDraft(parseIso(value))
  }, [value])

  const commitDraft = (next: Dayjs | null) => {
    const iso = toIso(next)
    if (iso == null) {
      return
    }
    if (iso !== value) {
      onChange(iso)
    }
  }

  const picker = (
    <DatePicker
      label={label}
      value={draft}
      disabled={disabled}
      minDate={minDate ? parseIso(minDate) ?? undefined : undefined}
      onChange={(next) => {
        // Локальный черновик при наборе секций; не шлём null в родителя (MUI даёт null при закрытии).
        setDraft(next)
      }}
      onAccept={(next) => {
        setDraft(next)
        commitDraft(next)
      }}
      slotProps={{
        textField: {
          size: slotProps?.textField?.size ?? 'small',
          fullWidth: slotProps?.textField?.fullWidth ?? true,
          required,
          sx: slotProps?.textField?.sx,
          onBlur: (event) => {
            const target = event.target as HTMLInputElement
            const raw = target.value?.trim() ?? ''
            if (!raw) {
              return
            }
            const parsed = dayjs(raw, ['DD.MM.YYYY', 'YYYY-MM-DD', 'D.M.YYYY'], true)
            if (parsed.isValid()) {
              setDraft(parsed)
              commitDraft(parsed)
            }
          },
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
