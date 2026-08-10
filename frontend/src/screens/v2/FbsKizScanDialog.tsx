import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import {
  commitFbsKiz,
  createFbsIdempotencyKey,
  FbsApiError,
  lookupFbsOrderBySticker,
  validateFbsKiz,
  type FbsKizLookup,
} from './fbsApi'

// Внесение чужих КИЗ по стикеру — tasks/fbs-kiz-manual-binding/TASK.md §6.4.
// Сопоставление ТОЛЬКО по стикеру: QR открывает заказ, следующий скан вешается на него.

type Pair = {
  orderId: string
  wbOrderId: number
  productName: string
  imageUrl: string | null
  value: string
  confirmed: boolean
  status: 'draft' | 'ok' | 'error'
  message: string | null
}

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  supplyId: string
  open: boolean
  onClose: () => void
  onCommitted: () => void
}

const tail = (value: string) => `…${value.slice(-6)}`

function errorText(cause: unknown): string {
  if (cause instanceof FbsApiError) {
    if (cause.code === 'sticker_not_found') return 'Стикер не найден в этой поставке'
    if (cause.code === 'order_frozen') return 'Заказ уже передан в доставку — КИЗ не изменить'
    if (cause.code === 'duplicate_kiz') {
      const context = cause.context as { wb_order_id?: number; created_at?: string } | null
      const order = context?.wb_order_id ? ` в заказ № ${context.wb_order_id}` : ''
      const when = context?.created_at
        ? ` от ${new Date(context.created_at).toLocaleDateString('ru-RU')}`
        : ''
      return `Этот КИЗ уже внесён${order}${when}`
    }
    if (cause.code === 'meta_validation_fail') return `WB не принял: ${cause.message}`
    if (cause.code.startsWith('wb_')) return 'WB недоступен, попробуйте ещё раз'
    return cause.message
  }
  return cause instanceof Error ? cause.message : 'Не удалось выполнить операцию'
}

