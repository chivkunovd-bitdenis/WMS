import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import CloudSyncOutlinedIcon from '@mui/icons-material/CloudSyncOutlined'
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined'
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined'
import { DeadlinePill, FbsStatusChip } from '../../components/fbs/FbsChips'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { FbsSupplyCreateDialog } from './FbsSupplyCreateDialog'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import {
  fetchFbsWorklist,
  runFbsOrdersSync,
  syncFbsOrderStatuses,
  type FbsWorklistOrder,
  type FbsWorklistWarehouseOption,
  type FbsWorkspace,
} from './fbsApi'

type SellerRow = { id: string; name: string }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  sellers: SellerRow[]
  isAdmin?: boolean
}

const TABS = [
  { key: 'new', label: 'Новые' },
  { key: 'active', label: 'В работе' },
] as const

const EXTERNAL_WB_SUPPLY_HINT =
  'Поставку создали в кабинете Wildberries, а в WMS она не привязана. Открыть её здесь нельзя.'

function MissingText({ children }: { children: string }) {
  return (
    <Typography variant="caption" color="error.main" sx={{ fontWeight: 650 }}>
      {children}
    </Typography>
  )
}

function MetadataState({ order }: { order: FbsWorklistOrder }) {
  if (order.metadata.required.length === 0) {
    return null
  }
  const rejected = order.metadata.states.some((state) =>
    ['rejected', 'replacement_required'].includes(state.status),
  )
  const missing = order.metadata.states.filter((state) => state.status === 'missing').length
  return (
    <Chip
      size="small"
      variant="outlined"
      color={rejected ? 'error' : missing ? 'warning' : 'success'}
      label={rejected ? 'Отклонено WB' : missing ? `Не хватает: ${missing}` : 'Готово'}
    />
  )
}

function warehouseOptionLabel(option: FbsWorklistWarehouseOption) {
  return option.name || `WB ${option.wb_warehouse.id}`
}

