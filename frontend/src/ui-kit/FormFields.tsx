import { Box, TextField } from '@mui/material'
import type { ChangeEvent } from 'react'
import { useId, useMemo, useState } from 'react'

type FieldProps = {
  id?: string
  label: string
  error?: string
  helperText?: string
  disabled?: boolean
  loading?: boolean
  required?: boolean
  testId?: string
}

type TextInputProps = FieldProps & {
  value: string
  onChange: (value: string) => void
  multiline?: boolean
}

type NumberInputProps = FieldProps & {
  value: number | null
  onChange: (value: number | null) => void
  min?: number
  max?: number
  step?: number
}

type SelectInputProps = FieldProps & {
  value: string
  onChange: (value: string) => void
  options: Array<{ value: string; label: string; disabled?: boolean }>
  emptyLabel?: string
}

type MoscowDateTimeInputProps = FieldProps & {
  value: string | null
  onChange: (utcIso: string | null) => void
}

const MOSCOW_TIME_ZONE = 'Europe/Moscow'
const WALL_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/

function visibleHelp({ error, helperText, loading }: FieldProps) {
  return error ?? helperText ?? (loading ? 'Загрузка…' : undefined)
}

type FieldMetadata = {
  inputId: string
  helperId?: string
  helperText?: string
}

function useFieldMetadata(props: FieldProps): FieldMetadata {
  const generatedId = useId().replace(/[^A-Za-z0-9_-]/g, '')
  const inputId = props.id ?? `ui-field-${generatedId}`
  const helperText = visibleHelp(props)
  return {
    inputId,
    helperId: helperText ? `${inputId}-helper` : undefined,
    helperText,
  }
}

function FieldFrame({ children, loading, testId }: { children: React.ReactNode; loading?: boolean; testId?: string }) {
  return (
    <Box data-testid={testId ? `${testId}-field` : undefined} aria-busy={loading || undefined}>
      {children}
    </Box>
  )
}

function inputA11y(props: FieldProps, metadata: FieldMetadata) {
  return {
    'data-testid': props.testId,
    'aria-invalid': Boolean(props.error),
    ...(metadata.helperId ? { 'aria-describedby': metadata.helperId } : {}),
  }
}

function commonProps(props: FieldProps, metadata: FieldMetadata) {
  return {
    id: metadata.inputId,
    label: props.label,
    required: props.required,
    disabled: Boolean(props.disabled || props.loading),
    error: Boolean(props.error),
    helperText: metadata.helperText,
    size: 'small' as const,
    fullWidth: true,
    slotProps: {
      htmlInput: inputA11y(props, metadata),
      ...(metadata.helperId ? { formHelperText: { id: metadata.helperId } } : {}),
    },
  }
}

export function TextInput({ value, onChange, multiline = false, ...props }: TextInputProps) {
  const metadata = useFieldMetadata(props)
  return (
    <FieldFrame loading={props.loading} testId={props.testId}>
      <TextField
        {...commonProps(props, metadata)}
        value={value}
        multiline={multiline}
        minRows={multiline ? 2 : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldFrame>
  )
}

export function NumberInput({ value, onChange, min, max, step = 1, ...props }: NumberInputProps) {
  const metadata = useFieldMetadata(props)
  function handleChange(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    const raw = event.target.value.trim()
    if (!raw) {
      onChange(null)
      return
    }
    const parsed = Number(raw)
    if (!Number.isFinite(parsed) || (min != null && parsed < min) || (max != null && parsed > max)) {
      return
    }
    onChange(parsed)
  }

  return (
    <FieldFrame loading={props.loading} testId={props.testId}>
      <TextField
        {...commonProps(props, metadata)}
        type="number"
        value={value ?? ''}
        onChange={handleChange}
        slotProps={{
          ...commonProps(props, metadata).slotProps,
          htmlInput: {
            ...inputA11y(props, metadata),
            min,
            max,
            step,
            inputMode: 'decimal',
            style: { textAlign: 'right' },
          },
        }}
      />
    </FieldFrame>
  )
}

export function SelectInput({ value, onChange, options, emptyLabel, ...props }: SelectInputProps) {
  const metadata = useFieldMetadata(props)
  return (
    <FieldFrame loading={props.loading} testId={props.testId}>
      <TextField
        {...commonProps(props, metadata)}
        select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        slotProps={{
          ...commonProps(props, metadata).slotProps,
          inputLabel: { shrink: true },
          select: { native: true, tabIndex: 0 },
        }}
      >
        {emptyLabel ? <option value="">{emptyLabel}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </TextField>
    </FieldFrame>
  )
}

function localPartsAt(utcMillis: number) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: MOSCOW_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(utcMillis))
  const values = Object.fromEntries(parts.filter((part) => part.type !== 'literal').map((part) => [part.type, part.value]))
  return {
    year: Number(values.year),
    month: Number(values.month),
    day: Number(values.day),
    hour: Number(values.hour),
    minute: Number(values.minute),
    second: Number(values.second),
  }
}

