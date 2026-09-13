import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FfBillingTariffMatrixPanel } from './FfBillingTariffMatrixPanel'
import { FfSubscriptionPanel } from './FfSubscriptionPanel'
import {
  FF_STAFF_ACCESS_BLOCKS,
  applyFfStaffAccessChange,
  ffPermissionsToStaffAccess,
  type FfPermissions,
  type FfStaffAccessKey,
} from '../../utils/ffPermissions'
type StaffPackagingBilling = {
  billing_month: string
  units_packed: number
  earned_rub: string
}
type StaffAccountRow = {
  id: string
  email: string | null
  full_name?: string | null
  job_title?: string | null
  display_name: string
  role: string
  must_set_password: boolean
  permissions: FfPermissions
  packaging_rate_rub?: string
  packaging_billing?: StaffPackagingBilling
}

import { FfLabelTemplatePanel } from './FfLabelTemplatePanel'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  me?: { display_name: string; full_name?: string | null; job_title?: string | null }
  onProfileUpdated?: (profile: { full_name: string; job_title: string }) => Promise<unknown>
  isFulfillmentAdmin: boolean
  canManageStaff: boolean
  addressStorageEnabled?: boolean
  onAddressStorageChange?: (enabled: boolean) => void
  separateMarkingPrintEnabled?: boolean
  fbsShipmentCutoffTime?: string | null
}

function humanStaffError(message: string): string {
  if (message.includes('email_taken')) return 'Этот сотрудник уже добавлен'
  if (message.includes('forbidden') || message.includes('Нет доступа')) {
    return 'Нет доступа к сотрудникам'
  }
  if (message.includes('not_staff_user') || message.includes('user_not_found')) {
    return 'Сотрудник не найден'
  }
  return message || 'Не удалось сохранить. Попробуйте еще раз'
}

function currentBillingMonth(): string {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  return `${y}-${m}`
}