export function FfFbsOrdersScreen({ token, authHeaders, sellers, isAdmin = false }: Props) {
  const [statusGroup, setStatusGroup] = useState<(typeof TABS)[number]['key']>('new')
  const [sellerId, setSellerId] = useState('__all__')
  const [wbWarehouseId, setWbWarehouseId] = useState('__all__')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [orders, setOrders] = useState<FbsWorklistOrder[]>([])
  const [warehouseOptions, setWarehouseOptions] = useState<FbsWorklistWarehouseOption[]>([])
  const [serverNow, setServerNow] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncNote, setSyncNote] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [workspaceSeed, setWorkspaceSeed] = useState<FbsWorkspace | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const page = await fetchFbsWorklist(token, authHeaders, {
        seller_id: sellerId === '__all__' ? null : sellerId,
        status_group: statusGroup,
        wb_warehouse_id: statusGroup === 'new' && wbWarehouseId !== '__all__' ? wbWarehouseId : null,
        search: appliedSearch || null,
        limit: 200,
      })
      setOrders(page.items)
      setWarehouseOptions(statusGroup === 'new' ? page.warehouse_options ?? [] : [])
      if (
        statusGroup === 'new' &&
        wbWarehouseId !== '__all__' &&
        !(page.warehouse_options ?? []).some((warehouse) => warehouse.id === wbWarehouseId)
      ) {
        setWbWarehouseId('__all__')
        setSelected(new Set())
      }
      setServerNow(page.server_now)
      setSelected((current) => {
        const visible = new Set(page.items.map((order) => order.id))
        return new Set([...current].filter((id) => visible.has(id)))
      })
    } catch (cause) {
      setOrders([])
      setWarehouseOptions([])
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить заказы FBS.')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, sellerId, statusGroup, wbWarehouseId, appliedSearch])

  useEffect(() => {
    void load()
  }, [load])

  // Ручной поход в Wildberries: тянем новые заказы и подтягиваем их статусы.
  // Автоопрос делает то же самое раз в минуту, но оператору нужна кнопка на случай,
  // когда ждать нельзя или фоновый воркер отвалился.
  const syncTargets = useMemo(
    () => (sellerId === '__all__' ? sellers.map((seller) => seller.id) : [sellerId]),
    [sellerId, sellers],
  )

  const syncWithWb = useCallback(async () => {
    if (syncTargets.length === 0) {
      setError('Нет ни одного селлера, по которому можно запросить заказы.')
      return
    }
    setSyncing(true)
    setError(null)
    setSyncNote(null)
    let received = 0
    let created = 0
    let statusesUpdated = 0
    const failures: string[] = []
    for (const targetSellerId of syncTargets) {
      const sellerName = sellers.find((seller) => seller.id === targetSellerId)?.name ?? 'селлер'
      try {
        const outcome = await runFbsOrdersSync(token, authHeaders, targetSellerId)
        received += outcome.ordersReceived
        created += outcome.ordersCreated
      } catch (cause) {
        failures.push(`${sellerName}: ${cause instanceof Error ? cause.message : 'ошибка синхронизации'}`)
        continue
      }
      try {
        statusesUpdated += await syncFbsOrderStatuses(token, authHeaders, targetSellerId)
      } catch {
        // Статусы — не критично: заказы уже приехали, покажем их и без обновлённых статусов.
      }
    }
    setSyncing(false)
    if (failures.length > 0) {
      setError(failures.join(' · '))
    }
    if (failures.length < syncTargets.length) {
      setSyncNote(
        `WB отдал заказов: ${received}, из них новых: ${created}. Обновлено статусов: ${statusesUpdated}.`,
      )
    }
    await load()
  }, [syncTargets, sellers, token, authHeaders, load])

  const selectedOrders = useMemo(
    () => orders.filter((order) => selected.has(order.id)),
    [orders, selected],
  )
  const selectedOrderIds = useMemo(() => [...selected], [selected])
  const selectionBlockers = useMemo(
    () => selectedOrders.flatMap((order) => order.selection_blockers.map((blocker) => ({ order, blocker }))),
    [selectedOrders],
  )
  const selectableIds = useMemo(
    () => orders.filter((order) => order.selection_blockers.length === 0).map((order) => order.id),
    [orders],
  )

  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const openWorkspace = (supplyId: string, seed?: FbsWorkspace) => {
    setWorkspaceId(supplyId)
    setWorkspaceSeed(seed ?? null)
    setWorkspaceOpen(true)
    setError(null)
  }

  return (
    <Box data-testid="fbs-orders-screen" sx={{ pb: selected.size ? 12 : 3 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        sx={{ justifyContent: 'space-between', gap: 2, mb: 1.5 }}
      >
        <Box>
          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
            <Inventory2OutlinedIcon color="primary" />
            <Typography variant="h5">Заказы FBS</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Соберите совместимые заказы в поставку и проведите её до подтверждённой передачи WB.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: 'flex-start' }}>
          <Button
            variant="outlined"
            startIcon={<RefreshOutlinedIcon />}
            onClick={() => void load()}
            disabled={busy || syncing}
          >
            Обновить данные
          </Button>
          <Button
            variant="contained"
            startIcon={
              syncing ? <CircularProgress size={18} color="inherit" /> : <CloudSyncOutlinedIcon />
            }
            onClick={() => void syncWithWb()}
            disabled={syncing || busy}
            data-testid="fbs-orders-sync-wb"
            sx={{ minWidth: 214 }}
          >
            {syncing ? 'Забираем заказы…' : 'Забрать заказы из WB'}
          </Button>
        </Stack>
      </Stack>

      <FfFbsSectionNav showStockSync={isAdmin} />

      <Paper variant="outlined" sx={{ overflow: 'hidden', mt: 2 }}>
        <Tabs
          value={statusGroup}
          onChange={(_, value) => {
            setStatusGroup(value)
            setWbWarehouseId('__all__')
            setSelected(new Set())
          }}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ px: 1.5, borderBottom: 1, borderColor: 'divider' }}
        >
          {TABS.map((tab) => (
            <Tab key={tab.key} value={tab.key} label={tab.label} />
          ))}
        </Tabs>

        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1.5}
          sx={{ p: 2, bgcolor: 'rgba(255,255,255,.75)' }}
        >
          <FormControl sx={{ minWidth: 230 }}>
            <InputLabel id="fbs-worklist-seller-label">Селлер</InputLabel>
            <Select
              labelId="fbs-worklist-seller-label"
              label="Селлер"
              value={sellerId}
              onChange={(event) => {
                setSellerId(String(event.target.value))
                setWbWarehouseId('__all__')
                setSelected(new Set())
              }}
            >
              <MenuItem value="__all__">Все селлеры</MenuItem>
              {sellers.map((seller) => (
                <MenuItem key={seller.id} value={seller.id}>
                  {seller.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          {statusGroup === 'new' ? (
            <FormControl sx={{ minWidth: 260 }}>
              <InputLabel id="fbs-worklist-warehouse-label">Склад селлера</InputLabel>
              <Select
                labelId="fbs-worklist-warehouse-label"
                label="Склад селлера"
                value={wbWarehouseId}
                onChange={(event) => {
                  setWbWarehouseId(String(event.target.value))
                  setSelected(new Set())
                }}
                data-testid="fbs-worklist-warehouse"
              >
                <MenuItem value="__all__">Все склады</MenuItem>
                {warehouseOptions.map((warehouse) => (
                  <MenuItem
                    key={warehouse.id}
                    value={warehouse.id}
                    data-testid={`fbs-worklist-warehouse-${warehouse.id}`}
                  >
                    {warehouseOptionLabel(warehouse)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : null}
          <TextField
            fullWidth
            label="Заказ, артикул или штрихкод"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') setAppliedSearch(search.trim())
            }}
          />
          <Button
            variant="contained"
            startIcon={<SearchOutlinedIcon />}
            onClick={() => setAppliedSearch(search.trim())}
            sx={{ minWidth: 130 }}
          >
            Найти
          </Button>
        </Stack>
      </Paper>

      {error ? (
        <Alert severity="error" sx={{ mt: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}

      {syncNote ? (
        <Alert
          severity="success"
          sx={{ mt: 2 }}
          onClose={() => setSyncNote(null)}
          data-testid="fbs-orders-sync-result"
        >
          {syncNote}
        </Alert>
      ) : null}

      <TableContainer component={Paper} variant="outlined" sx={{ mt: 2, maxHeight: 'calc(100vh - 330px)' }}>
        <Table stickyHeader size="small" data-testid="fbs-worklist-table">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                {statusGroup === 'new' ? (
                  <Checkbox
                    checked={selectableIds.length > 0 && selectableIds.every((id) => selected.has(id))}
                    indeterminate={selected.size > 0 && !selectableIds.every((id) => selected.has(id))}
                    onChange={(_, checked) => setSelected(new Set(checked ? selectableIds : []))}
                  />
                ) : null}
              </TableCell>
              <TableCell sx={{ minWidth: 270 }}>Товар</TableCell>
              <TableCell sx={{ minWidth: 125 }}>Селлер</TableCell>
              <TableCell sx={{ minWidth: 125 }}>Маршрут сдачи</TableCell>
              <TableCell sx={{ minWidth: 105 }}>Отгрузить до</TableCell>
              {statusGroup !== 'new' ? <TableCell sx={{ minWidth: 130 }}>Статус</TableCell> : null}
            </TableRow>
          </TableHead>
          <TableBody>
            {orders.map((order) => {
              const blocked = order.selection_blockers.length > 0
              const localSupplyMissing = statusGroup !== 'new' && !order.supply_id
              const row = (
                <TableRow
                  key={order.id}
                  hover={!localSupplyMissing}
                  selected={selected.has(order.id)}
                  sx={{
                    verticalAlign: 'top',
                    cursor: order.supply_id ? 'pointer' : 'default',
                    ...(localSupplyMissing
                      ? {
                          bgcolor: 'action.disabledBackground',
                          opacity: 0.72,
                          '&:hover': { bgcolor: 'action.disabledBackground' },
                        }
                      : {}),
                  }}
                  onClick={() => order.supply_id && openWorkspace(order.supply_id)}
                  data-testid={`fbs-order-${order.id}`}
                  aria-disabled={localSupplyMissing ? true : undefined}
                >
                  <TableCell padding="checkbox">
                    {statusGroup === 'new' ? (
                      <Checkbox
                        checked={selected.has(order.id)}
                        disabled={blocked}
                        onClick={(event) => event.stopPropagation()}
                        onChange={() => toggle(order.id)}
                      />
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1.25}>
                      <ProductPhotoThumb
                        src={order.product.image_url}
                        alt={order.product.name}
                        size={56}
                        previewSize={280}
                        testId={`fbs-product-photo-${order.id}`}
                      />
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="subtitle2" sx={{ lineHeight: 1.25 }}>
                          {order.product.id ? order.product.name : 'Товар не сопоставлен'}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Заказ WB №{order.wb_order_id}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Артикул: {order.product.seller_article ?? '—'}{order.product.wb_article ? ` · WB ${order.product.wb_article}` : ''}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          ШК: {order.product.barcode ?? '—'}{order.product.size ? ` · Размер: ${order.product.size}` : ''}
                        </Typography>
                        {statusGroup === 'new' && blocked ? (
                          <Stack sx={{ mt: 0.75 }} spacing={0.25}>
                            {order.selection_blockers.map((blocker) => (
                              <MissingText key={blocker.code}>{blocker.message}</MissingText>
                            ))}
                          </Stack>
                        ) : null}
                      </Box>
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{order.seller.name ?? '—'}</Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" label={order.can_pvz ? 'ПВЗ' : 'Склад / СЦ'} />
                    {order.buyer_type === 'legal' ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>Юридическое лицо</Typography> : null}
                  </TableCell>
                  <TableCell>
                    <DeadlinePill
                      deadlineAt={order.deadline_at}
                      serverNow={serverNow}
                      cancelled={order.status === 'cancelled'}
                    />
                  </TableCell>
                  {statusGroup !== 'new' ? (
                    <TableCell>
                      <FbsStatusChip status={order.status} />
                      <Stack sx={{ mt: 0.75, alignItems: 'flex-start' }} spacing={0.75}>
                        {localSupplyMissing ? (
                          <Tooltip title={EXTERNAL_WB_SUPPLY_HINT}>
                            <Chip
                              size="small"
                              variant="outlined"
                              color="warning"
                              label="Поставка создана в WB"
                              data-testid={`fbs-order-${order.id}-external-supply`}
                            />
                          </Tooltip>
                        ) : null}
                        <MetadataState order={order} />
                      </Stack>
                    </TableCell>
                  ) : null}
                </TableRow>
              )
              return (
                localSupplyMissing ? (
                  <Tooltip key={order.id} title={EXTERNAL_WB_SUPPLY_HINT} placement="top" arrow>
                    {row}
                  </Tooltip>
                ) : row
              )
            })}
            {!busy && orders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={statusGroup === 'new' ? 5 : 6}>
                  <Box sx={{ py: 8, textAlign: 'center' }}>
                    <Inventory2OutlinedIcon sx={{ fontSize: 42, color: 'text.disabled' }} />
                    <Typography variant="subtitle1" sx={{ mt: 1 }}>
                      Заказов в этой группе нет
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Измените фильтры или обновите синхронизацию с WB.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        {busy ? (
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'center', py: 2 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Обновляем рабочий список…</Typography>
          </Stack>
        ) : null}
      </TableContainer>

      {selected.size ? (
        <Paper
          elevation={8}
          sx={{
            position: 'fixed',
            left: { xs: 12, md: 280 },
            right: 20,
            bottom: 18,
            zIndex: 1200,
            px: 2.5,
            py: 1.5,
            border: 1,
            borderColor: selectionBlockers.length ? 'error.light' : 'primary.light',
          }}
          data-testid="fbs-selection-bar"
        >
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: { md: 'center' } }}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle2">Выбрано заказов: {selected.size}</Typography>
              <Typography variant="caption" color={selectionBlockers.length ? 'error.main' : 'text.secondary'}>
                {selectionBlockers.length
                  ? selectionBlockers[0].blocker.message
                  : 'Следующий шаг — серверная проверка состава и маршрута.'}
              </Typography>
            </Box>
            <Button onClick={() => setSelected(new Set())}>Снять выбор</Button>
            <Button
              variant="contained"
              size="large"
              disabled={selectionBlockers.length > 0}
              onClick={() => setCreateOpen(true)}
            >
              Сформировать поставку
            </Button>
          </Stack>
        </Paper>
      ) : null}

      <FbsSupplyCreateDialog
        token={token}
        authHeaders={authHeaders}
        orderIds={selectedOrderIds}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(workspace) => {
          setCreateOpen(false)
          setSelected(new Set())
          openWorkspace(workspace.supply.id, workspace)
          void load()
        }}
      />

      <FfFbsSupplyWorkspace
        token={token}
        authHeaders={authHeaders}
        supplyId={workspaceId}
        initialWorkspace={workspaceSeed}
        open={workspaceOpen}
        onClose={() => {
          setWorkspaceOpen(false)
          setWorkspaceSeed(null)
          void load()
        }}
      />

    </Box>
  )
}