function parseWallTime(value: string) {
  const match = WALL_TIME_PATTERN.exec(value)
  if (!match) return null
  const [, rawYear, rawMonth, rawDay, rawHour, rawMinute, rawSecond = '0'] = match
  const parts = {
    year: Number(rawYear),
    month: Number(rawMonth),
    day: Number(rawDay),
    hour: Number(rawHour),
    minute: Number(rawMinute),
    second: Number(rawSecond),
  }
  const probe = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second))
  if (
    probe.getUTCFullYear() !== parts.year || probe.getUTCMonth() + 1 !== parts.month || probe.getUTCDate() !== parts.day ||
    probe.getUTCHours() !== parts.hour || probe.getUTCMinutes() !== parts.minute || probe.getUTCSeconds() !== parts.second
  ) return null
  return parts
}

function sameParts(left: ReturnType<typeof localPartsAt>, right: NonNullable<ReturnType<typeof parseWallTime>>) {
  return left.year === right.year && left.month === right.month && left.day === right.day && left.hour === right.hour &&
    left.minute === right.minute && left.second === right.second
}

function resolveMoscowWallTime(value: string) {
  const wall = parseWallTime(value)
  if (!wall) return null
  const nominalUtc = Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute, wall.second)
  const offsets = new Set([-18, 0, 18].map((hours) => {
    const instant = nominalUtc + hours * 60 * 60 * 1000
    const local = localPartsAt(instant)
    return Date.UTC(local.year, local.month - 1, local.day, local.hour, local.minute, local.second) - instant
  }))
  const matches = [...offsets]
    .map((offset) => nominalUtc - offset)
    .filter((instant) => sameParts(localPartsAt(instant), wall))
  return matches.length === 1 ? new Date(matches[0]).toISOString() : null
}

function formatMoscowWallTime(value: string | null) {
  if (!value) return ''
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) return ''
  const parts = localPartsAt(instant.getTime())
  return `${parts.year.toString().padStart(4, '0')}-${parts.month.toString().padStart(2, '0')}-${parts.day.toString().padStart(2, '0')}T${parts.hour.toString().padStart(2, '0')}:${parts.minute.toString().padStart(2, '0')}`
}

// Test-only seam; it is deliberately not re-exported by ui-kit/index.
export const __formFieldsTest = { resolveMoscowWallTime }

export function MoscowDateTimeInput({ value, onChange, ...props }: MoscowDateTimeInputProps) {
  const [localError, setLocalError] = useState<string | undefined>()
  const wallValue = useMemo(() => formatMoscowWallTime(value), [value])
  const error = localError ?? props.error
  const fieldProps = { ...props, error }
  const metadata = useFieldMetadata(fieldProps)

  function handleChange(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    const next = event.target.value
    if (!next) {
      setLocalError(undefined)
      onChange(null)
      return
    }
    const utc = resolveMoscowWallTime(next)
    if (utc == null) {
      setLocalError('Укажите существующее однозначное время Москвы')
      return
    }
    setLocalError(undefined)
    onChange(utc)
  }

  return (
    <FieldFrame loading={fieldProps.loading} testId={fieldProps.testId}>
      <TextField
        {...commonProps(fieldProps, metadata)}
        type="datetime-local"
        value={wallValue}
        onChange={handleChange}
        slotProps={{
          ...commonProps(fieldProps, metadata).slotProps,
          inputLabel: { shrink: true },
        }}
      />
    </FieldFrame>
  )
}
