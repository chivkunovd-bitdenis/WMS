import { useEffect, useState, type FormEvent } from 'react'
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
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
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
  SELLER_PERMISSION_BLOCKS,
  type SellerPermissions,
} from '../../utils/sellerPermissions'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  permissions: SellerPermissions
  onStaffChanged?: () => void | Promise<void>
}

type MarkingCredentialsState = {
  has_cz_token: boolean
  has_suz_oms_token: boolean
  has_mp_api_key: boolean
  marketplace: string | null
  mchd_id: string | null
  mchd_valid_until: string | null
  signing_method: string
  edo_route: string
  auto_introduce: boolean
  auto_emit_limit: number | null
}

type SellerStaffAccountRow = {
  id: string
  email: string
  role: string
  seller_id: string
  must_set_password: boolean
  is_owner: boolean
  permissions: SellerPermissions
}

const DEFAULT_STAFF_PERMISSIONS: SellerPermissions = {
  documents: true,
  products: true,
  honest_sign: true,
  settings: false,
  staff: false,
}

const SIGNING_OPTIONS = [
  { value: 'manual', label: 'Вручную в кабинете' },
  { value: 'ff_kep_mchd', label: 'КЭП фулфилмента + МЧД' },
  { value: 'seller_cloud', label: 'Облачная подпись селлера' },
] as const

const EDO_OPTIONS = [
  { value: 'edo_light_roaming_diadoc', label: 'ЭДО Лайт → роуминг в Диадок' },
  { value: 'diadoc_direct', label: 'Диадок напрямую' },
] as const

const MARKETPLACE_OPTIONS = [
  { value: 'wildberries', label: 'Wildberries' },
  { value: 'ozon', label: 'Ozon' },
] as const

function humanSellerStaffError(message: string): string {
  if (message.includes('Этот сотрудник уже добавлен') || message.includes('email_taken')) {
    return 'Этот сотрудник уже добавлен'
  }
  if (message.includes('Нет доступа') || message.includes('forbidden') || message.includes('seller_not_linked')) {
    return 'Нет доступа к сотрудникам'
  }
  if (
    message.includes('Сотрудник не найден') ||
    message.includes('not_seller_user') ||
    message.includes('user_not_found')
  ) {
    return 'Сотрудник не найден'
  }
  if (message.includes('owner_protected')) {
    return 'Нельзя снять последний полный доступ к кабинету'
  }
  if (message.includes('self_update_forbidden')) {
    return 'Нельзя изменить собственный доступ'
  }
  return message || 'Не удалось сохранить. Попробуйте еще раз'
}

