import { Box, TextField, Typography } from '@mui/material'
import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from '../api'
import {
  AppDialog,
  MoscowDateInput,
  NumberInput,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  TextInput,
  ErrorNotice,
} from '../ui-kit'
import { confirmDiscardChanges } from '../utils/confirmDiscardChanges'
import {
  downloadAuthorizedFile,
  resolveAuthHeaders,
  type AuthHeadersSource,
} from '../utils/downloadAuthorizedFile'
import { createLatestRequestSequence } from '../utils/latestRequestSequence'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'

// WMS-686 D7/D8: пропуск на машину — одна запись на отгрузку. ФФ вносит сведения и правит их
// до проведения отгрузки, селлер видит те же сведения только на чтение. Окно общее для ФФ и
// селлера: отличается только режим. Все данные хранит сервер (GET/PUT …/pass), а XLSX
// строится из сохранённых значений (GET …/pass.xlsx).

/**
 * Поля пропуска. Набор и подписи держим в одном месте: форма, проверка и тело запроса
 * строятся по этому списку. Госномер и телефон — всегда строки (ведущие нули и «+» не теряются).
 */
const PASS_FIELDS = [
  { key: 'driver_last_name', label: 'Фамилия водителя', kind: 'text', required: true },
  { key: 'driver_first_name', label: 'Имя водителя', kind: 'text', required: true },
  { key: 'driver_phone', label: 'Телефон водителя', kind: 'text', requiredForOzon: true },
  { key: 'car_brand', label: 'Марка и модель автомобиля', kind: 'text', required: true },
  { key: 'car_number', label: 'Госномер', kind: 'text', required: true, hint: 'Например, А111АА111' },
  {
    key: 'cargo_type',
    label: 'Тип грузомест',
    kind: 'select',
    options: [
      { value: 'box', label: 'Короб' },
      { value: 'pallet', label: 'Паллета' },
    ],
  },
  { key: 'cargo_places_count', label: 'Количество грузомест', kind: 'number' },
  { key: 'arrival_date', label: 'Плановая дата приезда', kind: 'date' },
] as const satisfies readonly PassFieldSpec[]

type PassFieldSpec = {
  key: string
  label: string
  kind: 'text' | 'select' | 'number' | 'date'
  required?: boolean
  requiredForOzon?: boolean
  hint?: string
  options?: readonly { value: string; label: string }[]
}

export type PassFieldKey = (typeof PASS_FIELDS)[number]['key']

/** Сохранённые сведения, как их отдаёт сервер. Незаполненное — null или отсутствует. */
export type PassDetails = Partial<Record<PassFieldKey, string | number | null>>

type PassResponse = { pass_details: PassDetails | null; editable: boolean }

// В форме всё хранится строками: так не теряются ведущие нули и «+», а пустое значение
// отличается от нуля. Число и дату приводим к типам API только в теле запроса.
type PassDraft = Record<PassFieldKey, string>
type FieldErrors = Partial<Record<PassFieldKey, string>>

const PASS_KEYS = PASS_FIELDS.map((f) => f.key) as PassFieldKey[]

const EMPTY_DRAFT = Object.fromEntries(PASS_KEYS.map((k) => [k, ''])) as PassDraft

export type FboPassMode = 'ff' | 'seller'

const PHONE_REQUIRED_OZON = 'Для Ozon телефон водителя обязателен.'

// Тексты кодов ответа сервера (WMS-686, раздел 5.8). Общий словарь ошибок ведёт другой
// исполнитель; здесь те же формулировки, чтобы окно говорило по-русски в любом случае.
const PASS_ERROR_MESSAGES: Record<string, string> = {
  pass_phone_required: PHONE_REQUIRED_OZON,
  pass_not_editable: 'Отгрузка проведена или отменена — пропуск менять нельзя.',
  pass_not_filled: 'Пропуск ещё не внесён.',
  pass_field_required: 'Заполните обязательные поля пропуска.',
  forbidden: 'Нет прав на изменение пропуска.',
}

function toDraft(details: PassDetails | null | undefined): PassDraft {
  const draft = { ...EMPTY_DRAFT }
  if (!details) return draft
  for (const key of PASS_KEYS) {
    const value = details[key]
    draft[key] = value == null ? '' : String(value)
  }
  return draft
}

