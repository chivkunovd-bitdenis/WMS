import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
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
import {
  CargoTypeChip,
  DeadlinePill,
  FbsStatusChip,
  SellerBadge,
} from '../../components/fbs/FbsChips'
import { FbsSupplyCreateDialog } from './FbsSupplyCreateDialog'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { fetchFbsWorklist, type FbsWorklistOrder, type FbsWorkspace } from './fbsApi'

type SellerRow = { id: string; name: string }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  sellers: SellerRow[]
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
  if (order.metadata.required.length === 0) {
    return <Chip size="small" variant="outlined" color="success" label="Не требуется" />
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

export function FfFbsOrdersScreen({ token, authHeaders, sellers }: Props) {
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
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const page = await fetchFbsWorklist(token, authHeaders, {
        seller_id: sellerId === '__all__' ? null : sellerId,
        status_group: statusGroup,
        search: appliedSearch || null,
        limit: 200,
      })
      setOrders(page.items)
      setServerNow(page.server_now)
      setSelected((current) => {
        const visible = new Set(page.items.map((order) => order.id))
        return new Set([...current].filter((id) => visible.has(id)))
      })
    } catch (cause) {
      setOrders([])
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить заказы FBS.')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, sellerId, statusGroup, appliedSearch])

  useEffect(() => {
    void load()
  }, [load])

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
        <Button
          variant="outlined"
          startIcon={<RefreshOutlinedIcon />}
          onClick={() => void load()}
          disabled={busy}
        >
          Обновить данные
        </Button>
      </Stack>

      <FfFbsSectionNav />

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
              <TableCell sx={{ minWidth: 310 }}>Товар и заказ</TableCell>
              <TableCell sx={{ minWidth: 190 }}>Селлер и склады</TableCell>
              <TableCell sx={{ minWidth: 180 }}>Остаток</TableCell>
              <TableCell sx={{ minWidth: 170 }}>Маршрут и данные</TableCell>
              <TableCell sx={{ minWidth: 145 }}>Срок</TableCell>
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
                  sx={{ verticalAlign: 'top' }}
                  data-testid={`fbs-order-${order.id}`}
                >
                  <TableCell padding="checkbox">
                    {statusGroup === 'new' ? (
                      <Checkbox
                        checked={selected.has(order.id)}
                        disabled={blocked}
                        onChange={() => toggle(order.id)}
                      />
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1.25}>
                      <Avatar
                        variant="rounded"
                        src={order.product.image_url ?? undefined}
                        onClick={() => order.product.image_url && setPreviewUrl(order.product.image_url)}
                        sx={{ width: 62, height: 72, cursor: order.product.image_url ? 'zoom-in' : 'default' }}
                      >
                        <Inventory2OutlinedIcon />
                      </Avatar>
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="subtitle2" sx={{ lineHeight: 1.25 }}>
                          {order.product.id ? order.product.name : 'Товар не сопоставлен'}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Заказ WB №{order.wb_order_id}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Артикул продавца: {order.product.seller_article ?? 'не указан'}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Артикул WB: {order.product.wb_article ?? 'не указан'} · ШК:{' '}
                          {order.product.barcode ?? 'не указан'}
                        </Typography>
                        {order.product.size ? (
                          <Chip size="small" label={`Размер ${order.product.size}`} sx={{ mt: 0.5 }} />
                        ) : null}
                        {blocked ? (
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
                    <Typography variant="body2" sx={{ mt: 0.75 }}>
                      WB: {order.wb_warehouse.name ?? `ID ${order.wb_warehouse.id}`}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      WMS: {order.wms_warehouse.name}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography
                      variant="body2"
                      color={order.inventory.available_unpacked > 0 ? 'success.main' : 'error.main'}
                      sx={{ fontWeight: 750 }}
                    >
                      Доступно: {order.inventory.available_unpacked}
                    </Typography>
                    {order.inventory.locations.length ? (
                      order.inventory.locations.map((location) => (
                        <Typography key={location.id} variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          {location.code}: {location.available_unpacked}
                        </Typography>
                      ))
                    ) : (
                      <MissingText>Ячейка не назначена</MissingText>
                    )}
                    {order.inventory.available_unpacked <= 0 ? (
                      <MissingText>Остаток отсутствует</MissingText>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }} useFlexGap>
                      <CargoTypeChip cargoType={order.cargo_type} />
                      <Chip
                        size="small"
                        variant="outlined"
                        color={order.can_pvz ? 'success' : 'default'}
                        label={order.can_pvz ? 'Можно в ПВЗ' : 'Только склад/СЦ'}
                      />
                      <Chip
                        size="small"
                        variant="outlined"
                        label={order.buyer_type === 'legal' ? 'Юрлицо' : 'Физлицо'}
                      />
                    </Stack>
                    <Box sx={{ mt: 1 }}>
                      <MetadataState order={order} />
                    </Box>
                  </TableCell>
                  <TableCell>
                    <DeadlinePill deadlineAt={order.deadline_at} serverNow={serverNow} />
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                      Создан {new Date(order.created_at_wb).toLocaleString('ru-RU')}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <FbsStatusChip status={order.status} />
                    {order.supply_id ? (
                      <Button size="small" sx={{ mt: 0.75 }} onClick={() => openWorkspace(order.supply_id!)}>
                        Открыть поставку
                      </Button>
                    ) : null}
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

      <Dialog open={Boolean(previewUrl)} onClose={() => setPreviewUrl(null)} maxWidth="md">
        <DialogContent sx={{ p: 1 }}>
          {previewUrl ? <Box component="img" src={previewUrl} alt="Фото товара" sx={{ maxWidth: '80vw', maxHeight: '80vh' }} /> : null}
        </DialogContent>
      </Dialog>
    </Box>
  )
}
