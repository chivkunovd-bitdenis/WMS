import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { confirmDiscardChanges } from '../../utils/confirmDiscardChanges'
import { plural } from '../../utils/plural'
import {
  FbsApiError,
  createFbsIdempotencyKey,
  createFbsSupplyFromOrders,
  preflightFbsSupply,
  type FbsSupplyPreflight,
  type FbsWorklistOrder,
} from './fbsApi'
import { fbsErrorText, ordersWord } from './fbsUx'
import {
  groupFbsOrdersForSupplies,
  runFbsSupplyGroupCreation,
  type FbsGroupCreateResult,
  type FbsSupplyGroupDraft,
} from './fbsSupplyAssembly'

// WMS-574 R1–R4: окно «Новые поставки FBS» — выбор делится на несколько
// поставок WB (Д1), для каждой идёт тот же preflight и тот же POST from-orders,
// что у окна одной поставки (FbsSupplyCreateDialog). Окно одной поставки
// остаётся прежним и открывается, когда выбор укладывается в одну поставку (Д2).

export type FbsCreatedSupplyRef = { supplyId: string; orderIds: string[] }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  orders: FbsWorklistOrder[]
  open: boolean
  /** Закрыли окно; orderIds — заказы уже созданных поставок (их больше нет на «Новых»). */
  onClose: (createdOrderIds: string[]) => void
  /** Открыть окно сборки с созданными поставками — в порядке групп. */
  onOpenAssembly: (created: FbsCreatedSupplyRef[]) => void
}

type PreflightState = {
  busy: boolean
  result: FbsSupplyPreflight | null
  error: string | null
}

