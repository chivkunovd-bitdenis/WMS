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
import { DataTable, ErrorNotice, PrimaryAction, WarningNotice, WarehouseContextSwitch } from '../../ui-kit'
import type { Column } from '../../ui-kit'
import {
  FbsApiError,
  createFbsIdempotencyKey,
  createFbsSupplyFromOrders,
  preflightFbsSupply,
  type FbsSupplyPreflight,
  type FbsSupplyPreflightInventoryLine,
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

type InventoryLine = FbsSupplyPreflightInventoryLine

type StockSource = { id: string; name: string; quantity: number }

function transferSources(line: InventoryLine): StockSource[] {
  let remaining = Math.max(line.required - line.current, 0)
  const sources = line.source_warehouses.length > 0
    ? line.source_warehouses.map(({ id, name, quantity }) => ({ id, name, quantity }))
    : line.source_warehouse
      ? [{
          id: line.source_warehouse.id,
          name: line.source_warehouse.name,
          quantity: line.source_warehouse.available,
        }]
      : []

  return sources.flatMap((source) => {
    const quantity = Math.min(Math.max(source.quantity, 0), remaining)
    remaining -= quantity
    return quantity > 0 ? [{ ...source, quantity }] : []
  })
}

export function sourceBreakdown(line: InventoryLine) {
  const deficit = Math.max(line.required - line.current, 0)
  const sources = transferSources(line)
  const knownQuantity = sources.reduce((total, source) => total + source.quantity, 0)
  const remainder = deficit - knownQuantity
  const parts = sources.map((source) => `${source.name} · ${source.quantity}`)
  if (remainder > 0) parts.push(`другие склады · ${remainder}`)

  return parts.join('; ') || '—'
}

export function aggregateSources(lines: InventoryLine[]) {
  const quantities = new Map<string, { name: string; quantity: number }>()
  let otherWarehouses = 0

  for (const line of lines) {
    const sources = transferSources(line)
    const knownQuantity = sources.reduce((total, source) => total + source.quantity, 0)
    for (const source of sources) {
      const current = quantities.get(source.id)
      quantities.set(source.id, {
        name: source.name,
        quantity: (current?.quantity ?? 0) + source.quantity,
      })
    }
    otherWarehouses += Math.max(line.required - line.current - knownQuantity, 0)
  }

  const parts = Array.from(quantities.values(), ({ name, quantity }) => `${name} — ${quantity} шт.`)
  if (otherWarehouses > 0) parts.push(`другие склады — ${otherWarehouses} шт.`)
  return parts.join(', ')
}

const inventoryColumns: Column<InventoryLine>[] = [
  { key: 'product', header: 'Товар', render: (line) => line.product_name },
  { key: 'required', header: 'Нужно', align: 'right', render: (line) => line.required },
  { key: 'here', header: 'Здесь', align: 'right', render: (line) => line.current },
  {
    key: 'source',
    header: 'Взять со склада',
    align: 'right',
    render: sourceBreakdown,
  },
]

const shortageColumns: Column<InventoryLine>[] = [
  { key: 'product', header: 'Товар', render: (line) => line.product_name },
  { key: 'required', header: 'Нужно', align: 'right', render: (line) => line.required },
  { key: 'total', header: 'Всего', align: 'right', render: (line) => line.total },
  { key: 'shortage', header: 'Не хватает', align: 'right', render: (line) => line.shortage },
]

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
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(null)
  const [resolvedPreflightKey, setResolvedPreflightKey] = useState<string | null>(null)

  const orderKey = useMemo(() => orderIds.join(','), [orderIds])
  const preflightKey = `${orderKey}:${deliveryType}:${selectedWarehouseId ?? ''}`

  // I6 (20.08.2026): сервер считает отпечаток запроса вместе со способом сдачи. Если
  // ключ не менять при переключении «Склад или СЦ» ↔ «Пункт выдачи», оператор упирается
  // в «ключ уже использован с другими параметрами» и выходит только перезакрытием окна.
  useEffect(() => {
    if (!open) return
    setIdempotencyKey(createFbsIdempotencyKey())
    setError(null)
    setPending(null)
    setSelectedWarehouseId(null)
    setResolvedPreflightKey(null)
  }, [open, orderKey, deliveryType])

  useEffect(() => {
    if (!open || orderIds.length === 0) {
      setPreflight(null)
      return
    }
    let active = true
    setPreflightBusy(true)
    setResolvedPreflightKey(null)
    setError(null)
    setPending(null)
    void preflightFbsSupply(token, authHeaders, {
      order_ids: orderIds,
      planned_delivery_type: deliveryType,
      selected_warehouse_id: selectedWarehouseId,
    })
      .then((result) => {
        if (active) {
          setPreflight(result)
          setResolvedPreflightKey(preflightKey)
        }
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
  }, [open, orderKey, orderIds, deliveryType, selectedWarehouseId, token, authHeaders, preflightKey])

  const create = async () => {
    if (!canCreate || creating) return
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
        selected_warehouse_id: effectiveWarehouseId,
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
  const warehouseOptions = preflight?.warehouse_options ?? []
  const effectiveWarehouseId = selectedWarehouseId ?? preflight?.recommended_warehouse?.id ?? summary?.wms_warehouse.id ?? null
  const warningLines = preflight?.stock_preflight.warning_lines ?? []
  const blockingLines = preflight?.stock_preflight.blocking_lines ?? []
  const localShortage = warningLines.reduce((total, line) => total + line.required - line.current, 0)
  const sourceSummary = aggregateSources(warningLines)
  const totalShortage = blockingLines.reduce((total, line) => total + line.shortage, 0)
  const shortageProducts = blockingLines.length
  const blockedByStock = totalShortage > 0
  const isCurrentPreflight = resolvedPreflightKey === preflightKey
  const canCreate = Boolean(preflight?.compatible && isCurrentPreflight && !blockedByStock && !preflightBusy)
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
          {error ? <ErrorNotice>{error}</ErrorNotice> : null}
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
            <Box data-testid="fbs-preflight-skeleton">
              <Typography variant="body2" sx={{ mb: 1.5 }}>Проверяем актуальный состав и остатки…</Typography>
              <DataTable columns={inventoryColumns} rows={[]} getRowKey={(line) => line.product_id} loading testId="fbs-preflight-skeleton-table" />
            </Box>
          ) : null}
          {summary ? (
            <Stack spacing={2}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <Chip
                  color={preflight?.compatible ? 'success' : 'error'}
                  label={preflight?.compatible ? 'Можно создать поставку' : 'Есть причины, которые нужно исправить'}
                />
              </Stack>

              {warehouseOptions.length > 1 ? <WarehouseContextSwitch options={warehouseOptions} value={effectiveWarehouseId} onChange={setSelectedWarehouseId} testId="fbs-preflight-warehouse" /> : null}
              {warningLines.length > 0 && !blockedByStock ? (
                <WarningNotice testId="fbs-preflight-warning">
                  <strong>На складе «{summary.wms_warehouse.name}» не хватает {localShortage} шт. по {warningLines.length} товарам.</strong>
                  <br />
                  Нужно подобрать: {sourceSummary}
                  <DataTable columns={inventoryColumns} rows={warningLines} getRowKey={(line) => line.product_id} testId="fbs-preflight-warning-table" />
                </WarningNotice>
              ) : null}
              {blockedByStock ? (
                <>
                  <ErrorNotice testId="fbs-preflight-stock-error">Не хватает {totalShortage} шт. по {shortageProducts} товарам. Пополните остаток или уберите заказы из выборки.</ErrorNotice>
                  <DataTable columns={shortageColumns} rows={blockingLines} getRowKey={(line) => line.product_id} testId="fbs-preflight-stock-table" />
                </>
              ) : null}

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
        <PrimaryAction
          onClick={() => void create()}
          disabled={!canCreate || creating}
          disabledReason={preflightBusy || !isCurrentPreflight ? 'Проверяем остатки' : blockedByStock ? 'Не хватает общего остатка' : undefined}
          startIcon={creating ? <CircularProgress size={18} color="inherit" /> : undefined}
          data-testid="fbs-create-submit"
        >
          Создать поставку
        </PrimaryAction>
      </DialogActions>
    </Dialog>
  )
}