export function SellerSettingsScreen({
  token,
  authHeaders,
  permissions,
  onStaffChanged,
}: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [okMsg, setOkMsg] = useState<string | null>(null)
  const [contentKey, setContentKey] = useState('')
  const [hasContentKey, setHasContentKey] = useState<boolean | null>(null)
  const [wbCardsCount, setWbCardsCount] = useState<number | null>(null)

  const [czCreds, setCzCreds] = useState<MarkingCredentialsState | null>(null)
  const [czDialogOpen, setCzDialogOpen] = useState(false)
  const [czToken, setCzToken] = useState('')
  const [suzToken, setSuzToken] = useState('')
  const [mpKey, setMpKey] = useState('')
  const [mchdId, setMchdId] = useState('')
  const [mchdUntil, setMchdUntil] = useState('')
  const [signingMethod, setSigningMethod] = useState('manual')
  const [edoRoute, setEdoRoute] = useState('edo_light_roaming_diadoc')
  const [marketplace, setMarketplace] = useState('wildberries')
  const [autoIntroduce, setAutoIntroduce] = useState(false)
  const [autoEmitLimit, setAutoEmitLimit] = useState('')
  const [staffRows, setStaffRows] = useState<SellerStaffAccountRow[]>([])
  const [staffBusy, setStaffBusy] = useState(false)
  const [staffPermBusyId, setStaffPermBusyId] = useState<string | null>(null)
  const [staffError, setStaffError] = useState<string | null>(null)
  const [staffOk, setStaffOk] = useState<string | null>(null)
  const [staffCreatePerms, setStaffCreatePerms] = useState<SellerPermissions>(
    DEFAULT_STAFF_PERMISSIONS,
  )

  useEffect(() => {
    if (!permissions.settings) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(apiUrl('/integrations/wildberries/self/tokens'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          return
        }
        const j = (await res.json()) as { has_content_token: boolean }
        if (!cancelled) {
          setHasContentKey(Boolean(j.has_content_token))
        }
      } catch {
        // ignore
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, permissions.settings, token])

  async function loadMarkingCredentials(): Promise<void> {
    try {
      const res = await fetch(apiUrl('/operations/marking-codes/self/credentials'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        return
      }
      const j = (await res.json()) as MarkingCredentialsState
      setCzCreds(j)
      setMchdId(j.mchd_id ?? '')
      setMchdUntil(j.mchd_valid_until ?? '')
      setSigningMethod(j.signing_method)
      setEdoRoute(j.edo_route)
      setMarketplace(j.marketplace ?? 'wildberries')
      setAutoIntroduce(j.auto_introduce)
      setAutoEmitLimit(j.auto_emit_limit != null ? String(j.auto_emit_limit) : '')
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!permissions.settings) {
      return
    }
    void loadMarkingCredentials()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when token changes
  }, [permissions.settings, token])

  async function loadStaffRows(): Promise<void> {
    if (!permissions.staff) {
      return
    }
    const res = await fetch(apiUrl('/auth/seller-staff-accounts'), {
      headers: { ...authHeaders(token) },
    })
    if (!res.ok) {
      throw new Error(humanSellerStaffError(await readApiErrorMessage(res)))
    }
    setStaffRows((await res.json()) as SellerStaffAccountRow[])
  }

  useEffect(() => {
    if (!permissions.staff) {
      setStaffRows([])
      return
    }
    void loadStaffRows().catch((e: unknown) => {
      setStaffError(e instanceof Error ? e.message : 'Не удалось загрузить сотрудников.')
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when permission or token changes
  }, [permissions.staff, token])

  async function refreshWbCardsCount(): Promise<void> {
    try {
      const res = await fetch(apiUrl('/products/wb-catalog'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        return
      }
      const rows = (await res.json()) as unknown[]
      setWbCardsCount(Array.isArray(rows) ? rows.length : null)
    } catch {
      // ignore
    }
  }

  async function onSave() {
    setError(null)
    setOkMsg(null)
    const trimmed = contentKey.trim()
    if (!trimmed) {
      setError('Введите API ключ.')
      return
    }
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/wildberries/self/content-token'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content_api_token: trimmed }),
      })
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        setError(
          msg.includes('invalid_wb_token')
            ? 'Этот API ключ не подходит (проверка WB не прошла).'
            : msg,
        )
        return
      }
      const j = (await res.json()) as {
        validation_ok?: boolean
        validation_error?: string | null
        cards_received?: number
        cards_saved?: number
      }
      setOpen(false)
      setContentKey('')
      setHasContentKey(true)
      await refreshWbCardsCount()
      if (j.validation_ok === false) {
        if (j.validation_error === 'missing_marketplace_scope') {
          setOkMsg(
            'Ключ сохранён только для карточек WB. В ключе нет прав на «Маркетплейс»: включите эту категорию в кабинете WB и сохраните ключ заново.',
          )
        } else {
          setOkMsg(
            `Ключ сохранён. Проверка WB сейчас не прошла (${j.validation_error ?? 'transport_error'}).`,
          )
        }
      } else {
        setOkMsg(
          `Ключ сохранён. Проверка WB прошла (карточек получено: ${j.cards_received ?? 0}, сохранено: ${j.cards_saved ?? 0}).`,
        )
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить ключ.')
    } finally {
      setBusy(false)
    }
  }

  async function onSyncNow() {
    setError(null)
    setOkMsg(null)
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/wildberries/self/sync-products'), {
        method: 'POST',
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const j = (await res.json()) as {
        cards_received?: number
        cards_saved?: number
        products_created?: number
        products_updated?: number
      }
      await refreshWbCardsCount()
      setOkMsg(
        `Синхронизация выполнена. WB карточек: ${j.cards_received ?? 0} (сохранено: ${j.cards_saved ?? 0}), ` +
          `товаров: +${j.products_created ?? 0} / обновлено: ${j.products_updated ?? 0}.`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось запустить синхронизацию.')
    } finally {
      setBusy(false)
    }
  }

  async function onSaveMarkingCredentials() {
    setError(null)
    setOkMsg(null)
    setBusy(true)
    try {
      const body: Record<string, unknown> = {
        mchd_id: mchdId.trim() || null,
        mchd_valid_until: mchdUntil.trim() || null,
        signing_method: signingMethod,
        edo_route: edoRoute,
        marketplace,
        auto_introduce: autoIntroduce,
        auto_emit_limit: autoEmitLimit.trim() ? Number(autoEmitLimit) : null,
      }
      if (czToken.trim()) {
        body.cz_token = czToken.trim()
      }
      if (suzToken.trim()) {
        body.suz_oms_token = suzToken.trim()
      }
      if (mpKey.trim()) {
        body.mp_api_key = mpKey.trim()
      }
      const res = await fetch(apiUrl('/operations/marking-codes/self/credentials'), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setCzDialogOpen(false)
      setCzToken('')
      setSuzToken('')
      setMpKey('')
      await loadMarkingCredentials()
      setOkMsg('Настройки Честного Знака сохранены.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить настройки.')
    } finally {
      setBusy(false)
    }
  }

  async function onCreateStaff(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    const form = e.currentTarget
    const fd = new FormData(form)
    const email = String(fd.get('seller_staff_email') ?? '').trim()
    if (!email) {
      setStaffError('Укажите email сотрудника.')
      return
    }
    setStaffBusy(true)
    setStaffError(null)
    setStaffOk(null)
    try {
      const res = await fetch(apiUrl('/auth/seller-staff-accounts'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, permissions: staffCreatePerms }),
      })
      if (!res.ok) {
        setStaffError(humanSellerStaffError(await readApiErrorMessage(res)))
        return
      }
      form.reset()
      setStaffCreatePerms(DEFAULT_STAFF_PERMISSIONS)
      await loadStaffRows()
      await onStaffChanged?.()
      setStaffOk('Сотрудник добавлен')
    } catch (e) {
      setStaffError(e instanceof Error ? e.message : 'Не удалось добавить сотрудника.')
    } finally {
      setStaffBusy(false)
    }
  }

  async function onToggleStaffPermission(
    row: SellerStaffAccountRow,
    key: keyof SellerPermissions,
    checked: boolean,
  ): Promise<void> {
    if (row.is_owner) {
      return
    }
    const next: SellerPermissions = { ...row.permissions, [key]: checked }
    setStaffPermBusyId(row.id)
    setStaffError(null)
    setStaffOk(null)
    try {
      const res = await fetch(apiUrl(`/auth/seller-staff-accounts/${row.id}/permissions`), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(next),
      })
      if (!res.ok) {
        setStaffError(humanSellerStaffError(await readApiErrorMessage(res)))
        return
      }
      const updated = (await res.json()) as SellerStaffAccountRow
      setStaffRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      await onStaffChanged?.()
      setStaffOk('Права сохранены')
    } catch (e) {
      setStaffError(e instanceof Error ? e.message : 'Не удалось сохранить права.')
    } finally {
      setStaffPermBusyId(null)
    }
  }

  const signingLabel =
    SIGNING_OPTIONS.find((o) => o.value === czCreds?.signing_method)?.label ?? '—'

  return (
    <Box data-testid="seller-settings-root">
      <Typography variant="h5" gutterBottom>
        Настройки
      </Typography>

      {okMsg ? (
        <Alert severity="success" sx={{ mb: 2 }} data-testid="seller-settings-ok">
          {okMsg}
        </Alert>
      ) : null}
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-settings-error">
          {error}
        </Alert>
      ) : null}

      {permissions.staff ? (
        <Paper
          variant="outlined"
          sx={{ p: 2, maxWidth: 920, mb: 2 }}
          data-testid="seller-staff-panel"
        >
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6">Сотрудники селлера</Typography>
              <Typography variant="body2" color="text.secondary">
                Пользователи этого селлера и доступ к разделам личного кабинета.
              </Typography>
            </Box>
            {staffError ? (
              <Alert severity="error" data-testid="seller-staff-error">
                {staffError}
              </Alert>
            ) : null}
            {staffOk ? (
              <Alert severity="success" data-testid="seller-staff-ok">
                {staffOk}
              </Alert>
            ) : null}
            <TableContainer
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                overflowX: 'auto',
              }}
              data-testid="seller-staff-table-wrap"
            >
              <Table size="small" data-testid="seller-staff-table">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ minWidth: 220 }}>Email</TableCell>
                    {SELLER_PERMISSION_BLOCKS.map((block) => (
                      <TableCell key={block.key} align="center" sx={{ minWidth: 104 }}>
                        {block.label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {staffRows.map((row) => (
                    <TableRow
                      key={row.id}
                      hover
                      data-testid="seller-staff-row"
                      data-staff-id={row.id}
                    >
                      <TableCell>
                        <Typography variant="body2">{row.email}</Typography>
                        <Typography
                          variant="caption"
                          color={row.is_owner ? 'text.secondary' : 'warning.main'}
                        >
                          {row.is_owner
                            ? 'владелец селлера'
                            : row.must_set_password
                              ? 'ожидает первый вход'
                              : 'сотрудник'}
                        </Typography>
                      </TableCell>
                      {SELLER_PERMISSION_BLOCKS.map((block) => (
                        <TableCell key={block.key} align="center" padding="checkbox">
                          <Checkbox
                            size="small"
                            checked={row.permissions[block.key]}
                            disabled={row.is_owner || staffPermBusyId === row.id}
                            slotProps={{
                              root: {
                                'data-testid': `seller-staff-perm-${row.id}-${block.key}`,
                              } as React.HTMLAttributes<HTMLSpanElement>,
                              input: {
                                'aria-label': `${block.label} для ${row.email}`,
                              } as React.InputHTMLAttributes<HTMLInputElement>,
                            }}
                            onChange={(e) =>
                              void onToggleStaffPermission(row, block.key, e.target.checked)
                            }
                          />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                  {staffRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={SELLER_PERMISSION_BLOCKS.length + 1}>
                        <Typography variant="body2" color="text.secondary">
                          Пока нет сотрудников.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>

            <Box
              component="form"
              noValidate
              onSubmit={(e) => void onCreateStaff(e)}
              data-testid="seller-staff-create-form"
              sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 2 }}
            >
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Добавить сотрудника
                </Typography>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1.5}
                  sx={{ alignItems: { xs: 'stretch', sm: 'flex-start' } }}
                >
                  <TextField
                    name="seller_staff_email"
                    label="Email для входа"
                    type="email"
                    required
                    fullWidth
                    size="small"
                    autoComplete="off"
                    helperText="Пароль задаётся при первом входе"
                    slotProps={{ htmlInput: { 'data-testid': 'seller-staff-email' } }}
                    sx={{ flex: 1 }}
                  />
                  <Button
                    type="submit"
                    variant="contained"
                    disabled={staffBusy}
                    data-testid="seller-staff-submit"
                    startIcon={staffBusy ? <CircularProgress size={16} color="inherit" /> : null}
                    sx={{ minWidth: { sm: 140 }, mt: { xs: 0, sm: 0.5 } }}
                  >
                    {staffBusy ? 'Сохранение…' : 'Добавить'}
                  </Button>
                </Stack>
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
                  {SELLER_PERMISSION_BLOCKS.map((block) => (
                    <FormControlLabel
                      key={block.key}
                      control={
                        <Checkbox
                          size="small"
                          checked={staffCreatePerms[block.key]}
                          onChange={(e) =>
                            setStaffCreatePerms((prev) => ({
                              ...prev,
                              [block.key]: e.target.checked,
                            }))
                          }
                          data-testid={`seller-staff-create-perm-${block.key}`}
                        />
                      }
                      label={block.label}
                    />
                  ))}
                </Stack>
              </Stack>
            </Box>
          </Stack>
        </Paper>
      ) : null}

      {permissions.settings ? (
        <>
      <Paper variant="outlined" sx={{ p: 2, maxWidth: 720, mb: 2 }} data-testid="seller-settings-wb-card">
        <Stack spacing={1.5}>
          <Typography variant="h6">Wildberries</Typography>
          <Typography variant="body2" color="text.secondary">
            Добавь API ключ WB, чтобы подтягивать карточки товаров и ШК (баркоды).
          </Typography>
          <Divider />
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary">
              Ключ:
            </Typography>
            <Typography
              variant="body2"
              sx={{ color: hasContentKey ? 'text.secondary' : 'text.disabled' }}
              data-testid="seller-settings-key-status"
            >
              {hasContentKey ? 'добавлен' : hasContentKey === false ? 'не добавлен' : '—'}
            </Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Typography variant="body2" color="text.secondary" data-testid="seller-settings-wb-count">
              WB товары: {wbCardsCount ?? '—'}
            </Typography>
          </Stack>
          <Box>
            <Button
              variant="contained"
              onClick={() => setOpen(true)}
              disabled={busy}
              data-testid="seller-settings-add-key"
            >
              {hasContentKey ? 'Заменить ключ' : 'Добавить ключ'}
            </Button>
            <Button
              sx={{ ml: 1 }}
              variant="outlined"
              onClick={() => void onSyncNow()}
              disabled={busy || !hasContentKey}
              data-testid="seller-settings-sync-products"
            >
              Синхронизировать товары
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Paper
        variant="outlined"
        sx={{ p: 2, maxWidth: 720 }}
        data-testid="seller-settings-marking-card"
      >
        <Stack spacing={1.5}>
          <Typography variant="h6">Честный Знак — интеграция</Typography>
          <Typography variant="body2" color="text.secondary">
            Токены ГИС МТ/СУЗ, способ подписи, МЧД и маршрут ЭДО для авто-ввода в оборот и передачи
            кодов на маркетплейс.
          </Typography>
          <Divider />
          <Stack spacing={0.5}>
            <Typography variant="body2" data-testid="seller-settings-cz-signing">
              Подпись: {signingLabel}
            </Typography>
            <Typography variant="body2" data-testid="seller-settings-cz-tokens">
              Токены: ЧЗ {czCreds?.has_cz_token ? '✓' : '—'} · СУЗ {czCreds?.has_suz_oms_token ? '✓' : '—'} ·
              МП {czCreds?.has_mp_api_key ? '✓' : '—'}
            </Typography>
            <Typography variant="body2" color="text.secondary" data-testid="seller-settings-cz-auto">
              Авто-ввод: {czCreds?.auto_introduce ? 'вкл' : 'выкл'}
              {czCreds?.auto_emit_limit != null ? ` · лимит эмиссии: ${czCreds.auto_emit_limit}` : ''}
            </Typography>
          </Stack>
          <Box>
            <Button
              variant="contained"
              onClick={() => setCzDialogOpen(true)}
              disabled={busy}
              data-testid="seller-settings-cz-edit"
            >
              Настроить интеграцию
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Dialog
        open={open}
        onClose={() => (busy ? undefined : setOpen(false))}
        fullWidth
        maxWidth="sm"
        data-testid="seller-settings-key-dialog"
      >
        <DialogTitle>WB API ключ</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="WB API ключ"
              value={contentKey}
              onChange={(e) => setContentKey(e.target.value)}
              fullWidth
              disabled={busy}
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-key-input' } }}
              placeholder={hasContentKey ? 'ключ уже добавлен (вставь новый, чтобы заменить)' : undefined}
            />
            <Typography variant="body2" color="text.secondary">
              При сохранении мы проверим ключ запросом к WB и попробуем получить список карточек.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} disabled={busy} data-testid="seller-settings-cancel">
            Отмена
          </Button>
          <Button variant="contained" onClick={() => void onSave()} disabled={busy} data-testid="seller-settings-save">
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={czDialogOpen}
        onClose={() => (busy ? undefined : setCzDialogOpen(false))}
        fullWidth
        maxWidth="sm"
        data-testid="seller-settings-cz-dialog"
      >
        <DialogTitle>Интеграция Честного Знака</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControl fullWidth data-testid="seller-settings-cz-signing-control">
              <InputLabel id="cz-signing-label">Способ подписи</InputLabel>
              <Select
                labelId="cz-signing-label"
                label="Способ подписи"
                value={signingMethod}
                onChange={(e) => setSigningMethod(e.target.value)}
                disabled={busy}
                data-testid="seller-settings-cz-signing-select"
              >
                {SIGNING_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="cz-edo-label">Маршрут ЭДО</InputLabel>
              <Select
                labelId="cz-edo-label"
                label="Маршрут ЭДО"
                value={edoRoute}
                onChange={(e) => setEdoRoute(e.target.value)}
                disabled={busy}
                data-testid="seller-settings-cz-edo-select"
              >
                {EDO_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="cz-mp-label">Маркетплейс</InputLabel>
              <Select
                labelId="cz-mp-label"
                label="Маркетплейс"
                value={marketplace}
                onChange={(e) => setMarketplace(e.target.value)}
                disabled={busy}
              >
                {MARKETPLACE_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Номер МЧД"
              value={mchdId}
              onChange={(e) => setMchdId(e.target.value)}
              fullWidth
              disabled={busy}
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-cz-mchd-id' } }}
            />
            <TextField
              label="МЧД действует до"
              type="date"
              value={mchdUntil}
              onChange={(e) => setMchdUntil(e.target.value)}
              fullWidth
              disabled={busy}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Токен ГИС МТ (ЧЗ)"
              value={czToken}
              onChange={(e) => setCzToken(e.target.value)}
              fullWidth
              disabled={busy}
              type="password"
              placeholder={czCreds?.has_cz_token ? 'уже сохранён — вставьте новый для замены' : undefined}
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-cz-token' } }}
            />
            <TextField
              label="Токен СУЗ (эмиссия)"
              value={suzToken}
              onChange={(e) => setSuzToken(e.target.value)}
              fullWidth
              disabled={busy}
              type="password"
              placeholder={czCreds?.has_suz_oms_token ? 'уже сохранён' : undefined}
            />
            <TextField
              label="API ключ маркетплейса"
              value={mpKey}
              onChange={(e) => setMpKey(e.target.value)}
              fullWidth
              disabled={busy}
              type="password"
              placeholder={czCreds?.has_mp_api_key ? 'уже сохранён' : undefined}
            />
            <TextField
              label="Лимит авто-эмиссии (кодов)"
              value={autoEmitLimit}
              onChange={(e) => setAutoEmitLimit(e.target.value)}
              fullWidth
              disabled={busy}
              type="number"
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-cz-emit-limit' } }}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={autoIntroduce}
                  onChange={(e) => setAutoIntroduce(e.target.checked)}
                  disabled={busy}
                />
              }
              label="Автоматический ввод в оборот"
              data-testid="seller-settings-cz-auto-introduce"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setCzDialogOpen(false)}
            disabled={busy}
            data-testid="seller-settings-cz-cancel"
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            onClick={() => void onSaveMarkingCredentials()}
            disabled={busy}
            data-testid="seller-settings-cz-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>
        </>
      ) : null}
    </Box>
  )
}
