import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  Box,
  Button,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  Link,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { restoreCisGs } from '../../utils/restoreCisGs'
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

type ScannerDebug = {
  length: number
  first8: string
  last8: string
}

type DialogError = {
  text: string
  debug: ScannerDebug | null
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

const HINT_TEXT: Record<string, string> = {
  keyboard_layout: 'исправлена раскладка',
  gs_substitute: 'восстановлен разделитель',
  aim_prefix: 'убран префикс сканера',
  gs_structure_restored: 'разделители восстановлены по структуре кода',
}

function errorTextByCode(code: string, message: string, context: unknown): string {
  if (code === 'sticker_not_found') return 'Стикер не найден в этой поставке'
  if (code === 'order_frozen') return 'Заказ уже передан в доставку — КИЗ не изменить'
  if (code === 'duplicate_kiz') {
    const details = context as { wb_order_id?: number; created_at?: string } | null
    const order = details?.wb_order_id ? ` в заказ № ${details.wb_order_id}` : ''
    const when = details?.created_at
      ? ` от ${new Date(details.created_at).toLocaleDateString('ru-RU')}`
      : ''
    return `Этот КИЗ уже внесён${order}${when}`
  }
  if (code === 'needs_confirmation') {
    const details = context as { current_kiz?: string } | null
    const current = details?.current_kiz ? ` ${details.current_kiz}` : ''
    return `На этот заказ уже есть ЧЗ${current}. Внести другой КИЗ?`
  }
  if (code === 'not_a_kiz') return 'Это не похоже на Честный знак'
  if (code === 'gs_separator_lost') {
    return 'Разделители кода потеряны при вводе, структуру не восстановить — отсканируйте Честный знак заново целиком'
  }
  if (code === 'meta_validation_fail') return `WB не принял: ${message}`
  if (code.startsWith('wb_')) return 'WB недоступен, попробуйте ещё раз'
  return message
}

function errorText(cause: unknown): string {
  if (cause instanceof FbsApiError) {
    return errorTextByCode(cause.code, cause.message, cause.context)
  }
  return cause instanceof Error ? cause.message : 'Не удалось выполнить операцию'
}

function scannerDebug(cause: unknown): ScannerDebug | null {
  if (!(cause instanceof FbsApiError) || cause.code !== 'not_a_kiz') return null
  if (!cause.context || typeof cause.context !== 'object') return null
  const debug = (cause.context as { debug?: unknown }).debug
  if (!debug || typeof debug !== 'object') return null
  const row = debug as { length?: unknown; first8?: unknown; last8?: unknown }
  if (
    typeof row.length !== 'number' ||
    typeof row.first8 !== 'string' ||
    typeof row.last8 !== 'string'
  ) {
    return null
  }
  return { length: row.length, first8: row.first8, last8: row.last8 }
}

// Тот же вид отладочной строки, что отдаёт сервер (scan_debug), но для случая,
// когда мы отказали ДО сетевого запроса — восстановить разделители по
// структуре не вышло, отправлять в WB нечего.
function scanDebugFromRaw(raw: string): ScannerDebug {
  const visible = (part: string) => part.replaceAll('\x1d', '<GS>')
  return { length: raw.length, first8: visible(raw.slice(0, 8)), last8: visible(raw.slice(-8)) }
}

export function FbsKizScanDialog({ token, authHeaders, supplyId, open, onClose, onCommitted }: Props) {
  const [active, setActive] = useState<FbsKizLookup | null>(null)
  const [value, setValue] = useState('')
  const [pairs, setPairs] = useState<Pair[]>([])
  const [confirmTarget, setConfirmTarget] = useState<FbsKizLookup | null>(null)
  const [error, setError] = useState<DialogError | null>(null)
  const [hints, setHints] = useState<string[]>([])
  const [debugOpen, setDebugOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  // Сканер стреляет в активное поле. Пока запрос идёт, поле заблокировано и фокус
  // теряется — без возврата фокуса следующий выстрел уходит в никуда.
  // С ретраями: если после focus() активный элемент — не наше поле, повторить попытку.
  const refocus = useCallback(() => {
    let attempts = 0
    const focus = () => {
      const input = inputRef.current
      input?.focus()
      attempts += 1
      if (input != null && document.activeElement !== input && attempts < 8) {
        window.setTimeout(focus, 50)
      }
    }
    window.setTimeout(focus, 0)
  }, [])

  useEffect(() => {
    if (open) return
    setActive(null)
    setValue('')
    setPairs([])
    setConfirmTarget(null)
    setError(null)
    setHints([])
    setDebugOpen(false)
  }, [open])

  // Фокус в поле при открытии диалога — важна надёжность, т.к. анимация открытия
  // может помешать autoFocus пропсу на TextField.
  useEffect(() => {
    if (open) {
      refocus()
    }
  }, [open, refocus])

  const scanSticker = useCallback(
    async (raw: string) => {
      setBusy(true)
      setError(null)
      setHints([])
      setDebugOpen(false)
      try {
        const found = await lookupFbsOrderBySticker(token, authHeaders, supplyId, raw)
        if (pairs.some((pair) => pair.orderId === found.order_id)) {
          setError({ text: `Заказ № ${found.wb_order_id} уже в списке`, debug: null })
          setValue('')
          return
        }
        if (!found.can_bind) {
          setError({ text: found.block_reason ?? 'На этот заказ КИЗ внести нельзя', debug: null })
          setValue('')
          return
        }
        if (found.needs_confirmation) setConfirmTarget(found)
        else setActive(found)
        setValue('')
      } catch (cause) {
        setError({ text: errorText(cause), debug: scannerDebug(cause) })
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

      // I3: разделители GS иногда вырезаны целиком браузерным полем ввода
      // (сканер их посылал, поле их не пропустило). Чиним по структуре кода
      // сразу на клиенте — быстрее для оператора, чем ждать ответ сервера, и
      // код без единого шанса восстановиться отсекается прямо тут, не уходя
      // в сеть. Сервер — тот же restoreCisGs.ts, но на бэкенде, в
      // normalize_scanned_cis — остаётся последним рубежом на случай любого
      // другого входа (мобильный терминал, ручной ввод), а не только этого
      // диалога.
      const structural = restoreCisGs(raw)
      if (structural.unrestorable) {
        setError({
          text: 'Разделители кода потеряны, а структуру не восстановить — отсканируйте Честный знак заново целиком',
          debug: scanDebugFromRaw(raw),
        })
        setHints([])
        setDebugOpen(false)
        setValue('')
        refocus()
        return
      }
      const value = structural.value
      const localHints = structural.restored ? ['gs_structure_restored'] : []

      if (pairs.some((pair) => pair.value === value)) {
        setError({ text: 'Этот КИЗ уже в списке', debug: null })
        setHints([])
        setDebugOpen(false)
        setValue('')
        refocus()
        return
      }
      setBusy(true)
      setError(null)
      setHints(localHints)
      setDebugOpen(false)
      try {
        const result = await validateFbsKiz(token, authHeaders, active.order_id, value)
        setHints([...localHints, ...result.hints])
        setPairs((prev) => [
          ...prev,
          {
            orderId: active.order_id,
            wbOrderId: active.wb_order_id,
            productName: active.product.name,
            imageUrl: active.product.image_url,
            value,
            confirmed: active.needs_confirmation,
            status: 'draft',
            message: null,
          },
        ])
        setActive(null)
        setValue('')
      } catch (cause) {
        setError({ text: errorText(cause), debug: scannerDebug(cause) })
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
    setDebugOpen(false)
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
            message:
              result.status === 'ok'
                ? null
                : errorTextByCode(result.code ?? '', result.message ?? 'Не сохранено', null),
          }
        }),
      )
      onCommitted()
    } catch (cause) {
      setError({ text: errorText(cause), debug: scannerDebug(cause) })
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
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <QrCodeScannerOutlined fontSize="small" color="action" />
                    </InputAdornment>
                  ),
                },
              }}
              sx={{ '& input': { fontFamily: 'monospace' } }}
            />

            <Typography variant="caption" color="text.secondary" data-testid="fbs-kiz-scan-message">
              {active
                ? `Товар: ${active.product.name} № ${active.wb_order_id} — сканируйте Честный знак: код привяжется и уйдёт в WB.`
                : 'Сканируйте QR стикера, затем сразу Честный знак — код привяжется у нас и уйдёт в WB.'}
            </Typography>

            {hints.length > 0 ? (
              <Typography variant="caption" color="text.secondary">
                {hints.map((hint) => HINT_TEXT[hint] ?? hint).join(' · ')}
              </Typography>
            ) : null}

            {error ? (
              <Typography
                variant="body2"
                component="div"
                sx={{ color: 'error.main' }}
                data-testid="fbs-kiz-error"
              >
                {error.text}
                {error.debug ? (
                  <>
                    <Link
                      component="button"
                      type="button"
                      variant="body2"
                      color="inherit"
                      underline="hover"
                      onClick={() => setDebugOpen((current) => !current)}
                      sx={{ ml: 1 }}
                    >
                      Что приехало со сканера
                    </Link>
                    <Collapse in={debugOpen}>
                      <Typography variant="caption" component="div" color="text.secondary">
                        Длина: {error.debug.length} · начало: {error.debug.first8 || '—'} · конец:{' '}
                        {error.debug.last8 || '—'}
                      </Typography>
                    </Collapse>
                  </>
                ) : null}
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
