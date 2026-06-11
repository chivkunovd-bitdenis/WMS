import { useCallback, useEffect, useState, type FormEvent } from 'react'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
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
  Tooltip,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { FF_PERMISSION_BLOCKS, type FfPermissions } from '../../utils/ffPermissions'

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
  packaging_rate_rub: string
  packaging_billing: StaffPackagingBilling
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  isFulfillmentAdmin: boolean
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

export function FfSettingsScreen({ token, authHeaders, isFulfillmentAdmin }: Props) {
  const [rows, setRows] = useState<StaffAccountRow[]>([])
  const [billingMonth, setBillingMonth] = useState(currentBillingMonth)
  const [busy, setBusy] = useState(false)
  const [permBusyId, setPermBusyId] = useState<string | null>(null)
  const [rateBusyId, setRateBusyId] = useState<string | null>(null)
  const [rateDrafts, setRateDrafts] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [permSavedNotice, setPermSavedNotice] = useState<string | null>(null)
  const [rateSavedNotice, setRateSavedNotice] = useState<string | null>(null)
  const [highlightRowId, setHighlightRowId] = useState<string | null>(null)

  const loadRows = useCallback(async () => {
    if (!token || !isFulfillmentAdmin) {
      return
    }
    const params = new URLSearchParams({ billing_month: billingMonth })
    const res = await fetch(apiUrl(`/auth/staff-accounts?${params.toString()}`), {
      headers: authHeaders(token),
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    const data = (await res.json()) as StaffAccountRow[]
    setRows(data)
    setRateDrafts(
      Object.fromEntries(data.map((row) => [row.id, row.packaging_rate_rub])),
    )
  }, [authHeaders, billingMonth, isFulfillmentAdmin, token])

  useEffect(() => {
    void loadRows().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить пользователей.')
    })
  }, [loadRows])

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
    if (!token || !isFulfillmentAdmin) {
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
        setError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as StaffAccountRow
      form.reset()
      await loadRows()
      setHighlightRowId(created.id)
      setSuccess(
        `Сотрудник ${email} добавлен. Передайте ему email и адрес портала. Первый вход — с пустым паролем, система попросит задать новый.`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось добавить сотрудника.')
    } finally {
      setBusy(false)
    }
  }

  async function onTogglePermission(
    row: StaffAccountRow,
    key: keyof FfPermissions,
    checked: boolean,
  ) {
    if (!token || !isFulfillmentAdmin) {
      return
    }
    setError(null)
    setPermBusyId(row.id)
    const block = FF_PERMISSION_BLOCKS.find((b) => b.key === key)
    const next: FfPermissions = { ...row.permissions, [key]: checked }
    try {
      const res = await fetch(apiUrl(`/auth/staff-accounts/${row.id}/permissions`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const updated = (await res.json()) as StaffAccountRow
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      setPermSavedNotice(
        `${row.email}: «${block?.label ?? key}» ${checked ? 'включено' : 'выключено'}`,
      )
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
        setError(await readApiErrorMessage(res))
        return
      }
      const updated = (await res.json()) as StaffAccountRow
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      setRateDrafts((prev) => ({ ...prev, [row.id]: updated.packaging_rate_rub }))
      setRateSavedNotice(`${row.email}: ставка ${formatRubDisplay(updated.packaging_rate_rub)} ₽`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить ставку.')
    } finally {
      setRateBusyId(null)
    }
  }

  return (
    <Box data-testid="ff-settings-screen">
      <Typography variant="h5" gutterBottom>
        Настройки
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Сотрудники фулфилмента, доступ к разделам и расчёт зарплаты за упаковку.
      </Typography>

      {!isFulfillmentAdmin ? (
        <Alert severity="info" data-testid="ff-settings-users-admin-only">
          Управление пользователями доступно только администратору фулфилмента.
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

            {rows.length === 0 ? (
              <Paper
                variant="outlined"
                sx={{ py: 4, px: 2, textAlign: 'center' }}
                data-testid="ff-staff-empty"
              >
                <Typography variant="subtitle1" gutterBottom>
                  Пока нет сотрудников
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Добавьте первого пользователя в форме ниже — укажите email для входа в портал.
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
                      <TableCell sx={{ minWidth: 200 }}>Email</TableCell>
                      {FF_PERMISSION_BLOCKS.map((block) => (
                        <TableCell key={block.key} align="center" sx={{ minWidth: 88 }}>
                          <Tooltip title={block.hint} arrow placement="top">
                            <Stack
                              direction="row"
                              spacing={0.25}
                              sx={{ alignItems: 'center', justifyContent: 'center' }}
                            >
                              <Typography variant="caption" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                                {block.label}
                              </Typography>
                              <InfoOutlinedIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                            </Stack>
                          </Tooltip>
                        </TableCell>
                      ))}
                      <TableCell align="right" sx={{ minWidth: 120 }}>
                        Ставка за ед., ₽
                      </TableCell>
                      <TableCell align="right" sx={{ minWidth: 110 }}>
                        Упаковано, шт
                      </TableCell>
                      <TableCell align="right" sx={{ minWidth: 110 }}>
                        Начислено, ₽
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((row) => (
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
                        <TableCell>
                          <Typography variant="body2">{row.email}</Typography>
                          {row.must_set_password ? (
                            <Typography variant="caption" color="warning.main">
                              ожидает первый вход
                            </Typography>
                          ) : null}
                        </TableCell>
                        {FF_PERMISSION_BLOCKS.map((block) => (
                          <TableCell key={block.key} align="center" padding="checkbox">
                            <Checkbox
                              size="small"
                              checked={row.permissions[block.key]}
                              disabled={permBusyId === row.id}
                              slotProps={{
                                root: {
                                  'data-testid': `ff-staff-perm-${row.id}-${block.key}`,
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
                        <TableCell align="right">
                          <TextField
                            size="small"
                            type="number"
                            inputMode="decimal"
                            value={rateDrafts[row.id] ?? row.packaging_rate_rub}
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
                          {row.packaging_billing.units_packed}
                        </TableCell>
                        <TableCell align="right" data-testid={`ff-staff-earned-${row.id}`}>
                          {formatRubDisplay(row.packaging_billing.earned_rub)}
                        </TableCell>
                      </TableRow>
                    ))}
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
                  helperText="Пароль не задаётся: при первом входе сотрудник создаст его сам"
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
