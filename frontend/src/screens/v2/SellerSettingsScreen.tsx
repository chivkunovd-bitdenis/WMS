import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
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
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
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

export function SellerSettingsScreen({ token, authHeaders }: Props) {
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

  useEffect(() => {
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
  }, [authHeaders, token])

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
    void loadMarkingCredentials()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when token changes
  }, [token])

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
      const j = (await res.json()) as { cards_received?: number; cards_saved?: number }
      setOpen(false)
      setContentKey('')
      setHasContentKey(true)
      await refreshWbCardsCount()
      setOkMsg(
        `Ключ сохранён. Проверка WB прошла (карточек получено: ${j.cards_received ?? 0}, сохранено: ${j.cards_saved ?? 0}).`,
      )
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
              label="WB Content API key"
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
    </Box>
  )
}
