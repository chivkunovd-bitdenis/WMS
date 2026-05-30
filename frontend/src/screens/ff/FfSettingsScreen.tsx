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

type StaffAccountRow = {
  id: string
  email: string
  role: string
  must_set_password: boolean
  permissions: FfPermissions
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  isFulfillmentAdmin: boolean
}

export function FfSettingsScreen({ token, authHeaders, isFulfillmentAdmin }: Props) {
  const [rows, setRows] = useState<StaffAccountRow[]>([])
  const [busy, setBusy] = useState(false)
  const [permBusyId, setPermBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [permSavedNotice, setPermSavedNotice] = useState<string | null>(null)
  const [highlightRowId, setHighlightRowId] = useState<string | null>(null)

  const loadRows = useCallback(async () => {
    if (!token || !isFulfillmentAdmin) {
      return
    }
    const res = await fetch(apiUrl('/auth/staff-accounts'), {
      headers: authHeaders(token),
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    setRows((await res.json()) as StaffAccountRow[])
  }, [authHeaders, isFulfillmentAdmin, token])

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

  return (
    <Box data-testid="ff-settings-screen">
      <Typography variant="h5" gutterBottom>
        Настройки
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Сотрудники фулфилмента и доступ к разделам портала.
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
        </Box>
      )}
    </Box>
  )
}
