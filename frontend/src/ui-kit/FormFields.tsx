import { Box, Checkbox, FormControlLabel, FormHelperText, Stack, Switch, TextField, Tooltip } from '@mui/material'
import type { ChangeEvent } from 'react'
import { useEffect, useId, useMemo, useState } from 'react'

type FieldProps = {
  id?: string
  label: string
  error?: string
  helperText?: string
  disabled?: boolean
  loading?: boolean
  required?: boolean
  testId?: string
  /** Adds an existing group-level description without replacing this field's own help. */
  describedBy?: string
  /** Marks a field invalid when its group owns the explanatory error text. */
  invalid?: boolean
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

type MoscowDateInputProps = FieldProps & {
  value: string | null
  onChange: (value: string | null) => void
  minDate?: string
  maxDate?: string
}

export type MoscowDateRangeValue = {
  start: string | null
  end: string | null
}

type MoscowDateRangeInputProps = FieldProps & {
  value: MoscowDateRangeValue
  onChange: (value: MoscowDateRangeValue) => void
  startLabel?: string
  endLabel?: string
  minDate?: string
  maxDate?: string
  /** Maximum number of calendar dates in the inclusive range. */
  maxDays?: number
}

type PreferenceSwitchProps = FieldProps & {
  checked: boolean
  onChange: (checked: boolean) => void
}

type CheckboxInputProps = FieldProps & {
  checked: boolean
  onChange: (checked: boolean) => void
  /** Explains why a non-interactive choice is unavailable. */
  disabledReason?: string
  /**
   * Заголовок колонки уже назвал выбор, поэтому в ячейке таблицы подпись рядом
   * с квадратом только шумит. Имя всё равно обязано существовать: без него
   * программа чтения объявит «флажок» и промолчит о том, что выбирается.
   */
  hideLabel?: boolean
}

type MoneyInputProps = FieldProps & {
  /** Decimal string is deliberate: money must not pass through a JS float. */
  value: string
  onChange: (value: string) => void
  allowNegative?: boolean
}

const MOSCOW_TIME_ZONE = 'Europe/Moscow'
const WALL_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/
const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/

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

// Со скрытой подписью причина недоступности обязана остаться программе чтения
// через aria-describedby, но не может быть видимым текстом: в колонке таблицы
// она переносится и растягивает строку втрое по высоте.
// Пиксели записаны строками намеренно: в MUI `sx` число не больше единицы для
// width/height означает долю, то есть `width: 1` — это 100%, а не один пиксель.
// С долей скрытая подсказка растягивается на всю ширину и уводит страницу вправо.
const VISUALLY_HIDDEN = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  margin: '-1px',
  padding: 0,
  border: 0,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const


function FieldFrame({ children, loading, testId }: { children: React.ReactNode; loading?: boolean; testId?: string }) {
  return (
    <Box data-testid={testId ? `${testId}-field` : undefined} aria-busy={loading || undefined}>
      {children}
    </Box>
  )
}

function inputA11y(props: FieldProps, metadata: FieldMetadata) {
  const describedBy = [metadata.helperId, props.describedBy].filter(Boolean).join(' ')
  return {
    'data-testid': props.testId,
    'aria-invalid': Boolean(props.error || props.invalid),
    ...(describedBy ? { 'aria-describedby': describedBy } : {}),
  }
}

function commonProps(props: FieldProps, metadata: FieldMetadata) {
  return {
    id: metadata.inputId,
    label: props.label,
    required: props.required,
    disabled: Boolean(props.disabled || props.loading),
    error: Boolean(props.error || props.invalid),
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

// Денежная сумма остаётся строкой до границы API. Так нельзя незаметно потерять
// копейки (например, «12.20») или превратить неверный ввод в другое число.
function validateMoney(value: string, allowNegative: boolean) {
  if (!value) return undefined
  if (!allowNegative && value.startsWith('-')) return 'Сумма не может быть отрицательной'
  return /^-?\d+(?:\.\d{1,2})?$/.test(value) ? undefined : 'Укажите сумму с точностью до копеек'
}

export function MoneyInput({ value, onChange, allowNegative = false, ...props }: MoneyInputProps) {
  const localError = validateMoney(value, allowNegative)
  const fieldProps = { ...props, error: props.error ?? localError }
  const metadata = useFieldMetadata(fieldProps)
  return (
    <FieldFrame loading={fieldProps.loading} testId={fieldProps.testId}>
      <TextField
        {...commonProps(fieldProps, metadata)}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        slotProps={{
          ...commonProps(fieldProps, metadata).slotProps,
          htmlInput: {
            ...inputA11y(fieldProps, metadata),
            inputMode: 'decimal',
            style: { textAlign: 'right' },
          },
        }}
      />
    </FieldFrame>
  )
}

export function CheckboxInput({ checked, onChange, disabledReason, hideLabel, ...props }: CheckboxInputProps) {
  const fieldProps = {
    ...props,
    helperText: props.helperText ?? disabledReason,
  }
  const metadata = useFieldMetadata(fieldProps)
  const disabled = Boolean(fieldProps.disabled || fieldProps.loading || disabledReason)
  const control = (
    <Checkbox
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      disabled={disabled}
      slotProps={{ input: { ...inputA11y(fieldProps, metadata), id: metadata.inputId, ...(hideLabel ? { 'aria-label': fieldProps.label } : {}) } }}
    />
  )

  return (
    <FieldFrame loading={fieldProps.loading} testId={fieldProps.testId}>
      <Box>
        {disabledReason ? <Tooltip title={disabledReason}><span>{hideLabel ? control : <FormControlLabel label={fieldProps.label} control={control} />}</span></Tooltip> : hideLabel ? control : <FormControlLabel label={fieldProps.label} control={control} />}
        {metadata.helperId ? <FormHelperText id={metadata.helperId} error={Boolean(fieldProps.error)} sx={hideLabel ? VISUALLY_HIDDEN : undefined}>{metadata.helperText}</FormHelperText> : null}
      </Box>
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

function parseIsoDate(value: string) {
  const match = DATE_PATTERN.exec(value)
  if (!match) return null
  const [, rawYear, rawMonth, rawDay] = match
  const year = Number(rawYear)
  const month = Number(rawMonth)
  const day = Number(rawDay)
  const probe = new Date(Date.UTC(year, month - 1, day))
  if (probe.getUTCFullYear() !== year || probe.getUTCMonth() + 1 !== month || probe.getUTCDate() !== day) return null
  return probe
}

function validateIsoDate(value: string | null, minDate?: string, maxDate?: string) {
  if (value == null || value === '') return undefined
  const parsed = parseIsoDate(value)
  if (parsed == null) return 'Укажите корректную дату'
  if ((minDate && value < minDate) || (maxDate && value > maxDate)) return 'Дата вне допустимого диапазона'
  return undefined
}

function validateDateRange(
  value: MoscowDateRangeValue,
  { minDate, maxDate, maxDays }: Pick<MoscowDateRangeInputProps, 'minDate' | 'maxDate' | 'maxDays'>,
) {
  const startError = validateIsoDate(value.start, minDate, maxDate)
  const endError = validateIsoDate(value.end, minDate, maxDate)
  if (startError || endError) return startError ?? endError
  if (!value.start || !value.end) return undefined
  const start = parseIsoDate(value.start)
  const end = parseIsoDate(value.end)
  if (start == null || end == null) return 'Укажите корректную дату'
  if (end < start) return 'Дата окончания не может быть раньше даты начала'
  const inclusiveDays = Math.floor((end.getTime() - start.getTime()) / 86_400_000) + 1
  if (maxDays != null && inclusiveDays > maxDays) return 'Период превышает допустимую длину'
  return undefined
}

type DateInputLocalError = { value: string | null; message: string }

function resolvedDateInputError(
  value: string | null,
  localError: DateInputLocalError | undefined,
  propsError: string | undefined,
  minDate?: string,
  maxDate?: string,
) {
  return propsError ?? validateIsoDate(value, minDate, maxDate) ?? (
    localError?.value === value ? localError.message : undefined
  )
}

export function MoscowDateInput({ value, onChange, minDate, maxDate, ...props }: MoscowDateInputProps) {
  const [localError, setLocalError] = useState<DateInputLocalError | undefined>()
  useEffect(() => {
    setLocalError((current) => current?.value === value ? current : undefined)
  }, [value])
  const error = resolvedDateInputError(value, localError, props.error, minDate, maxDate)
  const fieldProps = { ...props, error }
  const metadata = useFieldMetadata(fieldProps)

  function handleChange(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    const next = event.target.value || null
    const validation = validateIsoDate(next, minDate, maxDate)
    setLocalError(validation ? { value, message: validation } : undefined)
    if (!validation) onChange(next)
  }

  return (
    <FieldFrame loading={fieldProps.loading} testId={fieldProps.testId}>
      <TextField
        {...commonProps(fieldProps, metadata)}
        type="date"
        value={value ?? ''}
        onChange={handleChange}
        slotProps={{
          ...commonProps(fieldProps, metadata).slotProps,
          inputLabel: { shrink: true },
          htmlInput: { ...inputA11y(fieldProps, metadata), min: minDate, max: maxDate },
        }}
      />
    </FieldFrame>
  )
}

export function MoscowDateRangeInput({
  value,
  onChange,
  startLabel = 'Начало',
  endLabel = 'Окончание',
  minDate,
  maxDate,
  maxDays,
  ...props
}: MoscowDateRangeInputProps) {
  const validation = validateDateRange(value, { minDate, maxDate, maxDays })
  const error = validation ?? props.error
  const fieldProps = { ...props, error }
  const metadata = useFieldMetadata(fieldProps)

  function changePart(part: keyof MoscowDateRangeValue, next: string | null) {
    onChange({ ...value, [part]: next })
  }

  return (
    <FieldFrame loading={fieldProps.loading} testId={fieldProps.testId}>
      <Box component="fieldset" sx={{ border: 0, m: 0, p: 0 }} aria-invalid={Boolean(error)} aria-describedby={metadata.helperId}>
        <Box component="legend" sx={{ typography: 'body2', color: error ? 'error.main' : 'text.primary', mb: 0.75 }}>
          {fieldProps.label}
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <MoscowDateInput
            id={`${metadata.inputId}-start`}
            label={startLabel}
            value={value.start}
            onChange={(next) => changePart('start', next)}
            minDate={minDate}
            maxDate={maxDate}
            disabled={fieldProps.disabled}
            loading={fieldProps.loading}
            required={fieldProps.required}
            testId={fieldProps.testId ? `${fieldProps.testId}-start` : undefined}
            invalid={Boolean(error)}
            describedBy={metadata.helperId}
          />
          <MoscowDateInput
            id={`${metadata.inputId}-end`}
            label={endLabel}
            value={value.end}
            onChange={(next) => changePart('end', next)}
            minDate={minDate}
            maxDate={maxDate}
            disabled={fieldProps.disabled}
            loading={fieldProps.loading}
            required={fieldProps.required}
            testId={fieldProps.testId ? `${fieldProps.testId}-end` : undefined}
            invalid={Boolean(error)}
            describedBy={metadata.helperId}
          />
        </Stack>
        {metadata.helperId ? <FormHelperText id={metadata.helperId} error={Boolean(error)}>{metadata.helperText}</FormHelperText> : null}
      </Box>
    </FieldFrame>
  )
}

export function PreferenceSwitch({ checked, onChange, ...props }: PreferenceSwitchProps) {
  const metadata = useFieldMetadata(props)
  const disabled = Boolean(props.disabled || props.loading)
  return (
    <FieldFrame loading={props.loading} testId={props.testId}>
      <Box>
        <FormControlLabel
          label={props.label}
          control={
            <Switch
              checked={checked}
              onChange={(event) => onChange(event.target.checked)}
              disabled={disabled}
              slotProps={{ input: { ...inputA11y(props, metadata), id: metadata.inputId } }}
            />
          }
        />
        {metadata.helperId ? <FormHelperText id={metadata.helperId} error={Boolean(props.error)}>{metadata.helperText}</FormHelperText> : null}
      </Box>
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
export const __formFieldsTest = { resolveMoscowWallTime, resolvedDateInputError, validateDateRange, validateIsoDate, validateMoney }

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