function toBody(draft: PassDraft): Record<PassFieldKey, string | number | null> {
  const text = (key: PassFieldKey) => draft[key].trim()
  const optional = (key: PassFieldKey) => (text(key) === '' ? null : text(key))
  const count = text('cargo_places_count')
  return {
    driver_last_name: text('driver_last_name'),
    driver_first_name: text('driver_first_name'),
    driver_phone: optional('driver_phone'),
    car_brand: text('car_brand'),
    car_number: text('car_number'),
    cargo_type: optional('cargo_type'),
    cargo_places_count: count === '' ? null : Number(count),
    arrival_date: optional('arrival_date'),
  }
}

function validate(draft: PassDraft, isOzon: boolean): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of PASS_FIELDS) {
    const spec: PassFieldSpec = field
    if (spec.required && draft[field.key].trim() === '') {
      errors[field.key] = 'Заполните поле'
    }
  }
  if (isOzon && draft.driver_phone.trim() === '') {
    errors.driver_phone = PHONE_REQUIRED_OZON
  }
  return errors
}

/** ISO-дату показываем как дд.мм.гггг без перевода часовых поясов. */
function formatIsoDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return match ? `${match[3]}.${match[2]}.${match[1]}` : iso
}

function readOnlyText(spec: PassFieldSpec, value: string): string {
  if (spec.kind === 'select') return spec.options?.find((o) => o.value === value)?.label ?? value
  if (spec.kind === 'date') return value ? formatIsoDate(value) : ''
  return value
}

async function readPassError(
  res: Response,
): Promise<{ message: string; code: string | null; fields: FieldErrors }> {
  let code: string | null = null
  const fields: FieldErrors = {}
  try {
    const data = JSON.parse(await res.clone().text()) as { detail?: unknown }
    const detail = data.detail
    if (typeof detail === 'string') {
      code = detail
    } else if (Array.isArray(detail)) {
      // Ответ проверки схемы: подсвечиваем поле, на которое указывает сервер. Английский
      // текст проверки не показываем — поле получает понятную русскую подсказку.
      for (const item of detail as { loc?: unknown }[]) {
        const loc = Array.isArray(item?.loc) ? item.loc : []
        const last = loc.length > 0 ? String(loc[loc.length - 1]) : ''
        if ((PASS_KEYS as string[]).includes(last)) {
          fields[last as PassFieldKey] = 'Проверьте значение'
        }
      }
    } else if (detail && typeof detail === 'object') {
      const structured = detail as { code?: unknown; field?: unknown }
      if (typeof structured.code === 'string') code = structured.code
      if (typeof structured.field === 'string' && (PASS_KEYS as string[]).includes(structured.field)) {
        fields[structured.field as PassFieldKey] = 'Заполните поле'
      }
    }
  } catch {
    /* тело не JSON — ниже возьмём общий текст ошибки */
  }
  if (code === 'pass_phone_required') {
    fields.driver_phone = PHONE_REQUIRED_OZON
  }
  // «pass_field_required: car_number» — поле может прийти после двоеточия.
  const requiredField = code?.startsWith('pass_field_required') ? code.split(/[:\s]+/)[1] : undefined
  if (requiredField && (PASS_KEYS as string[]).includes(requiredField)) {
    fields[requiredField as PassFieldKey] = 'Заполните поле'
    code = 'pass_field_required'
  }
  const mapped = code ? PASS_ERROR_MESSAGES[code] : undefined
  return { message: mapped ?? (await readApiErrorMessage(res)), code, fields }
}

type Props = {
  open: boolean
  token: string
  /** Заголовки авторизации: готовый объект или функция от токена (как в окнах селлера). */
  authHeaders: AuthHeadersSource
  requestId: string | null
  /** ФФ может править, пока отгрузка не проведена; селлер всегда читает. */
  mode: FboPassMode
  /** Площадка отгрузки: для Ozon телефон водителя обязателен. Без неё решает сервер (422). */
  marketplace?: string | null
  onClose: () => void
  /** Вызывается после успешного сохранения; получает сохранённые сведения. */
  onSaved?: (pass: PassDetails | null) => void
}

