import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Typography,
} from '@mui/material'
import {
  FbsApiError,
  createFbsIdempotencyKey,
  fetchFbsTransferTargets,
  transferFbsOrders,
  type FbsTransferOrdersResult,
  type FbsTransferOrdersRequest,
  type FbsTransferTarget,
} from './fbsApi'
import { fbsErrorText, ordersWord } from './fbsUx'

// WMS-562: перенос выбранных заказов упаковки в другую поставку WB.
// Первая строка — «Новая поставка» (target_supply_id = null); остальные —
// доступные новые поставки того же селлера, которые ещё не взяты в работу.
// Один и тот же ключ идемпотентности переиспользуется при повторе после ошибки
// или pending — до тех пор, пока не сменился выбор заказов либо назначения.

// Загрузчики выносятся в проп, чтобы тесты могли подставить контракт без сети.
export type FbsTransferSupplyDialogDeps = {
  loadTargets: () => Promise<FbsTransferTarget[]>
  submit: (body: {
    order_ids: string[]
    target_supply_id: string | null
    idempotency_key: string
  }) => Promise<FbsTransferOrdersResult>
  createIdempotencyKey?: () => string
}

type Props = {
  open: boolean
  orderIds: string[]
  currentSupplyId: string
  onClose: () => void
  onTransferred: (result: FbsTransferOrdersResult) => void
  deps: FbsTransferSupplyDialogDeps
}

const NEW_SUPPLY_VALUE = '__wms562_new_supply__'

