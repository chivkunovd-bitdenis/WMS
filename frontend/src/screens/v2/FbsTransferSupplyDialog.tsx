import { useEffect, useMemo, useRef, useState } from 'react'
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown'
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Link,
  Menu,
  MenuItem,
  Stack,
  TextField,
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

// WMS-562/WMS-581: перенос выбранных заказов упаковки в другую поставку WB.
// Одно поле с выпадающим списком: первая строка — «Новая поставка»
// (target_supply_id = null), дальше открытые поставки того же селлера в любом
// рабочем состоянии, куда WB примет заказы: «номер WB · от даты создания».
// При «Новой поставке» это же поле — строка ввода её названия. Один и тот же
// ключ идемпотентности переиспользуется при повторе после ошибки или pending —
// до тех пор, пока не сменился выбор заказов, назначения или названия.

// Загрузчики выносятся в проп, чтобы тесты могли подставить контракт без сети.
export type FbsTransferSupplyDialogDeps = {
  loadTargets: (orderIds: string[]) => Promise<FbsTransferTarget[]>
  submit: (body: FbsTransferOrdersRequest) => Promise<FbsTransferOrdersResult>
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

function transferTargetLabel(target: FbsTransferTarget) {
  const date = new Date(target.created_at)
  return `${target.wb_supply_id} · от ${Number.isNaN(date.getTime()) ? target.created_at : date.toLocaleDateString('ru-RU')}`
}

// Карточка поставки открывается тем же адресом, что и из списка FBS: ?supply_id=.
function supplyCardHref(supplyId: string) {
  return `${window.location.pathname}?${new URLSearchParams({ supply_id: supplyId }).toString()}`
}

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
  const [newName, setNewName] = useState('')
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null)
  const [created, setCreated] = useState<FbsTransferOrdersResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [partial, setPartial] = useState<FbsTransferOrdersResult | null>(null)
  const fieldRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const orderIdsRef = useRef(orderIds)
  orderIdsRef.current = orderIds

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
    setCreated(null)
    setMenuAnchor(null)
    pendingRequestRef.current = null
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(storageKey) ?? 'null') as FbsTransferOrdersRequest | null
      if (saved?.idempotency_key && Array.isArray(saved.order_ids)) pendingRequestRef.current = saved
    } catch { /* A missing or unavailable saved request is not an operation. */ }
    const previous = pendingRequestRef.current
    setSelectedTarget(previous?.target_supply_id ?? NEW_SUPPLY_VALUE)
    setNewName(previous?.name ?? '')
    if (previous) setPending('Результат предыдущего переноса ещё не подтверждён. Повторите проверку.')
    let active = true
    setLoading(true)
    setLoadError(null)
    setTargets(null)
    void depsRef.current
      .loadTargets(previous?.order_ids ?? orderIdsRef.current)
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
  const typedName = targetSupplyId === null ? newName.trim() : ''
  const fingerprint = `${currentSupplyId}|${orderKey}|${targetSupplyId ?? `__new__|${typedName}`}`

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
    const request: FbsTransferOrdersRequest = pendingRequestRef.current ?? {
      order_ids: [...orderIds],
      target_supply_id: targetSupplyId,
      idempotency_key: ensureIdempotencyKey(),
      ...(typedName ? { name: typedName } : {}),
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
        } else if (request.target_supply_id === null && result.target_supply_id) {
          // WMS-581 R5: после переноса в новую поставку — окно со ссылкой на неё.
          setCreated(result)
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
  const selectedTargetRow = filteredTargets.find((target) => target.id === selectedTarget)
  const isNewTarget = targetSupplyId === null
  const fieldDisabled = busy || Boolean(pending)
  const openTargets = () => {
    if (!fieldDisabled) setMenuAnchor(fieldRef.current)
  }
  const chooseTarget = (value: string) => {
    setSelectedTarget(value)
    setMenuAnchor(null)
    if (value === NEW_SUPPLY_VALUE) window.setTimeout(() => inputRef.current?.focus(), 0)
  }

  if (created?.target_supply_id) {
    return (
      <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid="fbs-transfer-supply-dialog">
        <DialogContent>
          <Typography variant="body1" data-testid="fbs-transfer-created">
            Создана поставка{' '}
            <Link
              href={supplyCardHref(created.target_supply_id)}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="fbs-transfer-created-link"
            >
              {created.target_supply_name ?? 'Новая поставка'} · WB {created.target_wb_supply_id ?? '—'}
            </Link>
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button variant="contained" onClick={onClose} data-testid="fbs-transfer-created-ok">
            ОК
          </Button>
        </DialogActions>
      </Dialog>
    )
  }

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
            <Stack spacing={1} data-testid="fbs-transfer-targets">
              <TextField
                ref={fieldRef}
                inputRef={inputRef}
                fullWidth
                label="Поставка"
                placeholder="Новая поставка"
                value={isNewTarget ? newName : selectedTargetRow ? transferTargetLabel(selectedTargetRow) : ''}
                onChange={(event) => {
                  if (isNewTarget) setNewName(event.target.value)
                }}
                onClick={() => {
                  if (!isNewTarget) openTargets()
                }}
                disabled={fieldDisabled}
                data-testid="fbs-transfer-target-field"
                slotProps={{
                  inputLabel: { shrink: true },
                  htmlInput: {
                    readOnly: !isNewTarget,
                    maxLength: 255,
                    'data-testid': 'fbs-transfer-target-input',
                    style: isNewTarget ? undefined : { cursor: 'pointer' },
                  },
                  input: {
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          size="small"
                          edge="end"
                          aria-label="Выбрать поставку"
                          disabled={fieldDisabled}
                          onClick={(event) => {
                            event.stopPropagation()
                            openTargets()
                          }}
                          data-testid="fbs-transfer-target-open"
                        >
                          <ArrowDropDownIcon />
                        </IconButton>
                      </InputAdornment>
                    ),
                  },
                }}
              />
              <Menu
                anchorEl={menuAnchor}
                open={Boolean(menuAnchor)}
                onClose={() => setMenuAnchor(null)}
                disableRestoreFocus
                slotProps={{ paper: { sx: { width: menuAnchor?.clientWidth, maxHeight: 360 } } }}
              >
                <MenuItem
                  selected={isNewTarget}
                  onClick={() => chooseTarget(NEW_SUPPLY_VALUE)}
                  data-testid="fbs-transfer-target-new"
                >
                  Новая поставка
                </MenuItem>
                {filteredTargets.map((target) => (
                  <MenuItem
                    key={target.id}
                    selected={target.id === selectedTarget}
                    onClick={() => chooseTarget(target.id)}
                    data-testid={`fbs-transfer-target-${target.id}`}
                  >
                    {transferTargetLabel(target)}
                  </MenuItem>
                ))}
              </Menu>
              {targetsEmpty ? (
                <Typography variant="caption" color="text.secondary">
                  Других подходящих поставок нет — доступна только «Новая поставка».
                </Typography>
              ) : null}
            </Stack>
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
    loadTargets: (orderIds) => fetchFbsTransferTargets(token, authHeaders, sourceSupplyId, orderIds),
    submit: (body) => transferFbsOrders(token, authHeaders, sourceSupplyId, body),
  }
}
