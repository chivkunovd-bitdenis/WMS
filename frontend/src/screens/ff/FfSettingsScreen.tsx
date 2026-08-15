import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
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
import {
  FF_STAFF_ACCESS_BLOCKS,
  applyFfStaffAccessChange,
  ffPermissionsToStaffAccess,
  type FfPermissions,
  type FfStaffAccessKey,
} from '../../utils/ffPermissions'
import { setSeparateMarkingPrintEnabled } from '../../utils/separateMarkingPrint'

type StaffPackagingBilling = {
  billing_month: string
  units_packed: number
  earned_rub: string
}

type StaffAccountRow = {
  id: string
  email: string
  role: string
  must_set_password: boolean
  permissions: FfPermissions
  packaging_rate_rub?: string
  packaging_billing?: StaffPackagingBilling
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
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
  isFulfillmentAdmin,
  canManageStaff,
  addressStorageEnabled = true,
  onAddressStorageChange,
  separateMarkingPrintEnabled = false,
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
  const [separatePrint, setSeparatePrint] = useState(separateMarkingPrintEnabled)
  const [separatePrintBusy, setSeparatePrintBusy] = useState(false)
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
    setSeparatePrint(separateMarkingPrintEnabled)
  }, [separateMarkingPrintEnabled])

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
      const email = String(fd.get('staff_email') ?? '').trim()
      if (!email) {
        setError('Укажите email сотрудника.')
        return
      }
      const res = await fetch(apiUrl('/auth/staff-accounts'), {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
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
      setRateSavedNotice(`${row.email}: ставка ${formatRubDisplay(updated.packaging_rate_rub ?? '0')} ₽`)
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

  async function onSeparatePrintToggle(checked: boolean) {
    if (!token || !isFulfillmentAdmin) {
      return
    }
    const previous = separatePrint
    setSeparatePrint(checked)
    setSeparatePrintBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/tenant/settings'), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ separate_marking_print_enabled: checked }),
      })
      if (!res.ok) {
        setSeparatePrint(previous)
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as { separate_marking_print_enabled: boolean }
      setSeparatePrint(data.separate_marking_print_enabled)
      setSeparateMarkingPrintEnabled(data.separate_marking_print_enabled)
    } catch (err) {
      setSeparatePrint(previous)
      setError(err instanceof Error ? err.message : 'Не удалось сохранить настройку печати.')
    } finally {
      setSeparatePrintBusy(false)
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

  return (
    <Box data-testid="ff-settings-screen">
      <Typography variant="h5" gutterBottom>
        Настройки
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Сотрудники фулфилмента и доступ к рабочим разделам.
      </Typography>

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

          <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              В модалках печати — отдельные кнопки для ЧЗ и ШК ВБ со своими размерами этикеток (для складов, где ЧЗ и ШК печатаются на разных лентах).
            </Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={separatePrint}
                    disabled={separatePrintBusy}
                    onChange={(e) => void onSeparatePrintToggle(e.target.checked)}
                    data-testid="ff-settings-separate-marking-print"
                  />
                }
                label="Раздельная печать ЧЗ и ШК ВБ"
              />
              {separatePrintBusy ? <CircularProgress size={20} /> : null}
            </Stack>
          </Box>

          <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider' }} data-testid="cal-03-fbs-cutoff-section">
            <Typography variant="subtitle2" gutterBottom>
              Время отсечки FBS
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
              <TextField
                type="time"
                size="small"
                label="Время отсечки FBS"
                value={fbsCutoff}
                onChange={(event) => setFbsCutoff(event.target.value)}
                disabled={fbsCutoffBusy}
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: { 'data-testid': 'cal-03-fbs-cutoff-time' },
                }}
                sx={{ width: { xs: '100%', sm: 180 } }}
              />
              <Button
                variant="outlined"
                onClick={() => void onFbsCutoffSave()}
                disabled={fbsCutoffBusy || fbsCutoff === fbsCutoffSaved}
                data-testid="cal-03-fbs-cutoff-save"
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
	                      <TableCell sx={{ minWidth: 220 }}>Email</TableCell>
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
                              {row.email}
                            </Typography>
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
                                    'aria-label': `${block.label} для ${row.email}`,
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
                  name="staff_email"
                  label="Email для входа"
                  type="email"
                  required
                  fullWidth
                  size="small"
                  autoComplete="off"
                  helperText="Пароль задаётся при первом входе"
                  slotProps={{ htmlInput: { 'data-testid': 'ff-staff-email' } }}
                  sx={{ flex: 1 }}
                />
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
    </Box>
  )
}
