import { useEffect, useMemo, useRef, useState, type FormEventHandler } from 'react'
import {
  Alert,
  Button,
  FormControl,
  InputLabel,
  NativeSelect,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Screen } from '../AppV2Screens'
import {
  DataTable,
  QtyCell,
  SecondaryAction,
  TextCell,
  WarehouseContextSwitch,
  type WarehouseOption,
} from '../../ui-kit'

export type TransferLocationRow = { id: string; code: string; warehouse_id: string }
type ProductRow = { id: string; name: string; sku_code: string }
type TransferSummary = { quantity: number; product: string; from: string; to: string }
export type TransferMovementRow = {
  id: string
  product_id: string
  sku_code: string
  product_name?: string | null
  storage_location_id: string
  storage_location_code?: string | null
  warehouse_id?: string | null
  warehouse_name?: string | null
  quantity_delta: number
  movement_type: string
  transfer_group_id?: string | null
  created_at: string
}

export type TransferOperation = {
  id: string
  product: string
  quantity: number
  fromWarehouse: WarehouseOption
  toWarehouse: WarehouseOption
  fromLocation: string
  toLocation: string
}

type Props = {
  opsError: string | null
  opsBusy: boolean
  isFulfillmentAdmin: boolean
  locations: TransferLocationRow[]
  products: ProductRow[]
  onStockTransfer: FormEventHandler<HTMLFormElement>
  warehouses?: WarehouseOption[]
  selectedWarehouseId?: string | null
  onWarehouseChange?: (warehouseId: string) => void
  transferMovements?: TransferMovementRow[]
  onRefreshTransferMovements?: () => Promise<void>
}

export function buildTransferOperations(
  transferMovements: TransferMovementRow[],
  warehouses: WarehouseOption[],
  locations: TransferLocationRow[],
): TransferOperation[] {
  const movementsByGroup = new Map<string, TransferMovementRow[]>()
  transferMovements.forEach((movement) => {
    if (
      !movement.transfer_group_id ||
      (movement.movement_type !== 'stock_transfer_out' && movement.movement_type !== 'stock_transfer_in')
    ) return
    const group = movementsByGroup.get(movement.transfer_group_id) ?? []
    group.push(movement)
    movementsByGroup.set(movement.transfer_group_id, group)
  })

  const warehouseById = new Map(warehouses.map((warehouse) => [warehouse.id, warehouse]))
  const locationById = new Map(locations.map((location) => [location.id, location.code]))
  return [...movementsByGroup.entries()].flatMap(([groupId, movements]) => {
    const from = movements.find((movement) => movement.movement_type === 'stock_transfer_out')
    const to = movements.find((movement) => movement.movement_type === 'stock_transfer_in')
    if (!from?.warehouse_id || !to?.warehouse_id) return []
    const fromWarehouse = warehouseById.get(from.warehouse_id) ?? {
      id: from.warehouse_id,
      name: from.warehouse_name ?? 'Склад не указан',
    }
    const toWarehouse = warehouseById.get(to.warehouse_id) ?? {
      id: to.warehouse_id,
      name: to.warehouse_name ?? 'Склад не указан',
    }
    return [{
      id: groupId,
      product: from.product_name ? `${from.sku_code} — ${from.product_name}` : from.sku_code,
      quantity: Math.abs(from.quantity_delta),
      fromWarehouse,
      toWarehouse,
      fromLocation: from.storage_location_code ?? locationById.get(from.storage_location_id) ?? 'Ячейка не указана',
      toLocation: to.storage_location_code ?? locationById.get(to.storage_location_id) ?? 'Ячейка не указана',
    }]
  })
}