export function FboPassDialog({
  open,
  token,
  authHeaders,
  requestId,
  mode,
  marketplace,
  onClose,
  onSaved,
}: Props) {
  const [server, setServer] = useState<PassResponse | null>(null)
  const [draft, setDraft] = useState<PassDraft>(EMPTY_DRAFT)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [downloading, setDownloading] = useState(false)

  // Заголовки и токен читаем из ref: родитель может пересоздавать функцию на каждый рендер,
  // а это не должно ни перезагружать форму, ни стирать введённое.
  const authRef = useRef({ token, authHeaders })
  authRef.current = { token, authHeaders }
  // Повторное нажатие «Сохранить» до перерисовки не должно уйти вторым запросом.
  const savingRef = useRef(false)
  const loadRequests = useRef(createLatestRequestSequence())
  const downloadRequests = useRef(createLatestRequestSequence())

  const isOzon = marketplace === 'ozon'
  const passUrl = requestId ? `/operations/marketplace-unload-requests/${requestId}/pass` : null

  const load = useCallback(async () => {
    if (!passUrl) return
    const sequenceId = loadRequests.current.next()
    const isCurrent = () => loadRequests.current.isLatest(sequenceId)
    setLoadError(null)
    try {
      const { token: currentToken, authHeaders: currentHeaders } = authRef.current
      const res = await fetch(apiUrl(passUrl), { headers: resolveAuthHeaders(currentHeaders, currentToken) })
      if (!isCurrent()) return
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        if (isCurrent()) setLoadError(message)
        return
      }
      const body = (await res.json()) as PassResponse
      if (!isCurrent()) return
      setServer({ pass_details: body.pass_details ?? null, editable: Boolean(body.editable) })
      setDraft(toDraft(body.pass_details))
      setFieldErrors({})
    } catch (e) {
      if (isCurrent()) setLoadError(e instanceof Error ? e.message : 'Не удалось загрузить сведения о пропуске.')
    }
  }, [passUrl])

  useEffect(() => {
    if (!open || !passUrl) {
      loadRequests.current.invalidate()
      downloadRequests.current.invalidate()
      return
    }
    setServer(null)
    setDraft(EMPTY_DRAFT)
    setFieldErrors({})
    setLoadError(null)
    setSaveError(null)
    setDownloadError(null)
    setSaving(false)
    setDownloading(false)
    void load()
  }, [open, passUrl, token, load])

  const loading = server === null && loadError === null
  const hasSavedPass = server?.pass_details != null
  const canEdit = mode === 'ff' && server?.editable === true
  const baseline = toDraft(server?.pass_details)
  const dirty = canEdit && PASS_KEYS.some((key) => draft[key] !== baseline[key])

  function setField(key: PassFieldKey, value: string) {
    setDraft((current) => ({ ...current, [key]: value }))
    setFieldErrors((current) => {
      if (!current[key]) return current
      const next = { ...current }
      delete next[key]
      return next
    })
  }

  function handleClose() {
    if (saving) return
    if (!confirmDiscardChanges(dirty)) return
    onClose()
  }

  async function save() {
    if (!canEdit || saving || savingRef.current || !passUrl) return
    const errors = validate(draft, isOzon)
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) {
      setSaveError(null)
      return
    }
    savingRef.current = true
    setSaving(true)
    setSaveError(null)
    try {
      const { token: currentToken, authHeaders: currentHeaders } = authRef.current
      const res = await fetch(apiUrl(passUrl), {
        method: 'PUT',
        headers: { ...resolveAuthHeaders(currentHeaders, currentToken), 'Content-Type': 'application/json' },
        body: JSON.stringify({ pass_details: toBody(draft) }),
      })
      if (!res.ok) {
        const failure = await readPassError(res)
        setFieldErrors(failure.fields)
        if (failure.code === 'pass_not_editable') {
          // Отгрузку успели провести или отменить: форма должна показать сохранённую правду.
          await load()
          setSaveError(failure.message)
        } else if (Object.keys(failure.fields).length === 0) {
          // Ошибка без своего поля показывается над формой; введённое остаётся на месте.
          setSaveError(failure.message)
        }
        return
      }
      const body = (await res.json()) as PassResponse
      setServer({ pass_details: body.pass_details ?? null, editable: Boolean(body.editable) })
      setDraft(toDraft(body.pass_details))
      onSaved?.(body.pass_details ?? null)
      onClose()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Не удалось сохранить пропуск.')
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  async function download() {
    if (!requestId || downloading) return
    const sequenceId = downloadRequests.current.next()
    const isCurrent = () => downloadRequests.current.isLatest(sequenceId)
    setDownloading(true)
    setDownloadError(null)
    try {
      const { token: currentToken, authHeaders: currentHeaders } = authRef.current
      await downloadAuthorizedFile(
        `/operations/marketplace-unload-requests/${requestId}/pass.xlsx`,
        resolveAuthHeaders(currentHeaders, currentToken),
        'pass.xlsx',
        isCurrent,
      )
    } catch (e) {
      if (isCurrent()) {
        const message = e instanceof Error ? e.message : 'Не удалось скачать XLSX.'
        setDownloadError(PASS_ERROR_MESSAGES[message] ?? message)
      }
    } finally {
      if (isCurrent()) setDownloading(false)
    }
  }

  // XLSX строится из сохранённых значений: если пропуск уже сохранён, он скачивается с сервера
  // и при несохранённой правке в форме. Блок остаётся, только пока пропуска ещё нет.
  const downloadBlockedReason = loading
    ? 'Загрузка…'
    : downloading
      ? 'Файл формируется'
      : saving
        ? 'Идёт сохранение'
        : !hasSavedPass
          ? 'Сведения о пропуске ещё не внесены'
          : undefined

  const saveBlockedReason = loading ? 'Загрузка…' : saving ? 'Идёт сохранение' : undefined

  const emptyNote =
    !loading && !loadError && !hasSavedPass && !canEdit
      ? mode === 'seller'
        ? 'Фулфилмент ещё не внёс данные пропуска'
        : 'Данные пропуска не внесены'
      : null

  const downloadAction = (
    <SecondaryAction
      onClick={() => void download()}
      disabledReason={downloadBlockedReason}
      data-testid="fbo-pass-download"
    >
      Скачать XLSX
    </SecondaryAction>
  )

  const actions = canEdit ? (
    <>
      {downloadAction}
      <SecondaryAction onClick={handleClose} disabledReason={saving ? 'Идёт сохранение' : undefined} data-testid="fbo-pass-close">
        Закрыть
      </SecondaryAction>
      <PrimaryAction onClick={() => void save()} disabledReason={saveBlockedReason} data-testid="fbo-pass-save">
        Сохранить
      </PrimaryAction>
    </>
  ) : (
    <>
      <SecondaryAction onClick={handleClose} data-testid="fbo-pass-close">
        Закрыть
      </SecondaryAction>
      <PrimaryAction
        onClick={() => void download()}
        disabledReason={downloadBlockedReason}
        data-testid="fbo-pass-download"
      >
        Скачать XLSX
      </PrimaryAction>
    </>
  )

  return (
    <AppDialog
      open={open}
      title="Пропуск"
      onClose={handleClose}
      maxWidth="sm"
      testId="fbo-pass-dialog"
      actions={actions}
    >
      {loadError ? <ErrorNotice testId="fbo-pass-load-error">{loadError}</ErrorNotice> : null}
      {saveError ? <ErrorNotice testId="fbo-pass-save-error">{saveError}</ErrorNotice> : null}
      {downloadError ? <ErrorNotice testId="fbo-pass-download-error">{downloadError}</ErrorNotice> : null}
      {emptyNote ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="fbo-pass-empty">
          {emptyNote}
        </Typography>
      ) : null}
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'repeat(2, minmax(0, 1fr))' },
          alignItems: 'start',
        }}
        data-testid="fbo-pass-fields"
      >
        {PASS_FIELDS.map((field) => {
          const spec: PassFieldSpec = field
          const testId = `fbo-pass-${field.key}`
          const value = draft[field.key]
          if (!canEdit) {
            return (
              // Только чтение: поле выключено (как требует ТЗ) и закрыто для ввода, а цвет
              // текста оставлен обычным — сведения о водителе и машине должны читаться.
              <TextField
                key={field.key}
                size="small"
                fullWidth
                disabled
                label={field.label}
                value={readOnlyText(spec, value)}
                sx={{
                  '& .MuiInputBase-input.Mui-disabled': {
                    WebkitTextFillColor: (theme) => theme.palette.text.primary,
                  },
                }}
                slotProps={{
                  input: { readOnly: true },
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': testId },
                }}
              />
            )
          }
          const common = {
            label: field.label,
            required: Boolean(spec.required || (spec.requiredForOzon && isOzon)),
            disabled: loading || saving,
            error: fieldErrors[field.key],
            testId,
          }
          if (spec.kind === 'select') {
            return (
              <SelectInput
                key={field.key}
                {...common}
                value={value}
                onChange={(next) => setField(field.key, next)}
                options={[...(spec.options ?? [])]}
                emptyLabel="Не указан"
              />
            )
          }
          if (spec.kind === 'number') {
            return (
              <NumberInput
                key={field.key}
                {...common}
                value={value === '' ? null : Number(value)}
                onChange={(next) => setField(field.key, next == null ? '' : String(next))}
                min={1}
                step={1}
              />
            )
          }
          if (spec.kind === 'date') {
            return (
              <MoscowDateInput
                key={field.key}
                {...common}
                value={value === '' ? null : value}
                onChange={(next) => setField(field.key, next ?? '')}
              />
            )
          }
          return (
            <TextInput
              key={field.key}
              {...common}
              value={value}
              onChange={(next) => setField(field.key, next)}
              helperText={spec.hint}
            />
          )
        })}
      </Box>
    </AppDialog>
  )
}
