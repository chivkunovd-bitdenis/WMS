import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Typography,
} from '@mui/material'
import {
  FbsApiError,
  createFbsIdempotencyKey,
  createFbsSupplyFromOrders,
  preflightFbsSupply,
  type FbsSupplyPreflight,
  type FbsWorkspace,
} from './fbsApi'
import { ordersWord } from './fbsUx'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  orderIds: string[]
  open: boolean
  onClose: () => void
  onCreated: (workspace: FbsWorkspace) => void
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 700 }}>
        {value}
      </Typography>
    </Box>
  )
}

export function FbsSupplyCreateDialog({
  token,
  authHeaders,
  orderIds,
  open,
  onClose,
  onCreated,
}: Props) {
  const [deliveryType, setDeliveryType] = useState<'warehouse_sc' | 'pvz'>('warehouse_sc')
  const [preflight, setPreflight] = useState<FbsSupplyPreflight | null>(null)
  const [preflightBusy, setPreflightBusy] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [idempotencyKey, setIdempotencyKey] = useState(createFbsIdempotencyKey)

  const orderKey = useMemo(() => orderIds.join(','), [orderIds])

  // I6 (20.08.2026): сервер считает отпечаток запроса вместе со способом сдачи. Если
  // ключ не менять при переключении «Склад или СЦ» ↔ «Пункт выдачи», оператор упирается
  // в «ключ уже использован с другими параметрами» и выходит только перезакрытием окна.
  useEffect(() => {
    if (!open) return
    setIdempotencyKey(createFbsIdempotencyKey())
    setError(null)
    setPending(null)
  }, [open, orderKey, deliveryType])

  useEffect(() => {
    if (!open || orderIds.length === 0) {
      setPreflight(null)
      return
    }
    let active = true
    setPreflightBusy(true)
    setError(null)
    setPending(null)
    void preflightFbsSupply(token, authHeaders, {
      order_ids: orderIds,
      planned_delivery_type: deliveryType,
    })
      .then((result) => {
        if (active) setPreflight(result)
      })
      .catch((cause: unknown) => {
        if (!active) return
        setPreflight(null)
        setError(cause instanceof Error ? cause.message : 'Не удалось проверить состав поставки.')
      })
      .finally(() => {
        if (active) setPreflightBusy(false)
      })
    return () => {
      active = false
    }
  }, [open, orderKey, orderIds, deliveryType, token, authHeaders])

  const create = async () => {
    if (!preflight?.compatible || creating) return
    setCreating(true)
    setError(null)
    setPending(null)
    try {
      const workspace = await createFbsSupplyFromOrders(token, authHeaders, {
        // Имя генерирует WMS: оператору оно не требуется для сборки.
        name: `FBS ${new Date().toLocaleDateString('ru-RU')}`,
        order_ids: orderIds,
        planned_delivery_type: deliveryType,
        planned_destination: null,
        idempotency_key: idempotencyKey,
      })
      onCreated(workspace)
    } catch (cause) {
      if (
        cause instanceof FbsApiError &&
        cause.retryable &&
        ['wb_timeout', 'wb_pending_confirmation'].includes(cause.code)
      ) {
        const context = cause.context && typeof cause.context === 'object'
          ? cause.context as { wb_supply_id?: unknown }
          : null
        const wbSupply = typeof context?.wb_supply_id === 'string' ? ` WB: ${context.wb_supply_id}.` : ''
        setPending(`${cause.message}${wbSupply} Повторите проверку, чтобы прочитать фактический состав WB.`)
      } else {
        // Неудачная попытка не должна запирать оператора на использованном ключе:
        // следующее нажатие уходит со свежим.
        setIdempotencyKey(createFbsIdempotencyKey())
        setError(cause instanceof Error ? cause.message : 'Не удалось создать поставку.')
      }
    } finally {
      setCreating(false)
    }
  }

  const summary = preflight?.summary
  return (
    <Dialog open={open} onClose={creating ? undefined : onClose} fullWidth maxWidth="md">
      <DialogTitle component="div" sx={{ pb: 1 }}>
        <Typography component="h2" variant="h6">Новая поставка FBS</Typography>
        <Typography variant="body2" color="text.secondary">
          WMS ещё раз проверит совместимость {orderIds.length} {ordersWord(orderIds.length)} и создаст поставку.
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2.5}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {pending ? (
            <Alert
              severity="warning"
              action={
                <Button color="inherit" size="small" onClick={() => void create()} disabled={creating}>
                  Повторить проверку
                </Button>
              }
              data-testid="fbs-supply-pending-confirmation"
            >
              {pending}
            </Alert>
          ) : null}

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Планируемый способ сдачи
            </Typography>
            <RadioGroup
              row
              value={deliveryType}
              onChange={(event) =>
                setDeliveryType(event.target.value as 'warehouse_sc' | 'pvz')
              }
            >
              <FormControlLabel
                value="warehouse_sc"
                control={<Radio />}
                label="Склад или сортировочный центр"
              />
              <FormControlLabel value="pvz" control={<Radio />} label="Пункт выдачи" />
            </RadioGroup>
            {deliveryType === 'pvz' ? (
              <Typography variant="caption" color="text.secondary">
                Конкретный ПВЗ заранее не закрепляется. Здесь проверяется только допустимость
                маршрута для каждого заказа.
              </Typography>
            ) : null}
          </Box>

          <Divider />

          {preflightBusy ? (
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', py: 3 }}>
              <CircularProgress size={22} />
              <Typography variant="body2">Проверяем актуальный состав и остатки…</Typography>
            </Stack>
          ) : summary ? (
            <Stack spacing={2}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <Chip
                  color={preflight?.compatible ? 'success' : 'error'}
                  label={preflight?.compatible ? 'Можно создать поставку' : 'Есть причины, которые нужно исправить'}
                />
              </Stack>

              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' },
                  gap: 2,
                  p: 2,
                  borderRadius: 2,
                  bgcolor: 'rgba(91, 33, 182, 0.055)',
                }}
              >
                <SummaryItem label="Селлер" value={summary.seller.name} />
                <SummaryItem
                  label="Склад WB"
                  value={summary.wb_warehouse.name ? String(summary.wb_warehouse.name) : `WB ${summary.wb_warehouse.id}`}
                />
                <SummaryItem label="Склад WMS" value={summary.wms_warehouse.name} />
                <SummaryItem label="Заказов" value={String(summary.orders_count)} />
                <SummaryItem label="Грузовой тип" value={summary.cargo_type} />
                <SummaryItem label="Контроль сборки" value="без подтверждённого WB SLA" />
                {summary.buyer_type === 'legal' ? <SummaryItem label="Покупатель" value="Юридическое лицо" /> : null}
                {summary.required_marking_count > 0 ? <SummaryItem label="Нужна маркировка" value={String(summary.required_marking_count)} /> : null}
                {deliveryType === 'pvz' && summary.pvz_blocked_count > 0 ? <SummaryItem label="Нельзя сдать через ПВЗ" value={String(summary.pvz_blocked_count)} /> : null}
              </Box>

              {preflight?.issues.length ? (
                <Alert severity="error">
                  <Stack spacing={0.5}>
                    {preflight.issues.map((issue) => (
                      <Typography key={`${issue.order_id}-${issue.code}`} variant="body2">
                        {issue.message}
                      </Typography>
                    ))}
                  </Stack>
                </Alert>
              ) : null}
            </Stack>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} disabled={creating}>
          Отмена
        </Button>
        <Button
          variant="contained"
          size="large"
          onClick={() => void create()}
          disabled={!preflight?.compatible || preflightBusy || creating}
          startIcon={creating ? <CircularProgress size={18} color="inherit" /> : undefined}
          data-testid="fbs-create-submit"
        >
          Создать поставку
        </Button>
      </DialogActions>
    </Dialog>
  )
}
