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
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
}

export function SellerSettingsScreen({ token, authHeaders }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [okMsg, setOkMsg] = useState<string | null>(null)
  const [contentKey, setContentKey] = useState('')
  const [hasContentKey, setHasContentKey] = useState<boolean | null>(null)
  const [wbCardsCount, setWbCardsCount] = useState<number | null>(null)

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

      <Paper variant="outlined" sx={{ p: 2, maxWidth: 720 }} data-testid="seller-settings-wb-card">
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
    </Box>
  )
}