export function FbsKizScanDialog({ token, authHeaders, supplyId, open, onClose, onCommitted }: Props) {
  const [active, setActive] = useState<FbsKizLookup | null>(null)
  const [value, setValue] = useState('')
  const [pairs, setPairs] = useState<Pair[]>([])
  const [confirmTarget, setConfirmTarget] = useState<FbsKizLookup | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Сканер стреляет в активное поле. Пока запрос идёт, поле заблокировано и фокус
  // теряется — без возврата фокуса следующий выстрел уходит в никуда.
  const refocus = useCallback(() => {
    window.setTimeout(() => inputRef.current?.focus(), 0)
  }, [])

  useEffect(() => {
    if (open) return
    setActive(null)
    setValue('')
    setPairs([])
    setConfirmTarget(null)
    setError(null)
  }, [open])

  const scanSticker = useCallback(
    async (raw: string) => {
      setBusy(true)
      setError(null)
      try {
        const found = await lookupFbsOrderBySticker(token, authHeaders, supplyId, raw)
        if (pairs.some((pair) => pair.orderId === found.order_id)) {
          setError(`Заказ № ${found.wb_order_id} уже в списке`)
          setValue('')
          return
        }
        if (!found.can_bind) {
          setError(found.block_reason ?? 'На этот заказ КИЗ внести нельзя')
          setValue('')
          return
        }
        if (found.needs_confirmation) setConfirmTarget(found)
        else setActive(found)
        setValue('')
      } catch (cause) {
        setError(errorText(cause))
        setValue('')
      } finally {
        setBusy(false)
        refocus()
      }
    },
    [token, authHeaders, supplyId, pairs, refocus],
  )

  const scanKiz = useCallback(
    async (raw: string) => {
      if (!active) return
      if (pairs.some((pair) => pair.value === raw)) {
        setError('Этот КИЗ уже в списке')
        setValue('')
        refocus()
        return
      }
      setBusy(true)
      setError(null)
      try {
        await validateFbsKiz(token, authHeaders, active.order_id, raw)
        setPairs((prev) => [
          ...prev,
          {
            orderId: active.order_id,
            wbOrderId: active.wb_order_id,
            productName: active.product.name,
            imageUrl: active.product.image_url,
            value: raw,
            confirmed: active.needs_confirmation,
            status: 'draft',
            message: null,
          },
        ])
        setActive(null)
        setValue('')
      } catch (cause) {
        setError(errorText(cause))
        setValue('')
      } finally {
        setBusy(false)
        refocus()
      }
    },
    [token, authHeaders, active, pairs, refocus],
  )

  const onEnter = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key !== 'Enter' || busy) return
      event.preventDefault()
      const raw = value.trim()
      if (!raw) return
      if (active) void scanKiz(raw)
      else void scanSticker(raw)
    },
    [busy, value, active, scanKiz, scanSticker],
  )

  const commit = useCallback(async () => {
    const pending = pairs.filter((pair) => pair.status !== 'ok')
    if (pending.length === 0) return
    setBusy(true)
    setError(null)
    try {
      const results = await commitFbsKiz(
        token,
        authHeaders,
        pending.map((pair) => ({ order_id: pair.orderId, value: pair.value, confirmed: pair.confirmed })),
        createFbsIdempotencyKey(),
      )
      setPairs((prev) =>
        prev.map((pair) => {
          const result = results.find((item) => item.order_id === pair.orderId)
          if (!result) return pair
          return {
            ...pair,
            status: result.status === 'ok' ? 'ok' : 'error',
            message: result.status === 'ok' ? null : (result.message ?? 'Не сохранено'),
          }
        }),
      )
      onCommitted()
    } catch (cause) {
      setError(errorText(cause))
    } finally {
      setBusy(false)
      refocus()
    }
  }, [pairs, token, authHeaders, onCommitted, refocus])

  const pendingCount = pairs.filter((pair) => pair.status !== 'ok').length
  const allDone = pairs.length > 0 && pendingCount === 0

  return (
    <>
      <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth data-testid="fbs-kiz-dialog">
        <DialogTitle sx={{ pb: 0.5 }}>
          Внести КИЗ
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            Только если Честный знак уже наклеен селлером
          </Typography>
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.5}>
            {active ? (
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }} data-testid="fbs-kiz-active">
                <ProductPhotoThumb src={active.product.image_url} alt={active.product.name} size={40} previewSize={280} />
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>
                    {active.product.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    № {active.wb_order_id}
                    {active.product.seller_article ? ` · ${active.product.seller_article}` : ''}
                  </Typography>
                </Box>
              </Stack>
            ) : null}

            <TextField
              autoFocus
              fullWidth
              size="small"
              value={value}
              disabled={busy}
              placeholder={active ? 'Сканируйте Честный знак' : 'Сканируйте QR стикера'}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={onEnter}
              inputRef={inputRef}
              data-testid="fbs-kiz-input"
            />

            {error ? (
              <Typography variant="body2" sx={{ color: 'error.main' }} data-testid="fbs-kiz-error">
                {error}
              </Typography>
            ) : null}

            {pairs.length > 0 ? (
              <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
                <Stack divider={<Divider flexItem />}>
                  {pairs.map((pair) => (
                    <Stack
                      key={`${pair.orderId}:${pair.value}`}
                      direction="row"
                      spacing={1.5}
                      sx={{ alignItems: 'center', px: 1.5, py: 1 }}
                      data-testid="fbs-kiz-pair"
                    >
                      <ProductPhotoThumb src={pair.imageUrl} alt={pair.productName} size={32} previewSize={240} />
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="body2" noWrap>
                          {pair.productName}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          № {pair.wbOrderId} · {tail(pair.value)}
                        </Typography>
                      </Box>
                      {pair.status === 'ok' ? (
                        <Typography sx={{ color: 'success.main', fontWeight: 700 }}>✓</Typography>
                      ) : null}
                      {pair.status === 'error' ? (
                        <Typography variant="caption" sx={{ color: 'error.main' }}>
                          {pair.message}
                        </Typography>
                      ) : null}
                      {pair.status !== 'ok' ? (
                        <IconButton
                          size="small"
                          disabled={busy}
                          aria-label="Убрать"
                          onClick={() => setPairs((prev) => prev.filter((item) => item !== pair))}
                        >
                          <CloseIcon fontSize="small" />
                        </IconButton>
                      ) : null}
                    </Stack>
                  ))}
                </Stack>
              </Paper>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={busy}>
            {allDone ? 'Закрыть' : 'Отмена'}
          </Button>
          {allDone ? null : (
            <Button
              variant="contained"
              disabled={busy || pendingCount === 0}
              onClick={() => void commit()}
              data-testid="fbs-kiz-commit"
            >
              Провести ({pendingCount})
            </Button>
          )}
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(confirmTarget)} onClose={() => setConfirmTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Заказ уже с ЧЗ</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            На заказ № {confirmTarget?.wb_order_id} уже есть ЧЗ {confirmTarget?.current_kiz?.masked}. Внести другой КИЗ?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmTarget(null)}>Отмена</Button>
          <Button
            variant="contained"
            data-testid="fbs-kiz-confirm-replace"
            onClick={() => {
              setActive(confirmTarget)
              setConfirmTarget(null)
            }}
          >
            Внести
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
