import { useEffect, useRef, useState } from 'react'
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
  // Черновик и его ошибка проверки в ref: blur и Enter читают последнее значение без ожидания рендера.
  const draftRef = useRef<{ date: Dayjs | null; invalid: boolean }>({
    date: parseIso(value),
    invalid: false,
  })

  useEffect(() => {
    setDraft(parseIso(value))
    draftRef.current = { date: parseIso(value), invalid: false }
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

  // Набор с клавиатуры сохраняем только по окончании ввода, а не на промежуточной цифре года.
  const commitTyped = () => {
    if (draftRef.current.invalid) {
      return
    }
    commitDraft(draftRef.current.date)
  }

  const picker = (
    <DatePicker
      label={label}
      value={draft}
      disabled={disabled}
      minDate={minDate ? parseIso(minDate) ?? undefined : undefined}
      onChange={(next, context) => {
        // Локальный черновик при наборе секций; не шлём null в родителя (MUI даёт null при закрытии).
        setDraft(next)
        draftRef.current = { date: next, invalid: context.validationError != null }
      }}
      onAccept={(next, context) => {
        // Набор в поле MUI подтверждает на каждой полной дате (в т. ч. 0202 на середине года),
        // поэтому сразу сохраняем только выбор в календаре.
        if (context.source !== 'view') {
          return
        }
        setDraft(next)
        draftRef.current = { date: next, invalid: false }
        commitDraft(next)
      }}
      slotProps={{
        textField: {
          size: slotProps?.textField?.size ?? 'small',
          fullWidth: slotProps?.textField?.fullWidth ?? true,
          required,
          sx: slotProps?.textField?.sx,
          onBlur: (event) => {
            const nextFocus = event.relatedTarget as Node | null
            if (nextFocus && event.currentTarget.contains(nextFocus)) {
              return
            }
            commitTyped()
          },
          onKeyDown: (event) => {
            if (event.key === 'Enter') {
              commitTyped()
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