export function FbsTransferSupplyDialog({
  open,
  orderIds,
  currentSupplyId,
  onClose,
  onTransferred,
  deps,
}: Props) {
  const [targets, setTargets] = useState<FbsTransferTarget[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedTarget, setSelectedTarget] = useState<string>(NEW_SUPPLY_VALUE)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [partial, setPartial] = useState<FbsTransferOrdersResult | null>(null)

  const createKey = deps.createIdempotencyKey ?? createFbsIdempotencyKey
  const orderKey = useMemo(() => [...orderIds].sort().join(','), [orderIds])
  const idempotencyRef = useRef<string>('')
  const idempotencyFingerprintRef = useRef<string>('')
  const submittingRef = useRef(false)
  const depsRef = useRef(deps)
  depsRef.current = deps
  const generationRef = useRef(0)
  const pendingRequestRef = useRef<FbsTransferOrdersRequest | null>(null)
  const storageKey = `wms:fbs:${currentSupplyId}:transfer`
  const savePendingRequest = (request: FbsTransferOrdersRequest | null) => {
    pendingRequestRef.current = request
    try {
      if (request) window.sessionStorage.setItem(storageKey, JSON.stringify(request))
      else window.sessionStorage.removeItem(storageKey)
    } catch { /* The in-memory request still protects retries in this dialog. */ }
  }

  useEffect(() => {
    generationRef.current += 1
    if (!open) return
    setBusy(false)
    submittingRef.current = false
    setError(null)
    setPending(null)
    setPartial(null)
    pendingRequestRef.current = null
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(storageKey) ?? 'null') as FbsTransferOrdersRequest | null
      if (saved?.idempotency_key && Array.isArray(saved.order_ids)) pendingRequestRef.current = saved
    } catch { /* A missing or unavailable saved request is not an operation. */ }
    const previous = pendingRequestRef.current
    setSelectedTarget(previous?.target_supply_id ?? NEW_SUPPLY_VALUE)
    if (previous) setPending('Результат предыдущего переноса ещё не подтверждён. Повторите проверку.')
    let active = true
    setLoading(true)
    setLoadError(null)
    setTargets(null)
    void depsRef.current
      .loadTargets()
      .then((list) => {
        if (!active) return
        setTargets(list)
      })
      .catch((cause: unknown) => {
        if (!active) return
        setTargets([])
        setLoadError(cause instanceof Error ? cause.message : 'Не удалось загрузить список поставок.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
      generationRef.current += 1
    }
  }, [open, currentSupplyId, storageKey])

  const targetSupplyId = selectedTarget === NEW_SUPPLY_VALUE ? null : selectedTarget
  const fingerprint = `${currentSupplyId}|${orderKey}|${targetSupplyId ?? '__new__'}`

  const ensureIdempotencyKey = () => {
    if (idempotencyRef.current && idempotencyFingerprintRef.current === fingerprint) {
      return idempotencyRef.current
    }
    const next = createKey()
    idempotencyRef.current = next
    idempotencyFingerprintRef.current = fingerprint
    return next
  }

  const submit = async () => {
    if (busy || submittingRef.current) return
    if (orderIds.length === 0 && !pendingRequestRef.current) return
    submittingRef.current = true
    setBusy(true)
    setError(null)
    setPending(null)
    setPartial(null)
    const request = pendingRequestRef.current ?? {
      order_ids: [...orderIds],
      target_supply_id: targetSupplyId,
      idempotency_key: ensureIdempotencyKey(),
    }
    const generation = generationRef.current
    savePendingRequest(request)
    try {
      const result = await deps.submit(request)
      if (generation !== generationRef.current) return
      const unresolved = result.state === 'pending_confirmation' || result.pending_order_ids.length > 0
      if (unresolved) {
        setPending(result.message ?? 'WB ещё не подтвердил результат. Повторите проверку.')
        setPartial(result)
      } else {
        savePendingRequest(null)
        idempotencyRef.current = ''
        idempotencyFingerprintRef.current = ''
        if (result.state !== 'confirmed') {
          setError(result.message ?? `Не перенесены: ${result.failed_order_ids.length}.`)
          setPartial(result)
        }
      }
      if (result.transferred_order_ids.length > 0 || result.state === 'confirmed') onTransferred(result)
    } catch (cause) {
      if (generation !== generationRef.current) return
      if (cause instanceof FbsApiError && !cause.retryable && cause.status >= 400 && cause.status < 500 && cause.status !== 408) {
        savePendingRequest(null)
        setError(cause.message)
      } else {
        setPending(cause instanceof Error ? fbsErrorText(cause.message) : 'Результат переноса неизвестен. Повторите проверку.')
      }
    } finally {
      if (generation === generationRef.current) {
        submittingRef.current = false
        setBusy(false)
      }
    }
  }

  const filteredTargets = (targets ?? []).filter((target) => target.id !== currentSupplyId)
  const targetsEmpty = !loading && filteredTargets.length === 0

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      fullWidth
      maxWidth="sm"
      data-testid="fbs-transfer-supply-dialog"
    >
      <DialogTitle component="div" sx={{ pb: 1 }}>
        <Typography component="h2" variant="h6">
          Перенести в другую поставку
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {pendingRequestRef.current?.order_ids.length ?? orderIds.length} {ordersWord(pendingRequestRef.current?.order_ids.length ?? orderIds.length)} · КИЗ и данные сохранятся у выбранных заказов.
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          {loadError ? <Alert severity="error">{loadError}</Alert> : null}
          {error ? <Alert severity="error" data-testid="fbs-transfer-error">{error}</Alert> : null}
          {pending ? (
            <Alert severity="warning" data-testid="fbs-transfer-pending">
              {pending}
            </Alert>
          ) : null}
          {partial ? (
            <Alert severity="info" data-testid="fbs-transfer-partial">
              Перенесены: {partial.transferred_order_ids.length}. Ожидают подтверждения: {partial.pending_order_ids.length}. Не перенесены: {partial.failed_order_ids.length}.
            </Alert>
          ) : null}

          {loading ? (
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', py: 2 }}>
              <CircularProgress size={20} />
              <Typography variant="body2">Загружаем доступные поставки…</Typography>
            </Stack>
          ) : (
            <RadioGroup
              value={selectedTarget}
              onChange={(event) => setSelectedTarget(event.target.value)}
              data-testid="fbs-transfer-targets"
            >
              <FormControlLabel
                value={NEW_SUPPLY_VALUE}
                control={<Radio disabled={busy || Boolean(pending)} />}
                label={
                  <Stack spacing={0}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      Новая поставка
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      WMS создаст новую поставку в WB и перенесёт выбранные заказы туда.
                    </Typography>
                  </Stack>
                }
                data-testid="fbs-transfer-target-new"
              />
              {filteredTargets.map((target) => (
                <FormControlLabel
                  key={target.id}
                  value={target.id}
                  control={<Radio disabled={busy || Boolean(pending)} />}
                  label={
                    <Stack spacing={0}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {target.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        WB {target.wb_supply_id}
                      </Typography>
                    </Stack>
                  }
                  data-testid={`fbs-transfer-target-${target.id}`}
                />
              ))}
              {targetsEmpty ? (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
                  Других новых поставок нет — доступна только «Новая поставка».
                </Typography>
              ) : null}
            </RadioGroup>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} disabled={busy} data-testid="fbs-transfer-cancel">
          Отмена
        </Button>
        <Button
          variant="contained"
          onClick={() => void submit()}
          disabled={loading || busy || (orderIds.length === 0 && !pendingRequestRef.current)}
          startIcon={busy ? <CircularProgress size={18} color="inherit" /> : undefined}
          data-testid="fbs-transfer-submit"
        >
          {pending || partial ? 'Повторить' : 'ОК'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

// Пробрасываемые контрактом функции — чтобы дефолтная реализация не мешала тестам.
export function makeFbsTransferSupplyDeps(
  token: string,
  authHeaders: (token: string) => Record<string, string>,
  sourceSupplyId: string,
): FbsTransferSupplyDialogDeps {
  return {
    loadTargets: () => fetchFbsTransferTargets(token, authHeaders, sourceSupplyId),
    submit: (body) => transferFbsOrders(token, authHeaders, sourceSupplyId, body),
  }
}
