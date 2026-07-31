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
  DialogActions,
  DialogContent,
  DialogTitle,
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
import {
  addOrderToFbsSupply,
  createFbsSupply,
  fetchFbsOrders,
  TAB_STATUSES,
  type FbsOrderRow,
  type FbsOrdersTab,
} from './fbsApi'
import { FfFbsSupplyDrawer } from './FfFbsSupplyDrawer'
import {
  CargoTypeChip,
  DeadlinePill,
  FbsStatusChip,
  SellerBadge,
} from '../../components/fbs/FbsChips'

type SellerRow = { id: string; name: string }

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  sellers: SellerRow[]
}

const TABS: { key: FbsOrdersTab; label: string }[] = [
  { key: 'new', label: 'Новые' },
  { key: 'assembly', label: 'На сборке' },
  { key: 'delivery', label: 'В доставке' },
  { key: 'done', label: 'Завершённые' },
]

const priceFmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })

function formatWbDate(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('ru-RU')
}

function rowMatchesSearch(row: FbsOrderRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return (
    String(row.wb_order_id).includes(needle) ||
    (row.wb_article?.toLowerCase().includes(needle) ?? false) ||
    (row.wb_barcode?.toLowerCase().includes(needle) ?? false)
  )
}

export function FfFbsOrdersScreen({ token, authHeaders, sellers }: Props) {
  const [tab, setTab] = useState<FbsOrdersTab>('new')
  const [selectedSellerId, setSelectedSellerId] = useState<string>('__all__')
  const [search, setSearch] = useState('')
  const [orders, setOrders] = useState<FbsOrderRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Выделение заказов (вкладка «Новые») для создания отгрузки.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createDelivery, setCreateDelivery] = useState('warehouse_sc')
  const [creating, setCreating] = useState(false)

  // Карточка отгрузки (Экран 2).
  const [drawerSupplyId, setDrawerSupplyId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const sellerNameById = useMemo(() => {
    const m = new Map<string, string>()
    for (const s of sellers) m.set(s.id, s.name)
    return m
  }, [sellers])

  const load = useCallback(async () => {
    setError(null)
    setBusy(true)
    try {
      const rows = await fetchFbsOrders(token, authHeaders, {
        sellerId: selectedSellerId !== '__all__' ? selectedSellerId : null,
      })
      setOrders(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить заказы FBS')
      setOrders([])
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, selectedSellerId])

  useEffect(() => {
    void load()
  }, [load])

  const visibleOrders = useMemo(() => {
    const allowed = new Set(TAB_STATUSES[tab])
    return orders.filter((row) => allowed.has(row.status) && rowMatchesSearch(row, search))
  }, [orders, tab, search])

  const showCheckboxes = tab === 'new'

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const openSupply = useCallback((id: string) => {
    setDrawerSupplyId(id)
    setDrawerOpen(true)
  }, [])

  const handleCreateSupply = useCallback(async () => {
    const rows = orders.filter((o) => selected.has(o.id))
    if (rows.length === 0) return
    const sellerId = rows[0].seller_id
    const warehouseId = rows[0].warehouse_id
    if (rows.some((r) => r.seller_id !== sellerId || r.warehouse_id !== warehouseId)) {
      setError('В одну отгрузку можно объединить только заказы одного селлера и одного склада.')
      return
    }
    setCreating(true)
    setError(null)
    try {
      const supply = await createFbsSupply(token, authHeaders, {
        seller_id: sellerId,
        warehouse_id: warehouseId,
        name: createName.trim() || `Отгрузка ${new Date().toLocaleDateString('ru-RU')}`,
        delivery_type: createDelivery,
        cargo_type: rows[0].cargo_type,
        wb_office_id: rows[0].wb_office_id,
      })
      for (const r of rows) {
        await addOrderToFbsSupply(token, authHeaders, supply.id, r.id)
      }
      setCreateOpen(false)
      setCreateName('')
      setSelected(new Set())
      openSupply(supply.id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать отгрузку')
    } finally {
      setCreating(false)
    }
  }, [orders, selected, token, authHeaders, createName, createDelivery, openSupply, load])

  return (
    <Box data-testid="fbs-orders-screen">
      <Typography variant="h5" gutterBottom>
        FBS
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Заказы по модели «Маркетплейс»: сборка, отгрузка и передача в доставку.
      </Typography>

      <Tabs
        value={tab}
        onChange={(_, v) => {
          setTab(v as FbsOrdersTab)
          setSelected(new Set())
        }}
        sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
      >
        {TABS.map((t) => (
          <Tab key={t.key} value={t.key} label={t.label} data-testid={`fbs-orders-tab-${t.key}`} />
        ))}
      </Tabs>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="fbs-orders-error" onClose={() => setError(null)}>
          {error}
        </Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }} data-testid="fbs-orders-filters">
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' } }}>
          <FormControl size="small" sx={{ minWidth: 240 }}>
            <InputLabel id="fbs-seller-filter-label">Селлер</InputLabel>
            <Select
              labelId="fbs-seller-filter-label"
              label="Селлер"
              value={selectedSellerId}
              onChange={(e) => setSelectedSellerId(String(e.target.value))}
              data-testid="fbs-seller-filter"
            >
              <MenuItem value="__all__">Все</MenuItem>
              {sellers.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Поиск"
            placeholder="Номер задания, артикул, штрихкод"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ minWidth: 280, flexGrow: 1 }}
            slotProps={{ htmlInput: { 'data-testid': 'fbs-orders-search' } }}
          />
          {busy ? <CircularProgress size={18} data-testid="fbs-orders-loading" /> : null}
          <Button
            size="small"
            variant="text"
            onClick={() => void load()}
            disabled={busy}
            data-testid="fbs-orders-refresh"
            sx={{ ml: { sm: 'auto' } }}
          >
            Обновить
          </Button>
        </Stack>
      </Paper>

      <TableContainer
        component={Paper}
        variant="outlined"
        data-testid="fbs-orders-list"
        sx={{ maxHeight: 'calc(100vh - 300px)' }}
      >
        <Table stickyHeader size="small" data-testid="fbs-orders-table">
          <TableHead>
            <TableRow>
              {showCheckboxes ? <TableCell padding="checkbox" /> : null}
              <TableCell>Задание</TableCell>
              <TableCell>Товар</TableCell>
              <TableCell align="right" width={110}>
                Цена
              </TableCell>
              <TableCell width={180}>Селлер</TableCell>
              <TableCell width={90}>Тип</TableCell>
              <TableCell width={150}>Статус</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleOrders.map((row) => (
              <TableRow
                key={row.id}
                hover
                selected={selected.has(row.id)}
                onClick={() => (row.supply_id ? openSupply(row.supply_id) : showCheckboxes ? toggle(row.id) : undefined)}
                sx={{ cursor: 'pointer' }}
                data-testid="fbs-order-row"
                data-status={row.status}
                data-seller-id={row.seller_id}
              >
                {showCheckboxes ? (
                  <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selected.has(row.id)}
                      onChange={() => toggle(row.id)}
                      data-testid="fbs-order-checkbox"
                    />
                  </TableCell>
                ) : null}
                <TableCell>
                  <Stack spacing={0.5}>
                    <Typography variant="body2">№ {row.wb_order_id}</Typography>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                      <Typography variant="caption" color="text.secondary">
                        {formatWbDate(row.created_at_wb)}
                      </Typography>
                      <DeadlinePill deadlineAt={row.deadline_at} cancelled={row.status === 'cancelled'} />
                      {row.is_legal ? <Chip size="small" variant="outlined" label="Юрлицо" /> : null}
                    </Stack>
                  </Stack>
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <Avatar variant="rounded" sx={{ width: 36, height: 36 }}>
                      {(row.wb_article ?? row.wb_barcode ?? '#')[0]}
                    </Avatar>
                    <Stack spacing={0.25}>
                      <Typography variant="body2" sx={{ lineHeight: 1.2 }}>
                        {row.wb_article ?? row.wb_barcode ?? '—'}
                      </Typography>
                      <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                        <Typography variant="caption" color="text.secondary">
                          {row.wb_barcode ?? (row.wb_nm_id ? `nm ${row.wb_nm_id}` : '—')}
                        </Typography>
                        {row.mapping_status === 'missing' ? (
                          <Chip
                            size="small"
                            variant="outlined"
                            color="warning"
                            label="не сопоставлен"
                            data-testid="fbs-order-unmapped"
                          />
                        ) : null}
                      </Stack>
                    </Stack>
                  </Stack>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {row.price == null ? '—' : `${priceFmt.format(row.price)} ₽`}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                    <SellerBadge name={sellerNameById.get(row.seller_id) ?? null} />
                    {row.can_pvz ? <Chip size="small" variant="outlined" color="info" label="ПВЗ" /> : null}
                  </Stack>
                </TableCell>
                <TableCell>
                  <CargoTypeChip cargoType={row.cargo_type ?? '—'} />
                </TableCell>
                <TableCell>
                  <FbsStatusChip status={row.status} />
                </TableCell>
              </TableRow>
            ))}
            {!busy && visibleOrders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={showCheckboxes ? 7 : 6}>
                  <Box sx={{ py: 4, textAlign: 'center' }} data-testid="fbs-orders-empty">
                    <Typography variant="body2" color="text.secondary">
                      {search.trim() ? 'Ничего не найдено по запросу.' : 'Заказов в этой вкладке нет.'}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>

      {showCheckboxes && selected.size > 0 ? (
        <Paper
          variant="outlined"
          sx={{
            position: 'sticky',
            bottom: 8,
            mt: 2,
            p: 1.5,
            display: 'flex',
            alignItems: 'center',
            gap: 2,
          }}
          data-testid="fbs-orders-action-bar"
        >
          <Typography variant="body2">Выбрано заказов: {selected.size}</Typography>
          <Button variant="text" size="small" onClick={() => setSelected(new Set())}>
            Сбросить
          </Button>
          <Button
            variant="contained"
            sx={{ ml: 'auto' }}
            onClick={() => setCreateOpen(true)}
            data-testid="fbs-create-supply"
          >
            Создать отгрузку
          </Button>
        </Paper>
      ) : null}

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="xs" data-testid="fbs-create-supply-dialog">
        <DialogTitle>Новая отгрузка FBS</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Заказов в отгрузке: {selected.size}. В одной отгрузке — заказы одного селлера и склада.
            </Typography>
            <TextField
              label="Название"
              size="small"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="Отгрузка (по умолчанию — с датой)"
              fullWidth
            />
            <FormControl size="small" fullWidth>
              <InputLabel id="fbs-create-delivery-label">Куда</InputLabel>
              <Select
                labelId="fbs-create-delivery-label"
                label="Куда"
                value={createDelivery}
                onChange={(e) => setCreateDelivery(String(e.target.value))}
                data-testid="fbs-create-delivery"
              >
                <MenuItem value="warehouse_sc">Склад / СЦ</MenuItem>
                <MenuItem value="pvz">ПВЗ</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Отмена</Button>
          <Button
            variant="contained"
            onClick={() => void handleCreateSupply()}
            disabled={creating}
            data-testid="fbs-create-supply-submit"
          >
            {creating ? '…' : 'Создать'}
          </Button>
        </DialogActions>
      </Dialog>

      <FfFbsSupplyDrawer
        token={token}
        authHeaders={authHeaders}
        supplyId={drawerSupplyId}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onChanged={() => void load()}
      />
    </Box>
  )
}
