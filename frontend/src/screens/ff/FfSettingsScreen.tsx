import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  Paper,
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

function FfSettingsUsersPanel({ token, authHeaders, isFulfillmentAdmin }: Props) {
  const [rows, setRows] = useState<StaffAccountRow[]>([])
  const [busy, setBusy] = useState(false)
  const [permBusyId, setPermBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

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
      form.reset()
      await loadRows()
      setSuccess(
        `Сотрудник ${email} добавлен. Первый вход: пароль пустой — система попросит задать новый.`,
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
    setSuccess(null)
    setPermBusyId(row.id)
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить права.')
    } finally {
      setPermBusyId(null)
    }
  }

  if (!isFulfillmentAdmin) {
    return (
      <Alert severity="info" data-testid="ff-settings-users-admin-only">
        Управление пользователями доступно только администратору фулфилмента.
      </Alert>
    )
  }

  return (
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

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <TableContainer
          component={Paper}
          variant="outlined"
          sx={{ flex: 1, width: '100%', overflowX: 'auto' }}
          data-testid="ff-staff-table-wrap"
        >
          <Table size="small" data-testid="ff-staff-table">
            <TableHead>
              <TableRow>
                <TableCell>Email</TableCell>
                {FF_PERMISSION_BLOCKS.map((block) => (
                  <TableCell key={block.key} align="center">
                    {block.label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id} hover data-testid="ff-staff-row" data-staff-id={row.id}>
                  <TableCell>
                    <Typography variant="body2">{row.email}</Typography>
                    {row.must_set_password ? (
                      <Typography variant="caption" color="text.secondary">
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
                        onChange={(e) => void onTogglePermission(row, block.key, e.target.checked)}
                      />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={1 + FF_PERMISSION_BLOCKS.length}>
                    <Typography variant="body2" color="text.secondary" data-testid="ff-staff-empty">
                      Пока нет сотрудников. Добавьте первого в форме справа.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>

        <Paper
          variant="outlined"
          component="form"
          noValidate
          onSubmit={(e) => void onSubmit(e)}
          sx={{ p: 2, width: { xs: '100%', lg: 320 } }}
          data-testid="ff-staff-create-panel"
        >
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }} gutterBottom>
            Добавить пользователя
          </Typography>
          <Stack spacing={2}>
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
            />
            <Button
              type="submit"
              variant="contained"
              disabled={busy}
              data-testid="ff-staff-submit"
              startIcon={busy ? <CircularProgress size={16} color="inherit" /> : null}
            >
              {busy ? 'Сохранение…' : 'Добавить'}
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Box>
  )
}

function FfSettingsOverview() {
  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-settings-overview">
      <Typography variant="body2" color="text.secondary">
        Общие настройки организации появятся здесь позже.
      </Typography>
    </Paper>
  )
}

export function FfSettingsScreen({ token, authHeaders, isFulfillmentAdmin }: Props) {
  return (
    <Box data-testid="ff-settings-screen">
      <Typography variant="h5" gutterBottom>
        Настройки
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Пользователи фулфилмента и права доступа к разделам портала.
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Paper variant="outlined" sx={{ width: { xs: '100%', md: 220 }, flexShrink: 0 }}>
          <List dense aria-label="Подразделы настроек">
            <ListItemButton
              component={NavLink}
              to="users"
              data-testid="ff-settings-nav-users"
              sx={{
                '&.active': (theme) => ({
                  bgcolor: theme.palette.action.selected,
                }),
              }}
            >
              <ListItemText primary="Пользователи" />
            </ListItemButton>
          </List>
        </Paper>

        <Box sx={{ flex: 1, width: '100%' }}>
          <Routes>
            <Route
              index
              element={
                isFulfillmentAdmin ? (
                  <FfSettingsUsersPanel
                    token={token}
                    authHeaders={authHeaders}
                    isFulfillmentAdmin={isFulfillmentAdmin}
                  />
                ) : (
                  <FfSettingsOverview />
                )
              }
            />
            <Route
              path="users"
              element={
                <FfSettingsUsersPanel
                  token={token}
                  authHeaders={authHeaders}
                  isFulfillmentAdmin={isFulfillmentAdmin}
                />
              }
            />
          </Routes>
        </Box>
      </Stack>
    </Box>
  )
}