export function FbsSupplyGroupCreateDialog({
  token,
  authHeaders,
  orders,
  open,
  onClose,
  onOpenAssembly,
}: Props) {
  const [deliveryType, setDeliveryType] = useState<'warehouse_sc' | 'pvz'>('warehouse_sc')
  const [preflights, setPreflights] = useState<Record<string, PreflightState>>({})
  const [results, setResults] = useState<Map<string, FbsGroupCreateResult>>(() => new Map())
  const [creatingKey, setCreatingKey] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const keysRef = useRef(new Map<string, string>())
  const creatingRef = useRef(false)

  const groups = useMemo(() => groupFbsOrdersForSupplies(orders), [orders])
  const groupsSignature = useMemo(
    () => groups.map((group) => `${group.key}:${group.orderIds.join(',')}`).join(';'),
    [groups],
  )
  const createdGroups = groups.filter((group) => results.get(group.key)?.status === 'created')
  const anyCreated = createdGroups.length > 0

  // Новое открытие или другой выбор — новая попытка: результаты и ключи прежнего
  // выбора к нему не относятся.
  useEffect(() => {
    if (!open) return
    setDeliveryType('warehouse_sc')
    setResults(new Map())
    setCreatingKey(null)
    setAttempted(false)
    keysRef.current = new Map()
  }, [open, groupsSignature])

  // Сервер считает отпечаток запроса вместе со способом сдачи (I6 окна одной
  // поставки): при смене способа ключи несозданных групп обновляются.
  useEffect(() => {
    if (!open) return
    keysRef.current = new Map()
  }, [open, deliveryType])

  useEffect(() => {
    if (!open || groups.length === 0) {
      setPreflights((current) => (Object.keys(current).length ? {} : current))
      return
    }
    let active = true
    setPreflights(Object.fromEntries(groups.map((group) => [group.key, { busy: true, result: null, error: null }])))
    for (const group of groups) {
      void preflightFbsSupply(token, authHeaders, {
        order_ids: group.orderIds,
        planned_delivery_type: deliveryType,
      })
        .then((result) => {
          if (!active) return
          setPreflights((current) => ({ ...current, [group.key]: { busy: false, result, error: null } }))
        })
        .catch((cause: unknown) => {
          if (!active) return
          setPreflights((current) => ({
            ...current,
            [group.key]: {
              busy: false,
              result: null,
              error: cause instanceof Error ? cause.message : 'Не удалось проверить состав поставки.',
            },
          }))
        })
    }
    return () => {
      active = false
    }
    // groupsSignature покрывает groups; token/authHeaders — как у окна одной поставки.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, groupsSignature, deliveryType, token, authHeaders])

  const preflightBusy = groups.some((group) => preflights[group.key]?.busy !== false)
  const compatibleGroups = groups.filter((group) => preflights[group.key]?.result?.compatible)
  const pendingGroups = compatibleGroups.filter((group) => results.get(group.key)?.status !== 'created')

  const requestClose = () => {
    if (creatingRef.current) return
    if (!anyCreated && !confirmDiscardChanges(deliveryType !== 'warehouse_sc')) return
    onClose(createdGroups.flatMap((group) => group.orderIds))
  }

  const openAssembly = (finalResults: Map<string, FbsGroupCreateResult>) => {
    const created: FbsCreatedSupplyRef[] = []
    for (const group of groups) {
      const result = finalResults.get(group.key)
      if (result?.status === 'created') created.push({ supplyId: result.supplyId, orderIds: group.orderIds })
    }
    if (created.length > 0) onOpenAssembly(created)
  }

  const create = async () => {
    if (creatingRef.current || pendingGroups.length === 0) return
    creatingRef.current = true
    setCreating(true)
    try {
      const finalResults = await runFbsSupplyGroupCreation(
        pendingGroups,
        results,
        keysRef.current,
        (group: FbsSupplyGroupDraft, idempotencyKey: string) => createFbsSupplyFromOrders(token, authHeaders, {
          // Имя генерирует WMS — то же, что у окна одной поставки.
          name: `FBS ${new Date().toLocaleDateString('ru-RU')}`,
          order_ids: group.orderIds,
          planned_delivery_type: deliveryType,
          planned_destination: null,
          idempotency_key: idempotencyKey,
        }),
        {
          newKey: createFbsIdempotencyKey,
          isApiError: (cause) => cause instanceof FbsApiError,
          onProgress: (groupKey, result) => {
            if (result === 'creating') {
              setCreatingKey(groupKey)
              return
            }
            setCreatingKey(null)
            setResults((current) => new Map(current).set(groupKey, result))
          },
        },
      )
      setResults(finalResults)
      const allCreated = compatibleGroups.length > 0
        && compatibleGroups.every((group) => finalResults.get(group.key)?.status === 'created')
      // R3: окно сборки открывается после успеха всех групп; при частичном
      // успехе окно остаётся, у каждой группы виден её итог (R4).
      if (allCreated) openAssembly(finalResults)
    } finally {
      creatingRef.current = false
      setCreating(false)
      setCreatingKey(null)
      setAttempted(true)
    }
  }

  const groupStatus = (group: FbsSupplyGroupDraft) => {
    const result = results.get(group.key)
    if (creatingKey === group.key) {
      return (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <CircularProgress size={14} />
          <Typography variant="body2">Создаём поставку…</Typography>
        </Stack>
      )
    }
    if (result?.status === 'created') {
      return (
        <Typography variant="body2" sx={{ color: 'success.dark', fontWeight: 600 }}>
          Создана · {result.name}{result.wbSupplyId ? ` · WB № ${result.wbSupplyId}` : ''}
        </Typography>
      )
    }
    if (result) {
      return (
        <Typography variant="body2" color={result.status === 'pending' ? 'warning.dark' : 'error'}>
          {result.message}
        </Typography>
      )
    }
    const preflight = preflights[group.key]
    if (preflight?.error) {
      return <Typography variant="body2" color="error">{preflight.error}</Typography>
    }
    if (preflight?.result?.issues.length) {
      return (
        <Stack spacing={0.5}>
          {preflight.result.issues.map((issue) => (
            <Typography key={`${issue.order_id}-${issue.code}`} variant="body2" color="error">
              {fbsErrorText(issue.message)}
            </Typography>
          ))}
        </Stack>
      )
    }
    return null
  }

  // После первой попытки кнопка повторяет только несозданные группы (R4).
  const submitLabel = attempted
    ? `Повторить (${pendingGroups.length})`
    : `Создать поставки (${pendingGroups.length})`

  return (
    <Dialog open={open} onClose={creating ? undefined : requestClose} fullWidth maxWidth="md" data-testid="fbs-group-create-dialog">
      <DialogTitle component="div" sx={{ pb: 1 }}>
        <Typography component="h2" variant="h6">Новые поставки FBS</Typography>
        <Typography variant="body2" color="text.secondary">
          WMS разделит {orders.length} {ordersWord(orders.length)} на поставки по продавцу и складу WB и создаст каждую отдельно.
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2.5}>
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Планируемый способ сдачи
            </Typography>
            <RadioGroup
              row
              value={deliveryType}
              onChange={(event) => setDeliveryType(event.target.value as 'warehouse_sc' | 'pvz')}
            >
              <FormControlLabel
                value="warehouse_sc"
                control={<Radio />}
                label="Склад или сортировочный центр"
                disabled={creating || anyCreated}
              />
              <FormControlLabel
                value="pvz"
                control={<Radio />}
                label="Пункт выдачи"
                disabled={creating || anyCreated}
              />
            </RadioGroup>
            {deliveryType === 'pvz' ? (
              <Typography variant="caption" color="text.secondary">
                Конкретный ПВЗ заранее не закрепляется. Здесь проверяется только допустимость
                маршрута для каждого заказа.
              </Typography>
            ) : null}
          </Box>

          <Divider />

          <Stack spacing={2}>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
              <Chip
                color="success"
                label={`Разделено на ${groups.length} ${plural(groups.length, ['поставку', 'поставки', 'поставок'])}`}
                data-testid="fbs-group-create-count"
              />
              {preflightBusy ? (
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <CircularProgress size={18} />
                  <Typography variant="body2">Проверяем актуальный состав и остатки…</Typography>
                </Stack>
              ) : null}
            </Stack>

            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Селлер</TableCell>
                  <TableCell>Склад WB</TableCell>
                  <TableCell>Грузовой тип</TableCell>
                  <TableCell align="right">Заказов</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {groups.map((group) => {
                  const status = groupStatus(group)
                  return (
                    <Fragment key={group.key}>
                      <TableRow data-testid={`fbs-group-create-row-${group.key}`} sx={status ? { '& > td': { borderBottom: 0 } } : undefined}>
                        <TableCell>{group.sellerName}</TableCell>
                        <TableCell>{group.wbWarehouseName}</TableCell>
                        <TableCell>{group.cargoType}</TableCell>
                        <TableCell align="right">{group.orderIds.length}</TableCell>
                      </TableRow>
                      {status ? (
                        <TableRow>
                          <TableCell colSpan={4} sx={{ pt: 0 }} data-testid={`fbs-group-create-status-${group.key}`}>
                            {status}
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>

            {groups.length === 0 ? <Alert severity="warning">Нет ни одного выбранного заказа.</Alert> : null}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={requestClose} disabled={creating}>
          {anyCreated ? 'Закрыть' : 'Отмена'}
        </Button>
        {anyCreated ? (
          <Button
            variant="outlined"
            size="large"
            onClick={() => openAssembly(results)}
            disabled={creating}
            data-testid="fbs-group-open-assembly"
          >
            Открыть сборку
          </Button>
        ) : null}
        <Button
          variant="contained"
          size="large"
          onClick={() => void create()}
          disabled={pendingGroups.length === 0 || preflightBusy || creating}
          startIcon={creating ? <CircularProgress size={18} color="inherit" /> : undefined}
          data-testid="fbs-group-create-submit"
        >
          {submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