export function TransfersScreen({
  opsError,
  opsBusy,
  isFulfillmentAdmin,
  locations,
  products,
  onStockTransfer,
  warehouses = [],
  selectedWarehouseId = null,
  onWarehouseChange,
  transferMovements = [],
  onRefreshTransferMovements,
}: Props) {
  const [fromLoc, setFromLoc] = useState('')
  const [toLoc, setToLoc] = useState('')
  const [productId, setProductId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [lastTransfer, setLastTransfer] = useState<TransferSummary | null>(null)
  const [pendingTransfer, setPendingTransfer] = useState<TransferSummary | null>(null)
  const [expandedTransferIds, setExpandedTransferIds] = useState<Set<string>>(() => new Set())
  const [transferOperationsLoading, setTransferOperationsLoading] = useState(Boolean(onRefreshTransferMovements))
  const transferRefreshStarted = useRef(false)

  useEffect(() => {
    if (transferRefreshStarted.current || !onRefreshTransferMovements) return
    transferRefreshStarted.current = true
    void onRefreshTransferMovements().finally(() => setTransferOperationsLoading(false))
  }, [onRefreshTransferMovements])

  useEffect(() => {
    if (pendingTransfer && !opsBusy) {
      if (!opsError) setLastTransfer(pendingTransfer)
      setPendingTransfer(null)
    }
  }, [opsBusy, opsError, pendingTransfer])

  const fromLabel = useMemo(
    () => locations.find((loc) => loc.id === fromLoc)?.code ?? '',
    [fromLoc, locations],
  )
  const toLabel = useMemo(
    () => locations.find((loc) => loc.id === toLoc)?.code ?? '',
    [toLoc, locations],
  )
  const productLabel = useMemo(() => {
    const p = products.find((row) => row.id === productId)
    return p ? `${p.sku_code} — ${p.name}` : ''
  }, [productId, products])
  const quantityNumber = Number(quantity)
  const sameLocation = Boolean(fromLoc && toLoc && fromLoc === toLoc)
  const quantityInvalid =
    quantity.trim() !== '' &&
    (!Number.isInteger(quantityNumber) || quantityNumber < 1)
  const readyForSubmit =
    Boolean(fromLoc && toLoc && productId) &&
    Number.isInteger(quantityNumber) &&
    quantityNumber > 0 &&
    !sameLocation
  const transferOperations = useMemo(
    () => buildTransferOperations(transferMovements, warehouses, locations),
    [locations, transferMovements, warehouses],
  )
  const visibleTransferOperations = useMemo(
    () => transferOperations.filter((operation) => {
      if (!selectedWarehouseId) return true
      return operation.fromWarehouse.id === selectedWarehouseId || operation.toWarehouse.id === selectedWarehouseId
    }),
    [selectedWarehouseId, transferOperations],
  )
  const selectedWarehouseName = warehouses.find((warehouse) => warehouse.id === selectedWarehouseId)?.name
  const transferColumns = [
    {
      key: 'operation',
      header: 'Перемещение',
      render: (operation: TransferOperation) => {
        if (operation.fromWarehouse.id === operation.toWarehouse.id) {
          return <TextCell value={`На складе «${operation.fromWarehouse.name}»`} />
        }
        if (selectedWarehouseId === operation.fromWarehouse.id) {
          return <TextCell value={`Из склада «${operation.fromWarehouse.name}»`} />
        }
        if (selectedWarehouseId === operation.toWarehouse.id) {
          return <TextCell value={`В склад «${operation.toWarehouse.name}»`} />
        }
        return <TextCell value={`${operation.fromWarehouse.name} → ${operation.toWarehouse.name}`} />
      },
    },
    { key: 'product', header: 'Товар', render: (operation: TransferOperation) => <TextCell value={operation.product} /> },
    { key: 'quantity', header: 'Количество', align: 'right' as const, render: (operation: TransferOperation) => <QtyCell value={operation.quantity} /> },
    {
      key: 'details',
      header: 'Детали',
      render: (operation: TransferOperation) => {
        const expanded = expandedTransferIds.has(operation.id)
        return (
          <>
            <SecondaryAction
              type="button"
              data-testid={`transfer-operation-toggle-${operation.id}`}
              onClick={() => setExpandedTransferIds((current) => {
                const next = new Set(current)
                if (next.has(operation.id)) next.delete(operation.id)
                else next.add(operation.id)
                return next
              })}
            >
              {expanded ? 'Скрыть' : 'Раскрыть'}
            </SecondaryAction>
            {expanded ? (
              <Stack spacing={0.5} sx={{ mt: 1 }} data-testid={`transfer-operation-details-${operation.id}`}>
                <TextCell value={`Из склада «${operation.fromWarehouse.name}» · ячейка ${operation.fromLocation}`} />
                <TextCell value={`В склад «${operation.toWarehouse.name}» · ячейка ${operation.toLocation}`} />
              </Stack>
            ) : null}
          </>
        )
      },
    },
  ]
  const fromSelectInputProps = {
    id: 'transfer-from-loc',
    name: 'transfer_from_loc',
    'data-testid': 'transfer-from-loc',
    required: true,
  }
  const toSelectInputProps = {
    id: 'transfer-to-loc',
    name: 'transfer_to_loc',
    'data-testid': 'transfer-to-loc',
    required: true,
  }
  const productSelectInputProps = {
    id: 'transfer-product',
    name: 'transfer_product_id',
    'data-testid': 'transfer-product',
    required: true,
  }

  const submit: FormEventHandler<HTMLFormElement> = (event) => {
    if (!readyForSubmit) {
      event.preventDefault()
      return
    }
    setPendingTransfer({ quantity: quantityNumber, product: productLabel, from: fromLabel, to: toLabel })
    onStockTransfer(event)
  }

  return (
    <Screen title="Перемещения" subtitle="Перемещение между ячейками на одном складе">
      {opsError ? (
        <Alert severity="error" data-testid="operations-error">
          {opsError}
        </Alert>
      ) : null}
      {!isFulfillmentAdmin ? (
        <Alert severity="info">Доступно только для фулфилмента.</Alert>
      ) : (
        <Stack spacing={2}>
          <WarehouseContextSwitch
            options={warehouses}
            value={selectedWarehouseId}
            onChange={(warehouseId) => onWarehouseChange?.(warehouseId)}
            testId="transfers-warehouse-context"
          />
          <DataTable
            columns={transferColumns}
            rows={visibleTransferOperations}
            getRowKey={(operation) => operation.id}
            loading={transferOperationsLoading}
            empty={{
              title: selectedWarehouseName ? `На складе «${selectedWarehouseName}» пока нет перемещений.` : 'Перемещений пока нет.',
              hint: selectedWarehouseId ? 'Выберите другой склад или дождитесь новой операции.' : undefined,
            }}
            testId="transfer-operations-list"
          />
          <Paper variant="outlined" sx={{ p: 2 }} data-testid="stock-transfer-section">
          <Stack spacing={2}>
            {lastTransfer ? (
              <Alert severity="success" data-testid="transfer-operation-row">
                Перемещение: {lastTransfer.quantity} шт · {lastTransfer.product} · {lastTransfer.from} → {lastTransfer.to}
              </Alert>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              Выберите товар, ячейку списания и ячейку назначения. Система проведёт расход из первой ячейки и приход во вторую.
            </Typography>
            <Stack
              component="form"
              data-testid="stock-transfer-form"
              noValidate
              onSubmit={submit}
              spacing={2}
            >
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <FormControl
                  fullWidth
                  size="small"
                  required
                >
                  <InputLabel shrink htmlFor="transfer-from-loc">
                    Откуда
                  </InputLabel>
                  <NativeSelect
                    value={fromLoc}
                    onChange={(event) => setFromLoc(event.target.value)}
                    inputProps={fromSelectInputProps}
                  >
                    <option value="" disabled>
                      Выберите ячейку
                    </option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        {loc.code}
                      </option>
                    ))}
                  </NativeSelect>
                </FormControl>
                <FormControl
                  fullWidth
                  size="small"
                  required
                  error={sameLocation}
                >
                  <InputLabel shrink htmlFor="transfer-to-loc">
                    Куда
                  </InputLabel>
                  <NativeSelect
                    value={toLoc}
                    onChange={(event) => setToLoc(event.target.value)}
                    inputProps={toSelectInputProps}
                  >
                    <option value="" disabled>
                      Выберите ячейку
                    </option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        {loc.code}
                      </option>
                    ))}
                  </NativeSelect>
                  <Typography variant="caption" color={sameLocation ? 'error.main' : 'text.secondary'}>
                    {sameLocation ? 'Выберите другую ячейку назначения.' : ' '}
                  </Typography>
                </FormControl>
              </Stack>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                <FormControl
                  fullWidth
                  size="small"
                  required
                >
                  <InputLabel shrink htmlFor="transfer-product">
                    Товар
                  </InputLabel>
                  <NativeSelect
                    value={productId}
                    onChange={(event) => setProductId(event.target.value)}
                    inputProps={productSelectInputProps}
                  >
                    <option value="" disabled>
                      Выберите SKU
                    </option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.sku_code} — {p.name}
                      </option>
                    ))}
                  </NativeSelect>
                </FormControl>
                <TextField
                  fullWidth
                  size="small"
                  label="Количество"
                  name="transfer_qty"
                  type="number"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  required
                  error={quantityInvalid}
                  helperText={quantityInvalid ? 'Введите целое число от 1.' : ' '}
                  slotProps={{
                    htmlInput: {
                      min: 1,
                      step: 1,
                      inputMode: 'numeric',
                      'data-testid': 'transfer-qty',
                    },
                  }}
                />
              </Stack>
              {readyForSubmit ? (
                <Alert severity="info" data-testid="transfer-summary">
                  Перемещение: {quantityNumber} шт · {productLabel} · {fromLabel} → {toLabel}
                </Alert>
              ) : null}
              <Button
                variant="contained"
                type="submit"
                data-testid="transfer-submit"
                disabled={opsBusy || locations.length < 2 || !readyForSubmit}
              >
                {opsBusy ? 'Перемещаем...' : 'Переместить'}
              </Button>
            </Stack>
          </Stack>
          </Paper>
        </Stack>
      )}
    </Screen>
  )
}