function formatRubDisplay(value: string): string {
  const n = Number(value)
  if (!Number.isFinite(n)) {
    return value
  }
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

export function FfSettingsScreen({
  token,
  authHeaders,
  me,
  onProfileUpdated,
  isFulfillmentAdmin,
  canManageStaff,
  addressStorageEnabled = true,
  onAddressStorageChange,
  // separateMarkingPrintEnabled больше не используется здесь: переключатель
  // «раздельная печать ЧЗ/ШК» переехал на форму печати (MarkingPrintDialog, FBS-10).
  fbsShipmentCutoffTime = null,
}: Props) {
  const [rows, setRows] = useState<StaffAccountRow[]>([])
  const [billingMonth, setBillingMonth] = useState(currentBillingMonth)
  const [busy, setBusy] = useState(false)
  const [addressStorage, setAddressStorage] = useState(addressStorageEnabled)
  const [addressStorageBusy, setAddressStorageBusy] = useState(false)
  const [addressStorageNotice, setAddressStorageNotice] = useState<{
    severity: 'success' | 'info'
    message: string
    testId: string
  } | null>(null)
  const [fbsCutoff, setFbsCutoff] = useState(fbsShipmentCutoffTime ?? '')
  const [fbsCutoffSaved, setFbsCutoffSaved] = useState(fbsShipmentCutoffTime ?? '')
  const [fbsCutoffBusy, setFbsCutoffBusy] = useState(false)
  const [permBusyId, setPermBusyId] = useState<string | null>(null)
  const [rateBusyId, setRateBusyId] = useState<string | null>(null)
  const [rateDrafts, setRateDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [permSavedNotice, setPermSavedNotice] = useState<string | null>(null)
  const [rateSavedNotice, setRateSavedNotice] = useState<string | null>(null)
  const [highlightRowId, setHighlightRowId] = useState<string | null>(null)
  const [profileFullName, setProfileFullName] = useState(me?.full_name ?? '')
  const [profileJobTitle, setProfileJobTitle] = useState(me?.job_title ?? '')
  const [profileBusy, setProfileBusy] = useState(false)
  const [editingRow, setEditingRow] = useState<StaffAccountRow | null>(null)
  const [editingFullName, setEditingFullName] = useState('')
  const [editingJobTitle, setEditingJobTitle] = useState('')
  const [editingBusy, setEditingBusy] = useState(false)

  useEffect(() => {
    setProfileFullName(me?.full_name ?? '')
    setProfileJobTitle(me?.job_title ?? '')
  }, [me?.full_name, me?.job_title])

  const loadRows = useCallback(async () => {
    if (!token || !canManageStaff) {
      return
    }
    const staffUrl = isFulfillmentAdmin
      ? `/auth/staff-accounts?${new URLSearchParams({ billing_month: billingMonth }).toString()}`
      : '/auth/staff-accounts'
    const res = await fetch(apiUrl(staffUrl), {
      headers: authHeaders(token),
    })
    if (!res.ok) {
      throw new Error(humanStaffError(await readApiErrorMessage(res)))
    }
    const data = (await res.json()) as StaffAccountRow[]
    setRows(data)
    setRateDrafts(
      isFulfillmentAdmin
        ? Object.fromEntries(data.map((row) => [row.id, row.packaging_rate_rub ?? '0.00']))
        : {},
    )
  }, [authHeaders, billingMonth, canManageStaff, isFulfillmentAdmin, token])

  useEffect(() => {
    void loadRows().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить сотрудников.')
    })
  }, [loadRows])

  useEffect(() => {
    setAddressStorage(addressStorageEnabled)
  }, [addressStorageEnabled])

  useEffect(() => {
    setFbsCutoff(fbsShipmentCutoffTime ?? '')
    setFbsCutoffSaved(fbsShipmentCutoffTime ?? '')
  }, [fbsShipmentCutoffTime])

  useEffect(() => {
    if (!highlightRowId) {
      return
    }
    const timer = window.setTimeout(() => setHighlightRowId(null), 4000)
    return () => window.clearTimeout(timer)
  }, [highlightRowId])

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    if (!token || !canManageStaff) {
      return
    }
    setError(null)
    setSuccess(null)
    setBusy(true)
    try {
      const fd = new FormData(form)
      const fullName = String(fd.get('staff_full_name') ?? '').trim()
      const jobTitle = String(fd.get('staff_job_title') ?? '').trim()
      const password = String(fd.get('staff_password') ?? '')
      if (!fullName || !password) {
        setError('Укажите ФИО и пароль сотрудника.')
        return
      }
      const res = await fetch(apiUrl('/auth/staff-accounts'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName, job_title: jobTitle || null, password }),
      })
      if (!res.ok) {
        setError(humanStaffError(await readApiErrorMessage(res)))
        return
      }
      const created = (await res.json()) as StaffAccountRow
      form.reset()
      await loadRows()
      setHighlightRowId(created.id)
      setSuccess('Сотрудник добавлен')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить сотрудника.')
    } finally {
      setBusy(false)
    }
  }

  async function onTogglePermission(
    row: StaffAccountRow,
    key: FfStaffAccessKey,
    checked: boolean,
  ) {
    if (!token || !canManageStaff) {
      return
    }
    setError(null)
    setPermBusyId(row.id)
    const next = applyFfStaffAccessChange(row.permissions, key, checked)
    try {
      const res = await fetch(apiUrl(`/auth/staff-accounts/${row.id}/permissions`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
      if (!res.ok) {
        setError(humanStaffError(await readApiErrorMessage(res)))
        return
      }
      const updated = (await res.json()) as StaffAccountRow
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      setPermSavedNotice('Права сохранены')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить права.')
    } finally {
      setPermBusyId(null)
    }
  }

  async function savePackagingRate(row: StaffAccountRow) {
    if (!token || !isFulfillmentAdmin) {
      return
    }
    const draft = (rateDrafts[row.id] ?? '').trim().replace(',', '.')
    if (!draft) {
      setError('Укажите ставку за единицу (0 или больше).')
      return
    }
    const parsed = Number(draft)
    if (!Number.isFinite(parsed) || parsed < 0) {
      setError('Ставка должна быть неотрицательным числом.')
      return
    }
    setError(null)
    setRateBusyId(row.id)
    try {
      const params = new URLSearchParams({ billing_month: billingMonth })
      const res = await fetch(
        apiUrl(`/auth/staff-accounts/${row.id}/packaging-rate?${params.toString()}`),
        {
          method: 'PATCH',
          headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
          body: JSON.stringify({ rate_rub: parsed }),
        },
      )
      if (!res.ok) {
        setError(humanStaffError(await readApiErrorMessage(res)))
        return
      }
      const updated = (await res.json()) as StaffAccountRow
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      setRateDrafts((prev) => ({ ...prev, [row.id]: updated.packaging_rate_rub ?? '0.00' }))
      setRateSavedNotice(`${row.display_name}: ставка ${formatRubDisplay(updated.packaging_rate_rub ?? '0')} ₽`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить ставку.')
    } finally {
      setRateBusyId(null)
    }
  }

  async function onAddressStorageToggle(checked: boolean) {
    if (!token || !isFulfillmentAdmin) {
      return
    }
    const previous = addressStorage
    setAddressStorage(checked)
    setAddressStorageBusy(true)
    setAddressStorageNotice(null)
    setError(null)
    try {
      const res = await fetch(apiUrl('/tenant/settings'), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ address_storage_enabled: checked }),
      })
      if (!res.ok) {
        setAddressStorage(previous)
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as { address_storage_enabled: boolean }
      setAddressStorage(data.address_storage_enabled)
      onAddressStorageChange?.(data.address_storage_enabled)
      if (data.address_storage_enabled) {
        setAddressStorageNotice({
          severity: 'success',
          message: 'Адресное хранение включено.',
          testId: 'ff-settings-address-storage-saved',
        })
      } else {
        setAddressStorageNotice({
          severity: 'info',
          message: 'Остатки с ячеек перенесены на зону сортировки.',
          testId: 'ff-settings-address-storage-migration-info',
        })
      }
    } catch (err) {
      setAddressStorage(previous)
      setError(err instanceof Error ? err.message : 'Не удалось сохранить настройку склада.')
    } finally {
      setAddressStorageBusy(false)
    }
  }

  async function onFbsCutoffSave(nextValue = fbsCutoff) {
    if (!token || !isFulfillmentAdmin) {
      return
    }
    const normalized = nextValue.trim()
    setFbsCutoffBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/tenant/settings'), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ fbs_shipment_cutoff_time: normalized || null }),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as { fbs_shipment_cutoff_time: string | null }
      setFbsCutoff(data.fbs_shipment_cutoff_time ?? '')
      setFbsCutoffSaved(data.fbs_shipment_cutoff_time ?? '')
      setSuccess(data.fbs_shipment_cutoff_time ? 'Время отсечки FBS сохранено' : 'Время отсечки FBS очищено')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить время отсечки FBS.')
    } finally {
      setFbsCutoffBusy(false)
    }
  }

  async function saveOwnProfile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!onProfileUpdated) return
    const fullName = profileFullName.trim()
    if (!fullName) {
      setError('Укажите ФИО.')
      return
    }
    setProfileBusy(true)
    setError(null)
    try {
      await onProfileUpdated({ full_name: fullName, job_title: profileJobTitle.trim() })
      setSuccess('Профиль сохранён')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить профиль.')
    } finally {
      setProfileBusy(false)
    }
  }

  function openStaffProfile(row: StaffAccountRow) {
    setEditingRow(row)
    setEditingFullName(row.full_name ?? '')
    setEditingJobTitle(row.job_title ?? '')
  }

  async function saveStaffProfile() {
    if (!editingRow) return
    const fullName = editingFullName.trim()
    if (!fullName) {
      setError('Укажите ФИО сотрудника.')
      return
    }
    setEditingBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/auth/staff-accounts/${editingRow.id}/profile`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName, job_title: editingJobTitle.trim() || null }),
      })
      if (!res.ok) throw new Error(humanStaffError(await readApiErrorMessage(res)))
      const updated = (await res.json()) as StaffAccountRow
      setRows((previous) => previous.map((row) => row.id === updated.id ? updated : row))
      setEditingRow(null)
      setSuccess('Данные сотрудника сохранены')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить сотрудника.')
    } finally {
      setEditingBusy(false)
    }
  }

  return (
    <Box data-testid="ff-settings-screen">
      <Typography variant="h5" gutterBottom>
        Настройки
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Склад, печать и сотрудники фулфилмента.
      </Typography>

      {isFulfillmentAdmin ? <FfLabelTemplatePanel token={token} /> : null}

      {me ? (
        <Paper variant="outlined" component="form" onSubmit={(e) => void saveOwnProfile(e)} sx={{ p: 2, mb: 3 }} data-testid="ff-own-profile-panel">
          <Typography variant="subtitle1" gutterBottom>Мой профиль</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { xs: 'stretch', sm: 'flex-start' } }}>
            <TextField label="ФИО" required value={profileFullName} onChange={(e) => setProfileFullName(e.target.value)} size="small" fullWidth slotProps={{ htmlInput: { 'data-testid': 'ff-own-profile-name' } }} />
            <TextField label="Должность" value={profileJobTitle} onChange={(e) => setProfileJobTitle(e.target.value)} size="small" fullWidth slotProps={{ htmlInput: { 'data-testid': 'ff-own-profile-title' } }} />
            <Button type="submit" variant="contained" disabled={profileBusy} sx={{ minWidth: { sm: 130 } }}>{profileBusy ? 'Сохранение…' : 'Сохранить'}</Button>
          </Stack>
          {!me.full_name ? <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Заполните профиль, чтобы входить по ФИО.</Typography> : null}
        </Paper>
      ) : null}

      {isFulfillmentAdmin ? (
        <Paper
          variant="outlined"
          sx={{ p: 2, mb: 3 }}
          data-testid="ff-settings-warehouse-panel"
        >
          <Typography variant="subtitle1" gutterBottom>
            Склад
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Адресное хранение: учёт остатков по ячейкам в приёмке и отгрузке на маркетплейс.
          </Typography>
          {addressStorageNotice ? (
            <Alert
              severity={addressStorageNotice.severity}
              sx={{ mb: 2 }}
              data-testid={addressStorageNotice.testId}
            >
              {addressStorageNotice.message}
            </Alert>
          ) : null}
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={addressStorage}
                  disabled={addressStorageBusy}
                  onChange={(e) => void onAddressStorageToggle(e.target.checked)}
                  data-testid="ff-settings-address-storage-enabled"
                />
              }
              label="Адресное хранение включено"
            />
            {addressStorageBusy ? <CircularProgress size={20} /> : null}
          </Stack>

          <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider' }} data-testid="cal-03-fbs-cutoff-section" data-task-id="CAL-03">
            {/* GLOBAL-02: заголовок секции несёт название, поле ниже подписано просто «Время» */}
            <Typography variant="subtitle2" gutterBottom data-task-id="CAL-03">
              Время отсечки FBS
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }} data-task-id="CAL-03">
              <TextField
                type="time"
                size="small"
                label="Время"
                value={fbsCutoff}
                onChange={(event) => setFbsCutoff(event.target.value)}
                disabled={fbsCutoffBusy}
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'cal-03-fbs-cutoff-time' },
                }}
                sx={{ width: { xs: '100%', sm: 180 } }}
                data-task-id="CAL-03"
              />
              <Button
                variant="outlined"
                onClick={() => void onFbsCutoffSave()}
                disabled={fbsCutoffBusy || fbsCutoff === fbsCutoffSaved}
                data-testid="cal-03-fbs-cutoff-save"
                data-task-id="CAL-03"
              >
                Сохранить
              </Button>
              <Button
                variant="text"
                onClick={() => {
                  setFbsCutoff('')
                  void onFbsCutoffSave('')
                }}
                disabled={fbsCutoffBusy || !fbsCutoff}
                data-testid="cal-03-fbs-cutoff-clear"
                data-task-id="CAL-03"
              >
                Очистить
              </Button>
              {fbsCutoffBusy ? <CircularProgress size={20} /> : null}
            </Stack>
          </Box>
        </Paper>
      ) : null}

      {!canManageStaff ? (
        <Alert severity="info" data-testid="ff-settings-users-admin-only">
          Нет доступа к сотрудникам.
        </Alert>
      ) : (
        <Box data-testid="ff-settings-users-panel">
          {error ? (
            <Alert severity="error" sx={{ mb: 2 }} data-testid="ff-settings-users-error">
              {error}
            </Alert>
          ) : null}
          {success ? (
            <Alert severity="success" sx={{ mb: 2 }} data-testid="ff-settings-users-success">
              {success}
            </Alert>
          ) : null}

          <Typography variant="subtitle2" gutterBottom data-testid="ff-settings-staff-heading">
            Сотрудники
          </Typography>

          <Stack spacing={2}>
            {isFulfillmentAdmin ? (
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                sx={{ alignItems: { xs: 'stretch', sm: 'center' } }}
              >
                <TextField
                  label="Месяц расчёта"
                  type="month"
                  size="small"
                  value={billingMonth}
                  onChange={(e) => setBillingMonth(e.target.value)}
                  slotProps={{
                    htmlInput: { 'data-testid': 'ff-staff-billing-month' },
                  }}
                  helperText="Период по московскому времени"
                  sx={{ width: { xs: '100%', sm: 220 } }}
                />
              </Stack>
            ) : null}

            {rows.length === 0 ? (
              <Paper
                variant="outlined"
                sx={{ py: 2.5, px: 2, textAlign: 'center' }}
                data-testid="ff-staff-empty"
              >
                <Typography variant="body2" color="text.secondary">
                  Сотрудников пока нет.
                </Typography>
              </Paper>
            ) : (
              <TableContainer
                component={Paper}
                variant="outlined"
                sx={{ width: '100%', overflowX: 'auto' }}
                data-testid="ff-staff-table-wrap"
              >
                <Table size="small" data-testid="ff-staff-table">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ minWidth: 220 }}>Сотрудник</TableCell>
                      {FF_STAFF_ACCESS_BLOCKS.map((block) => (
                        <TableCell key={block.key} align="center" sx={{ minWidth: 116 }}>
                          <Typography variant="caption" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                            {block.label}
                          </Typography>
                        </TableCell>
                      ))}
                      {isFulfillmentAdmin ? (
                        <>
                          <TableCell align="right" sx={{ minWidth: 120 }}>
                            Ставка за ед., ₽
                          </TableCell>
                          <TableCell align="right" sx={{ minWidth: 110 }}>
                            Упаковано, шт
                          </TableCell>
                          <TableCell align="right" sx={{ minWidth: 110 }}>
                            Начислено, ₽
                          </TableCell>
                        </>
                      ) : null}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => {
                      const access = ffPermissionsToStaffAccess(row.permissions)
                      return (
                        <TableRow
                          key={row.id}
                          hover
                          data-testid="ff-staff-row"
                          data-staff-id={row.id}
                          sx={
                            highlightRowId === row.id
                              ? { bgcolor: 'action.selected' }
                              : undefined
                          }
                        >
                          <TableCell sx={{ maxWidth: 320 }}>
                            <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>
                              {row.display_name}
                            </Typography>
                            {row.job_title ? <Typography variant="caption" color="text.secondary">{row.job_title}</Typography> : null}
                            <Button size="small" variant="text" onClick={() => openStaffProfile(row)} sx={{ px: 0, minWidth: 0 }}>Изменить</Button>
                            <Typography
                              variant="caption"
                              color={row.must_set_password ? 'warning.main' : 'text.secondary'}
                            >
                              {row.must_set_password ? 'ожидает первый вход' : 'сотрудник'}
                            </Typography>
                          </TableCell>
                          {FF_STAFF_ACCESS_BLOCKS.map((block) => (
                            <TableCell key={block.key} align="center" padding="checkbox">
                              <Checkbox
                                size="small"
                                checked={access[block.key]}
                                disabled={permBusyId === row.id}
                                slotProps={{
                                  root: {
                                    'data-testid': `ff-staff-access-${row.id}-${block.key}`,
                                  } as React.HTMLAttributes<HTMLSpanElement>,
                                  input: {
                                    'aria-label': `${block.label} для ${row.display_name}`,
                                  } as React.InputHTMLAttributes<HTMLInputElement>,
                                }}
                                onChange={(e) =>
                                  void onTogglePermission(row, block.key, e.target.checked)
                                }
                              />
                            </TableCell>
                          ))}
                          {isFulfillmentAdmin ? (
                            <>
                              <TableCell align="right">
                                <TextField
                                  size="small"
                                  type="number"
                                  inputMode="decimal"
                                  value={rateDrafts[row.id] ?? row.packaging_rate_rub ?? '0.00'}
                                  disabled={rateBusyId === row.id}
                                  onChange={(e) =>
                                    setRateDrafts((prev) => ({
                                      ...prev,
                                      [row.id]: e.target.value,
                                    }))
                                  }
                                  onBlur={() => {
                                    const draft = rateDrafts[row.id]
                                    if (draft !== undefined && draft !== row.packaging_rate_rub) {
                                      void savePackagingRate(row)
                                    }
                                  }}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      e.preventDefault()
                                      void savePackagingRate(row)
                                    }
                                  }}
                                  slotProps={{
                                    htmlInput: {
                                      'data-testid': `ff-staff-rate-${row.id}`,
                                      min: 0,
                                      step: 0.01,
                                      style: { textAlign: 'right' },
                                    },
                                  }}
                                  sx={{ width: 108 }}
                                />
                              </TableCell>
                              <TableCell align="right" data-testid={`ff-staff-units-${row.id}`}>
                                {row.packaging_billing?.units_packed ?? 0}
                              </TableCell>
                              <TableCell align="right" data-testid={`ff-staff-earned-${row.id}`}>
                                {formatRubDisplay(row.packaging_billing?.earned_rub ?? '0')}
                              </TableCell>
                            </>
                          ) : null}
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}

            <Paper
              variant="outlined"
              component="form"
              noValidate
              onSubmit={(e) => void onSubmit(e)}
              sx={{ p: 2 }}
              data-testid="ff-staff-create-panel"
            >
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
                Добавить пользователя
              </Typography>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                sx={{ alignItems: { xs: 'stretch', sm: 'flex-start' } }}
              >
                <TextField
                  name="staff_full_name"
                  label="ФИО"
                  required
                  fullWidth
                  size="small"
                  autoComplete="off"
                  slotProps={{ htmlInput: { 'data-testid': 'ff-staff-name' } }}
                  sx={{ flex: 1 }}
                />
                <TextField name="staff_job_title" label="Должность" fullWidth size="small" sx={{ flex: 1 }} />
                <TextField name="staff_password" label="Пароль" type="password" required fullWidth size="small" autoComplete="new-password" sx={{ flex: 1 }} />
                <Button
                  type="submit"
                  variant="contained"
                  disabled={busy}
                  data-testid="ff-staff-submit"
                  startIcon={busy ? <CircularProgress size={16} color="inherit" /> : null}
                  sx={{ minWidth: { sm: 140 }, mt: { xs: 0, sm: 0.5 } }}
                >
                  {busy ? 'Сохранение…' : 'Добавить'}
                </Button>
              </Stack>
            </Paper>
          </Stack>

          <Snackbar
            open={permSavedNotice !== null}
            autoHideDuration={2500}
            onClose={() => setPermSavedNotice(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
          >
            <Alert
              severity="success"
              variant="filled"
              onClose={() => setPermSavedNotice(null)}
              data-testid="ff-staff-perm-saved"
              sx={{ width: '100%' }}
            >
              {permSavedNotice}
            </Alert>
          </Snackbar>

          <Snackbar
            open={rateSavedNotice !== null}
            autoHideDuration={2500}
            onClose={() => setRateSavedNotice(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
          >
            <Alert
              severity="success"
              variant="filled"
              onClose={() => setRateSavedNotice(null)}
              data-testid="ff-staff-rate-saved"
              sx={{ width: '100%' }}
            >
              {rateSavedNotice}
            </Alert>
          </Snackbar>
        </Box>
      )}
      <FfSubscriptionPanel token={token} isFulfillmentAdmin={isFulfillmentAdmin} />
      {isFulfillmentAdmin ? <FfBillingTariffMatrixPanel token={token} authHeaders={authHeaders} focusTariffs={typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('tab') === 'tariffs'} onSaved={() => setSuccess('Тарифы сохранены')} employees={rows.map((row) => ({ id: row.id, display_name: row.display_name, packaging_rate_rub: row.packaging_rate_rub }))} /> : null}
      <Dialog open={editingRow !== null} onClose={() => !editingBusy && setEditingRow(null)} fullWidth maxWidth="xs">
        <DialogTitle>Данные сотрудника</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField autoFocus label="ФИО" required value={editingFullName} onChange={(e) => setEditingFullName(e.target.value)} />
            <TextField label="Должность" value={editingJobTitle} onChange={(e) => setEditingJobTitle(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setEditingRow(null)} disabled={editingBusy}>Отмена</Button><Button variant="contained" onClick={() => void saveStaffProfile()} disabled={editingBusy}>Сохранить</Button></DialogActions>
      </Dialog>
    </Box>
  )
}
