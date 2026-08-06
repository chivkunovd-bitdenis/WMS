import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  Typography,
} from '@mui/material'
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined'
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined'
import { DeadlinePill, FbsMarkingStatusChip, FbsStatusChip, SellerBadge } from '../../components/fbs/FbsChips'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { FbsSupplyCreateDialog } from './FbsSupplyCreateDialog'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { fetchFbsWorklist, type FbsWorklistOrder, type FbsWorkspace } from './fbsApi'
import { createLatestRequestGuard } from './fbsUx'

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
  { key: 'delivery', label: 'В доставке' },
  { key: 'done', label: 'Завершённые' },
  { key: 'cancelled', label: 'Отменённые' },
] as const

function MissingText({ children }: { children: string }) {
  return (
    <Typography variant="caption" color="error.main" sx={{ fontWeight: 650 }}>
      {children}
    </Typography>
  )
}

function MetadataState({ order }: { order: FbsWorklistOrder }) {
  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }} useFlexGap>
      <Typography variant="caption" color="text.secondary">Маркировка:</Typography>
      <FbsMarkingStatusChip required={order.metadata.required} states={order.metadata.states} />
    </Stack>
  )
}

export function FfFbsOrdersScreen({ token, authHeaders, sellers, isAdmin = false }: Props) {
  const [statusGroup, setStatusGroup] = useState<(typeof TABS)[number]['key']>('new')
  const [sellerId, setSellerId] = useState('__all__')
  const [search, setSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [orders, setOrders] = useState<FbsWorklistOrder[]>([])
  const [serverNow, setServerNow] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [workspaceSeed, setWorkspaceSeed] = useState<FbsWorkspace | null>(null)
  const worklistRequestGuard = useRef(createLatestRequestGuard()).current

  const load = useCallback(async (silent = false) => {
    const requestGeneration = worklistRequestGuard.begin()
    if (!silent) {
      setBusy(true)
      setError(null)
    }
    try {
      const page = await fetchFbsWorklist(token, authHeaders, {
        seller_id: sellerId === '__all__' ? null : sellerId,
        status_group: statusGroup,
        search: appliedSearch || null,
        limit: 200,
      })
      if (!worklistRequestGuard.isCurrent(requestGeneration)) return
      setOrders(page.items)
      setServerNow(page.server_now)
      setSelected((current) => {
        const visible = new Set(page.items.map((order) => order.id))
        return new Set([...current].filter((id) => visible.has(id)))
      })
    } catch (cause) {
      if (!worklistRequestGuard.isCurrent(requestGeneration)) return
      setOrders([])
      if (!silent) setError(cause instanceof Error ? cause.message : 'Не удалось загрузить заказы FBS.')
    } finally {
      if (!silent && worklistRequestGuard.isCurrent(requestGeneration)) setBusy(false)
    }
  }, [token, authHeaders, sellerId, statusGroup, appliedSearch, worklistRequestGuard])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !workspaceOpen) void load(true)
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [load, workspaceOpen])

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
            Соберите совместимые заказы в поставку, подготовьте обязательные QR и завершите работу.
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<RefreshOutlinedIcon />}
          onClick={() => void load()}
          disabled={busy}
        >
          Обновить данные
        </Button>
      </Stack>

      <FfFbsSectionNav showStockSync={isAdmin} />

      <Paper variant="outlined" sx={{ overflow: 'hidden', mt: 2 }}>
        <Tabs
          value={statusGroup}
          onChange={(_, value) => {
            setStatusGroup(value)
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
              onChange={(event) => setSellerId(String(event.target.value))}
            >
              <MenuItem value="__all__">Все селлеры</MenuItem>
              {sellers.map((seller) => (
                <MenuItem key={seller.id} value={seller.id}>
                  {seller.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
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
              <TableCell sx={{ minWidth: 105 }}>Селлер</TableCell>
              <TableCell sx={{ minWidth: 125 }}>Маршрут сдачи</TableCell>
              <TableCell sx={{ minWidth: 125 }}>Ячейка и остаток</TableCell>
              <TableCell sx={{ minWidth: 95 }}>Отгрузить до</TableCell>
              <TableCell sx={{ minWidth: 130 }}>Статус</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {orders.map((order) => {
              const blocked = order.selection_blockers.length > 0
              return (
                <TableRow
                  key={order.id}
                  hover
                  selected={selected.has(order.id)}
                  tabIndex={order.supply_id ? 0 : undefined}
                  role={order.supply_id ? 'button' : undefined}
                  aria-label={order.supply_id ? `Открыть поставку заказа WB №${order.wb_order_id}` : undefined}
                  onClick={() => order.supply_id && openWorkspace(order.supply_id)}
                  onKeyDown={(event) => {
                    if (order.supply_id && ['Enter', ' '].includes(event.key)) {
                      event.preventDefault()
                      openWorkspace(order.supply_id)
                    }
                  }}
                  sx={{
                    verticalAlign: 'top',
                    cursor: order.supply_id ? 'pointer' : 'default',
                    '&:focus-visible': order.supply_id
                      ? { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: -2 }
                      : undefined,
                  }}
                  data-testid={`fbs-order-${order.id}`}
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
                        size={64}
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
                    <SellerBadge name={order.seller.name} />
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      variant="outlined"
                      color={order.can_pvz ? 'success' : 'default'}
                      label={order.can_pvz ? 'Можно в ПВЗ' : 'Только склад / СЦ'}
                    />
                    {order.buyer_type === 'legal' ? (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                        Юридическое лицо
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {statusGroup === 'new' ? (
                      <Typography
                        variant="body2"
                        color={order.inventory.available_unpacked > 0 ? 'success.main' : 'error.main'}
                        sx={{ fontWeight: 750 }}
                      >
                        Доступно: {order.inventory.available_unpacked}
                      </Typography>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        {order.pick.status === 'picked' ? 'Товар подобран' : 'Смотрите этап поставки'}
                      </Typography>
                    )}
                    {statusGroup === 'new' && order.inventory.locations.length ? (
                      order.inventory.locations.map((location) => (
                        <Typography key={location.id} variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          {location.code}: {location.available_unpacked}
                        </Typography>
                      ))
                    ) : statusGroup === 'new' ? (
                      <MissingText>Ячейка не назначена</MissingText>
                    ) : null}
                    {statusGroup === 'new' && order.inventory.available_unpacked <= 0 ? (
                      <MissingText>Остаток отсутствует</MissingText>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <DeadlinePill
                      deadlineAt={order.deadline_at}
                      serverNow={serverNow}
                      cancelled={order.status === 'cancelled'}
                    />
                  </TableCell>
                  <TableCell>
                    <FbsStatusChip status={order.status} />
                    <Box sx={{ mt: 0.75 }}><MetadataState order={order} /></Box>
                  </TableCell>
                </TableRow>
              )
            })}
            {!busy && orders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
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
