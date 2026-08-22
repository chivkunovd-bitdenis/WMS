import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Alert,
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
  Link,
  InputAdornment,
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
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined'
import Inventory2OutlinedIcon from '@mui/icons-material/Inventory2Outlined'
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined'
import { apiUrl } from '../../api'
import { FbsStatusChip } from '../../components/fbs/FbsChips'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { FbsSupplyCreateDialog } from './FbsSupplyCreateDialog'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import { ordersWord } from './fbsUx'
import { plural } from '../../utils/plural'
import {
  fetchFbsSellerWarehouses,
  fetchFbsSupplyWorklist,
  fetchFbsWorklist,
  addFbsOrdersToSupply,
  createFbsIdempotencyKey,
  runFbsOrdersSync,
  syncFbsOrderStatuses,
  type FbsSupplyWorklistItem,
  type FbsWorklistOrder,
  type FbsWorklistWarehouseOption,
  type FbsWorkspace,
} from './fbsApi'
import { WarehouseContextSwitch, type WarehouseOption } from '../../ui-kit'

const FBS_WMS_WAREHOUSE_SESSION_KEY = 'wms_operational_warehouse:fulfillment'

type SellerRow = { id: string; name: string }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  sellers: SellerRow[]
  isAdmin?: boolean
}

// Порядок вкладок — единственный источник истины для UI; заказчик 16.08 попросил
// подвинуть «Просрочены» после «В доставке» (раньше стояла сразу за «Новыми»).
const TABS = [
  { key: 'new', label: 'Новые' },
  { key: 'active', label: 'В работе' },
  { key: 'delivery', label: 'В доставке' },
  { key: 'expired', label: 'Просрочены' },
  { key: 'done', label: 'Завершённые' },
  { key: 'cancelled', label: 'Отменённые' },
] as const

type FbsStatusGroup = (typeof TABS)[number]['key']

const NEW_ORDERS_PAGE_LIMIT = 500

// HANDOFF-POLISH.md пул 1 п.4 (решение П3): «В работе», «В доставке» и «Завершённые» —
// это работа с уже собранным документом (поставкой) целиком, не с отдельными заказами.
// Бэкенд уже отдаёт поставки для всех трёх (fbs_supply_service.list_supply_worklist),
// раньше фронт звал это только для 'active'.
function isFbsSupplyGroup(group: FbsStatusGroup): group is 'active' | 'delivery' | 'done' {
  return group === 'active' || group === 'delivery' || group === 'done'
}

const SUPPLY_EMPTY_STATE: Record<'active' | 'delivery' | 'done', { title: string; hint: string }> = {
  active: {
    title: 'Поставок в работе нет',
    hint: 'Создайте поставку на вкладке «Новые» или обновите список.',
  },
  delivery: {
    title: 'Поставок в доставке нет',
    hint: 'Поставки появятся здесь после передачи в доставку.',
  },
  done: {
    title: 'Завершённых поставок нет',
    hint: 'Поставки появятся здесь после приёмки Wildberries.',
  },
}

const EXTERNAL_WB_SUPPLY_HINT =
  'Поставку создали в кабинете Wildberries, а в WMS она не привязана. Открыть её здесь нельзя.'
const SEARCH_NO_MATCH_NOTICE = 'Совпадений не найдено, список не изменён.'

function MissingText({ children }: { children: string }) {
  return (
    <Typography variant="caption" color="error.main" sx={{ fontWeight: 650 }}>
      {children}
    </Typography>
  )
}

// BL-4 (16.08, FBS-02): блокер "склад WB не привязан" — не просто упрёк, а понятная
// подсказка с действием. Привязка делается на соседней вкладке «Остатки WB» того же
// раздела FBS, поэтому клик по подписи ведёт туда через тот же react-router, которым
// пользуется FfFbsSectionNav.
function BlockerLine({
  blocker,
  onGoToStockSync,
}: {
  blocker: { code: string; message: string }
  onGoToStockSync: () => void
}) {
  if (blocker.code === 'warehouse_unmapped') {
    return (
      <Link
        component="button"
        type="button"
        color="error"
        underline="hover"
        sx={{ fontWeight: 650, fontSize: '0.75rem', textAlign: 'left' }}
        onClick={(event) => {
          event.stopPropagation()
          onGoToStockSync()
        }}
        data-testid="fbs-warehouse-unmapped-link"
        data-task-id="FBS-02"
      >
        Склад WB не привязан — привязать на «Остатках WB»
      </Link>
    )
  }
  return <MissingText>{blocker.message}</MissingText>
}

// ProductPhotoThumb сам проверяет ссылку через Image(). Без этой обёртки экран с
// 500 заказами одновременно запускал 500 проверок фото, хотя оператор видел лишь
// несколько строк. Подключаем реальный src только рядом с видимой областью.
function LazyProductPhotoThumb({
  src,
  alt,
  size,
  previewSize,
  testId,
}: {
  src: string | null | undefined
  alt: string
  size: number
  previewSize: number
  testId: string
}) {
  const anchorRef = useRef<HTMLSpanElement | null>(null)
  const [nearViewport, setNearViewport] = useState(false)

  useEffect(() => {
    const node = anchorRef.current
    if (!node || nearViewport) return undefined
    if (!('IntersectionObserver' in window)) {
      setNearViewport(true)
      return undefined
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setNearViewport(true)
        observer.disconnect()
      },
      { rootMargin: '320px 0px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [nearViewport])

  return (
    <Box
      component="span"
      ref={anchorRef}
      sx={{ display: 'inline-flex', width: size, height: size, flex: '0 0 auto' }}
    >
      <ProductPhotoThumb
        src={nearViewport ? src : null}
        alt={alt}
        size={size}
        previewSize={previewSize}
        testId={testId}
      />
    </Box>
  )
}

type NewOrderRowProps = {
  order: FbsWorklistOrder
  selected: boolean
  highlighted: boolean
  serverNow: string | null
  registerRow: (id: string, node: HTMLTableRowElement | null) => void
  onToggle: (order: FbsWorklistOrder) => void
  onOpenWorkspace: (supplyId: string) => void
  onGoToStockSync: () => void
}

// Клик по одной галке меняет selected только у одной строки. React.memo не даёт
// остальным 499 тяжёлым строкам заново строить фото, подсказки и типографику.
const NewOrderRow = memo(function NewOrderRow({
  order,
  selected,
  highlighted,
  serverNow,
  registerRow,
  onToggle,
  onOpenWorkspace,
  onGoToStockSync,
}: NewOrderRowProps) {
  const blocked = order.selection_blockers.length > 0
  return (
    <TableRow
      ref={(node) => registerRow(order.id, node)}
      hover
      selected={selected}
      sx={{
        verticalAlign: 'top',
        cursor: order.supply_id ? 'pointer' : 'default',
        scrollMarginBottom: '220px',
        '& > td': { py: 0.9 },
        ...(highlighted
          ? {
              bgcolor: 'rgba(255, 214, 102, 0.24)',
              '&:hover': { bgcolor: 'rgba(255, 214, 102, 0.32)' },
            }
          : {}),
      }}
      onClick={() => order.supply_id && onOpenWorkspace(order.supply_id)}
      data-testid={`fbs-order-${order.id}`}
    >
      <TableCell padding="checkbox">
        <Checkbox
          checked={selected}
          disabled={blocked}
          onClick={(event) => event.stopPropagation()}
          onChange={() => onToggle(order)}
        />
      </TableCell>
      <TableCell>
        <Stack direction="row" spacing={1.25}>
          <LazyProductPhotoThumb
            src={order.product.image_url}
            alt={order.product.name}
            size={44}
            previewSize={280}
            testId={`fbs-product-photo-${order.id}`}
          />
          <Box sx={{ minWidth: 0 }}>
            <Tooltip title={order.product.id ? order.product.name : 'Товар не сопоставлен'}>
              <Typography variant="subtitle2" noWrap sx={{ lineHeight: 1.25, maxWidth: 150 }}>
                {order.product.id ? order.product.name : 'Товар не сопоставлен'}
              </Typography>
            </Tooltip>
            {blocked ? (
              <Stack sx={{ mt: 0.75 }} spacing={0.25}>
                {order.selection_blockers.map((blocker) => (
                  <BlockerLine
                    key={blocker.code}
                    blocker={blocker}
                    onGoToStockSync={onGoToStockSync}
                  />
                ))}
              </Stack>
            ) : null}
          </Box>
        </Stack>
      </TableCell>
      <TableCell>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          WB №{order.wb_order_id}
        </Typography>
        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block', maxWidth: 170 }}>
          ШК: {order.product.barcode ?? '—'}
        </Typography>
        {order.product.sku ? (
          <Tooltip title={order.product.sku}>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block', maxWidth: 170 }}>
              SKU {order.product.sku}
            </Typography>
          </Tooltip>
        ) : order.product.seller_article ? (
          <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block', maxWidth: 170 }}>
            Артикул: {order.product.seller_article}
          </Typography>
        ) : null}
      </TableCell>
      <TableCell>
        <Tooltip title={order.seller.name ?? '—'}>
          <Typography variant="body2" noWrap sx={{ maxWidth: 100 }}>{order.seller.name ?? '—'}</Typography>
        </Tooltip>
        {order.buyer_type === 'legal' ? (
          <Typography variant="caption" color="text.secondary">
            Юридическое лицо
          </Typography>
        ) : null}
      </TableCell>
      <TableCell>
        <Tooltip title={order.wb_warehouse.name || `WB ${order.wb_warehouse.id}`}>
          <Typography variant="body2" noWrap sx={{ fontWeight: 650, maxWidth: 145 }}>
            {order.wb_warehouse.name || `WB ${order.wb_warehouse.id}`}
          </Typography>
        </Tooltip>
        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block', maxWidth: 145 }}>
          WMS: {order.wms_warehouse.name}
        </Typography>
      </TableCell>
      <TableCell>
        <Typography variant="body2">{formatDateTime(order.created_at_wb)}</Typography>
        <Typography variant="caption" color="text.secondary">
          В сборке: {elapsedSince(order.created_at_wb, serverNow)}
        </Typography>
      </TableCell>
    </TableRow>
  )
})

// GLOBAL-02: единственное состояние строки, которое реально мешает оператору
// отгрузить заказ, — незакрытая маркировка Честным знаком. «Не хватает: N» с прошлого
// стейджа заказчик прочитал как нехватку товара на складе — на деле это нехватка кодов
// маркировки (order.metadata), поэтому подпись теперь называет вещь напрямую и красный
// цвет держится только за тем, что действительно блокирует работу.
type MetadataProblem = { label: string; color: 'error' }

function metadataProblem(order: FbsWorklistOrder): MetadataProblem | null {
  if (order.metadata.required.length === 0) {
    return null
  }
  const rejected = order.metadata.states.some((state) =>
    ['rejected', 'replacement_required'].includes(state.status),
  )
  if (rejected) return { label: 'Отклонено WB', color: 'error' }
  const missing = order.metadata.states.filter((state) => state.status === 'missing').length
  if (missing > 0) return { label: `Не хватает честных знаков: ${missing}`, color: 'error' }
  return null
}

function warehouseOptionLabel(
  option: FbsWorklistWarehouseOption,
  sellerWarehouseNames: Record<string, string>,
) {
  return sellerWarehouseNames[option.id] || option.name || option.wb_warehouse.name || `WB ${option.wb_warehouse.id}`
}

function normalizeSearch(value: string): string {
  return value.trim().toLocaleLowerCase('ru-RU')
}

function orderSearchText(order: FbsWorklistOrder): string {
  return [
    order.wb_order_id,
    order.product.name,
    order.product.category,
    order.product.seller_article,
    order.product.wb_article,
    order.product.barcode,
    order.product.sku,
    order.product.chrt_id,
    order.product.color,
    order.product.size,
  ]
    .filter((value) => value !== null && value !== undefined && String(value).trim())
    .join(' ')
    .toLocaleLowerCase('ru-RU')
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatNullableDateTime(value: string | null): string {
  return value ? formatDateTime(value) : '—'
}

function supplyStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    // «Состав» — это название первой вкладки внутри карточки поставки, а не статус
    // документа. В списке поставок черновик должен называться черновиком.
    draft: 'Черновик',
    assembling: 'В работе',
    packed: 'Готова к сдаче',
    in_delivery: 'В доставке',
    done: 'Завершена',
  }
  return labels[status] ?? 'Статус уточняется'
}

function supplyStatusColor(status: string): 'default' | 'primary' | 'success' | 'warning' {
  if (status === 'done') return 'success'
  if (status === 'in_delivery') return 'primary'
  if (status === 'draft' || status === 'assembling' || status === 'packed') return 'warning'
  return 'default'
}

function elapsedSince(value: string, serverNow: string | null): string {
  const start = new Date(value).getTime()
  const end = serverNow ? new Date(serverNow).getTime() : Date.now()
  const minutes = Math.max(0, Math.floor((end - start) / 60000))
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  if (days > 0) return `${days} д ${hours} ч`
  if (hours > 0) return `${hours} ч ${mins} мин`
  return `${mins} мин`
}

// Задача 9 пула (HANDOFF-POLISH.md): отметка свежести данных — сколько прошло с последней
// успешной загрузки списка.
function formatFreshness(lastLoadedAt: string | null): string | null {
  if (!lastLoadedAt) return null
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(lastLoadedAt).getTime()) / 60000))
  if (minutes < 1) return 'Обновлено только что'
  return `Обновлено ${minutes} ${plural(minutes, ['минуту', 'минуты', 'минут'])} назад`
}

function excelCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? '' : String(value)
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function downloadOrdersExcel(rows: FbsWorklistOrder[]): void {
  const headers = [
    'Наименование',
    'Артикул продавца',
    'Цвет',
    'Размер',
    'Склад селлера WB',
    'Номер заказа WB',
    'ШК/SKU',
    'Количество',
  ]
  const bodyRows = rows.map((order) => [
    order.product.name,
    order.product.seller_article,
    order.product.color,
    order.product.size,
    order.wb_warehouse.name || `WB ${order.wb_warehouse.id}`,
    order.wb_order_id,
    [order.product.barcode, order.product.sku].filter(Boolean).join(' / '),
    1,
  ])
  const html = [
    '<html><head><meta charset="utf-8" /></head><body><table>',
    `<thead><tr>${headers.map((header) => `<th>${excelCell(header)}</th>`).join('')}</tr></thead>`,
    `<tbody>${bodyRows
      .map((row) => `<tr>${row.map((cell) => `<td>${excelCell(cell)}</td>`).join('')}</tr>`)
      .join('')}</tbody>`,
    '</table></body></html>',
  ].join('')
  const blob = new Blob([html], { type: 'application/vnd.ms-excel;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `fbs-new-orders-${new Date().toISOString().slice(0, 10)}.xls`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function FfFbsOrdersScreen({ token, authHeaders, sellers, isAdmin = false }: Props) {
  const location = useLocation()
  const navigate = useNavigate()
  const [statusGroup, setStatusGroup] = useState<(typeof TABS)[number]['key']>('new')
  const [sellerId, setSellerId] = useState('__all__')
  const [wbWarehouseId, setWbWarehouseId] = useState('__all__')
  const [search, setSearch] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [orders, setOrders] = useState<FbsWorklistOrder[]>([])
  const [activeSupplies, setActiveSupplies] = useState<FbsSupplyWorklistItem[]>([])
  const [externalActiveOrders, setExternalActiveOrders] = useState<FbsWorklistOrder[]>([])
  const [warehouseOptions, setWarehouseOptions] = useState<FbsWorklistWarehouseOption[]>([])
  const [wmsWarehouseOptions, setWmsWarehouseOptions] = useState<WarehouseOption[]>([])
  const [sellerWarehouseNames, setSellerWarehouseNames] = useState<Record<string, string>>({})
  const [serverNow, setServerNow] = useState<string | null>(null)
  const [lastLoadedAt, setLastLoadedAt] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [selectedCache, setSelectedCache] = useState<Map<string, FbsWorklistOrder>>(new Map())
  const [selectedOpen, setSelectedOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncNote, setSyncNote] = useState<string | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [syncWarning, setSyncWarning] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [addExistingOpen, setAddExistingOpen] = useState(false)
  const [addExistingSupplyId, setAddExistingSupplyId] = useState('')
  const [addingExisting, setAddingExisting] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [workspaceSeed, setWorkspaceSeed] = useState<FbsWorkspace | null>(null)
  const [wmsWarehouseId, setWmsWarehouseId] = useState<string | null>(() => {
    try {
      return window.sessionStorage.getItem(FBS_WMS_WAREHOUSE_SESSION_KEY)
    } catch {
      return null
    }
  })
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const registerRow = useCallback((id: string, node: HTMLTableRowElement | null) => {
    rowRefs.current[id] = node
  }, [])
  const goToStockSync = useCallback(() => navigate('/app/ff/fbs/stock-sync'), [navigate])
  const openedSupplyFromQuery = useRef<string | null>(null)
  const loadingRef = useRef(false)
  // Плавающая панель выбора (fbs-selection-bar) прибита к низу вьюпорта и накрывает
  // собой последние строки таблицы — оператор кликал по чекбоксу второго заказа и
  // попадал в панель (см. tests-e2e/ff-fbs-orders.spec.ts:277). Меряем реальную высоту
  // панели и резервируем под неё место в TableContainer, а не поднимаем z-index/двигаем
  // панель — так нижние строки остаются кликабельными при любой высоте панели.
  const selectionBarRef = useRef<HTMLDivElement | null>(null)
  const [selectionBarHeight, setSelectionBarHeight] = useState(0)
  const visibleOrders = useMemo(() => wmsWarehouseId ? orders.filter((item) => item.wms_warehouse.id === wmsWarehouseId) : orders, [orders, wmsWarehouseId])
  const visibleSupplies = useMemo(() => wmsWarehouseId ? activeSupplies.filter((item) => item.wms_warehouse.id === wmsWarehouseId) : activeSupplies, [activeSupplies, wmsWarehouseId])
  const visibleExternalOrders = useMemo(() => wmsWarehouseId ? externalActiveOrders.filter((item) => item.wms_warehouse.id === wmsWarehouseId) : externalActiveOrders, [externalActiveOrders, wmsWarehouseId])
  useEffect(() => {
    if (wmsWarehouseOptions.length === 1) setWmsWarehouseId(wmsWarehouseOptions[0].id)
    if (wmsWarehouseId && !wmsWarehouseOptions.some((option) => option.id === wmsWarehouseId)) setWmsWarehouseId(null)
  }, [wmsWarehouseOptions, wmsWarehouseId])

  useEffect(() => {
    try {
      if (wmsWarehouseId) window.sessionStorage.setItem(FBS_WMS_WAREHOUSE_SESSION_KEY, wmsWarehouseId)
      else window.sessionStorage.removeItem(FBS_WMS_WAREHOUSE_SESSION_KEY)
    } catch {
      // Session storage is optional; the screen still works for the current mount.
    }
  }, [wmsWarehouseId])

  useEffect(() => {
    let cancelled = false
    void fetch(apiUrl('/warehouses'), { headers: authHeaders(token) })
      .then(async (response) => {
        if (!response.ok) throw new Error('Не удалось загрузить склады.')
        return (await response.json()) as Array<{ id?: string; name?: string; is_operational?: boolean }>
      })
      .then((warehouses) => {
        if (cancelled) return
        setWmsWarehouseOptions(warehouses
          .filter((warehouse) => warehouse.is_operational !== false && warehouse.id && warehouse.name?.trim())
          .map((warehouse) => ({ id: String(warehouse.id), name: warehouse.name!.trim() })))
      })
      .catch(() => {
        if (!cancelled) setWarehouseOptions([])
      })
    return () => { cancelled = true }
  }, [authHeaders, token])

  const load = useCallback(async () => {
    // Задача 9 пула (HANDOFF-POLISH.md): поллинг не должен наслаиваться сам на себя —
    // если предыдущий запрос ещё летит, новый тик пропускаем.
    if (loadingRef.current) return
    loadingRef.current = true
    setBusy(true)
    setError(null)
    try {
      if (isFbsSupplyGroup(statusGroup)) {
        // Задача 4 пула (HANDOFF-POLISH.md, решение П3): «В работе», «В доставке» и
        // «Завершённые» показывают поставки, не отдельные заказы; ordersPage тут нужен
        // только чтобы найти заказы WB без локальной карточки поставки в WMS.
        const params = {
          seller_id: sellerId === '__all__' ? null : sellerId,
          status_group: statusGroup,
          limit: 500,
        }
        const [suppliesPage, ordersPage] = await Promise.all([
          fetchFbsSupplyWorklist(token, authHeaders, params),
          fetchFbsWorklist(token, authHeaders, params),
        ])
        setActiveSupplies(suppliesPage.items)
        setExternalActiveOrders(ordersPage.items.filter((order) => !order.supply_id))
        setOrders([])
        setServerNow(suppliesPage.server_now)
        setLastLoadedAt(new Date().toISOString())
        return
      }
      const page = await fetchFbsWorklist(token, authHeaders, {
        seller_id: sellerId === '__all__' ? null : sellerId,
        status_group: statusGroup,
        wb_warehouse_id: statusGroup === 'new' && wbWarehouseId !== '__all__' ? wbWarehouseId : null,
        limit: statusGroup === 'new' ? NEW_ORDERS_PAGE_LIMIT : 500,
      })
      setOrders(page.items)
      setActiveSupplies([])
      setExternalActiveOrders([])
      setSelectedCache((current) => {
        const next = new Map(current)
        page.items.forEach((order) => next.set(order.id, order))
        return next
      })
      setWarehouseOptions(statusGroup === 'new' ? page.warehouse_options ?? [] : [])
      if (
        statusGroup === 'new' &&
        wbWarehouseId !== '__all__' &&
        !(page.warehouse_options ?? []).some((warehouse) => warehouse.id === wbWarehouseId)
      ) {
        setWbWarehouseId('__all__')
      }
      setServerNow(page.server_now)
      setLastLoadedAt(new Date().toISOString())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить заказы FBS.')
    } finally {
      setBusy(false)
      loadingRef.current = false
    }
  }, [token, authHeaders, sellerId, statusGroup, wbWarehouseId])

  useEffect(() => {
    void load()
  }, [load])

  // Задача 9 пула (HANDOFF-POLISH.md): список раньше не обновлялся сам никогда. Поллинг
  // активной вкладки каждые 30 секунд; останавливается, когда вкладка браузера скрыта —
  // обновлять то, что оператор не видит, незачем. loadingRef внутри load() не даёт
  // соседним тикам наслоиться друг на друга.
  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (document.hidden) return
      void load()
    }, 30000)
    const onVisibilityChange = () => {
      if (!document.hidden) void load()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [load])

  useEffect(() => {
    let cancelled = false
    setSellerWarehouseNames({})
    if (statusGroup !== 'new' || sellerId === '__all__') return
    void fetchFbsSellerWarehouses(token, authHeaders, sellerId)
      .then((warehouses) => {
        if (cancelled) return
        setSellerWarehouseNames(Object.fromEntries(
          warehouses
            .filter((warehouse) => warehouse.id != null && warehouse.name?.trim())
            .map((warehouse) => [String(warehouse.id), warehouse.name!.trim()]),
        ))
      })
      .catch(() => {
        // WB names are optional for loading the worklist; IDs remain usable as fallback.
      })
    return () => { cancelled = true }
  }, [token, authHeaders, sellerId, statusGroup])

  // Ручной поход в Wildberries: тянем новые заказы и подтягиваем их статусы.
  // Автоопрос делает то же самое раз в минуту, но оператору нужна кнопка на случай,
  // когда ждать нельзя или фоновый воркер отвалился.
  const syncTargets = useMemo(
    () => (sellerId === '__all__' ? sellers.map((seller) => seller.id) : [sellerId]),
    [sellerId, sellers],
  )

  const syncWithWb = useCallback(async () => {
    if (syncTargets.length === 0) {
      setSyncError('Нет ни одного селлера, по которому можно запросить заказы.')
      return
    }
    setSyncing(true)
    setError(null)
    setSyncNote(null)
    setSyncError(null)
    setSyncWarning(null)
    let received = 0
    let created = 0
    let statusesUpdated = 0
    let skippedUnmappedWarehouse = 0
    let skippedMismatchOrders = 0
    const skippedSupplyIds: string[] = []
    const failures: string[] = []
    for (const targetSellerId of syncTargets) {
      const sellerName = sellers.find((seller) => seller.id === targetSellerId)?.name ?? 'селлер'
      try {
        const outcome = await runFbsOrdersSync(token, authHeaders, targetSellerId)
        received += outcome.ordersReceived
        created += outcome.ordersCreated
        skippedUnmappedWarehouse += outcome.supplyLinkSkippedUnmappedWarehouse
        skippedMismatchOrders += outcome.supplyLinkSkippedWarehouseMismatchOrders
        skippedSupplyIds.push(...outcome.supplyLinkSkippedUnmappedWarehouseSupplyIds)
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
    // КРИТ-2 (HANDOFF-POLISH.md, пул 1 п.3): раньше ошибка WB уходила только в лог,
    // экран не менялся ни на пиксель. Теперь у ошибки sync своя плашка — такая же
    // заметная, как зелёная плашка успеха ниже.
    if (failures.length > 0) {
      setSyncError(failures.join(' · '))
    }
    if (failures.length < syncTargets.length) {
      setSyncNote(
        `WB отдал заказов: ${received}, из них новых: ${created}. Обновлено статусов: ${statusesUpdated}.`,
      )
      // Предупреждение о пропущенных поставках из-за непривязанных складов.
      if (skippedUnmappedWarehouse > 0) {
        const displayedSupplyIds = skippedSupplyIds.slice(0, 5)
        const displayedIds = displayedSupplyIds.join(', ')
        const remaining = skippedSupplyIds.length - displayedSupplyIds.length
        const supplyWord = plural(skippedUnmappedWarehouse, ['поставка', 'поставки', 'поставок'])
        let supplyWarning = `Из кабинета WB не подхватилось ${skippedUnmappedWarehouse} ${supplyWord} — у их складов нет привязки к WMS. Номера: ${displayedIds}`
        if (remaining > 0) {
          supplyWarning += `, и ещё ${remaining}.`
        } else {
          supplyWarning += '.'
        }
        supplyWarning += ' Привязка делается на вкладке «Остатки WB».'
        if (skippedMismatchOrders > 0) {
          const orderWord = plural(skippedMismatchOrders, ['заказ', 'заказа', 'заказов'])
          supplyWarning += ` Кроме того, ${skippedMismatchOrders} ${orderWord} не привязались к своим поставкам из-за несовпадения склада.`
        }
        setSyncWarning(supplyWarning)
      }
    }
    await load()
  }, [syncTargets, sellers, token, authHeaders, load])

  const selectedOrders = useMemo(
    () => [...selected].map((id) => selectedCache.get(id)).filter((order): order is FbsWorklistOrder => Boolean(order)),
    [selected, selectedCache],
  )
  const selectedOrderIds = useMemo(() => [...selected], [selected])
  const compatibleExistingSupplies = useMemo(() => {
    if (selectedOrders.length === 0) return []
    const first = selectedOrders[0]
    const sameSelection = selectedOrders.every(
      (order) =>
        order.seller.id === first.seller.id &&
        Number(order.wb_warehouse.id) === Number(first.wb_warehouse.id),
    )
    if (!sameSelection) return []
    return visibleSupplies.filter(
      (supply) =>
        supply.can_add_orders &&
        supply.seller.id === first.seller.id &&
        Number(supply.wb_warehouse.id) === Number(first.wb_warehouse.id),
    )
  }, [visibleSupplies, selectedOrders])
  const selectionBlockers = useMemo(
    () => selectedOrders.flatMap((order) => order.selection_blockers.map((blocker) => ({ order, blocker }))),
    [selectedOrders],
  )
  const selectableIds = useMemo(
    () => visibleOrders.filter((order) => order.selection_blockers.length === 0).map((order) => order.id),
    [visibleOrders],
  )
  const searchTerm = normalizeSearch(activeSearch)
  const matchingOrders = useMemo(
    () => (searchTerm ? visibleOrders.filter((order) => orderSearchText(order).includes(searchTerm)) : []),
    [visibleOrders, searchTerm],
  )
  const matchingIds = useMemo(
    () => new Set(matchingOrders.map((order) => order.id)),
    [matchingOrders],
  )
  const exportRows = selected.size > 0 ? selectedOrders : searchTerm ? matchingOrders : visibleOrders

  const addSelectedToExistingSupply = async () => {
    if (!addExistingSupplyId || selectedOrderIds.length === 0) return
    setAddingExisting(true)
    setError(null)
    try {
      const workspace = await addFbsOrdersToSupply(token, authHeaders, addExistingSupplyId, {
        order_ids: selectedOrderIds,
        idempotency_key: createFbsIdempotencyKey(),
      })
      setAddExistingOpen(false)
      setAddExistingSupplyId('')
      setSelected(new Set())
      openWorkspace(workspace.supply.id, workspace)
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось добавить заказы в поставку.')
    } finally {
      setAddingExisting(false)
    }
  }

  const openAddExistingDialog = async () => {
    setError(null)
    try {
      const page = await fetchFbsSupplyWorklist(token, authHeaders, {
        seller_id: sellerId === '__all__' ? selectedOrders[0]?.seller.id ?? null : sellerId,
        status_group: 'active',
        limit: 500,
      })
      setActiveSupplies(page.items)
      setAddExistingSupplyId('')
      setAddExistingOpen(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить поставки в работе.')
    }
  }

  useEffect(() => {
    if (!searchTerm || matchingOrders.length === 0) return
    rowRefs.current[matchingOrders[0].id]?.scrollIntoView({ block: 'center' })
  }, [matchingOrders, searchTerm])

  useEffect(() => {
    if (!searchTerm || statusGroup !== 'new' || orders.length === 0) {
      if (notice === SEARCH_NO_MATCH_NOTICE) setNotice(null)
      return
    }
    if (matchingOrders.length === 0) {
      if (notice !== SEARCH_NO_MATCH_NOTICE) setNotice(SEARCH_NO_MATCH_NOTICE)
      return
    }
    if (notice === SEARCH_NO_MATCH_NOTICE) setNotice(null)
  }, [matchingOrders.length, notice, orders.length, searchTerm, statusGroup])

  const toggle = useCallback((order: FbsWorklistOrder) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(order.id)) next.delete(order.id)
      else next.add(order.id)
      return next
    })
    setSelectedCache((current) => {
      const next = new Map(current)
      next.set(order.id, order)
      return next
    })
  }, [])

  const toggleVisibleSelectable = (checked: boolean) => {
    setSelected((current) => {
      const next = new Set(current)
      selectableIds.forEach((id) => {
        if (checked) next.add(id)
        else next.delete(id)
      })
      return next
    })
  }

  const downloadExcel = () => {
    if (exportRows.length === 0) {
      setNotice('Выгружать нечего: по текущему набору нет заказов.')
      return
    }
    downloadOrdersExcel(exportRows)
    setNotice(`Выгружено заказов: ${exportRows.length}.`)
  }

  const openWorkspace = useCallback((supplyId: string, seed?: FbsWorkspace) => {
    setWorkspaceId(supplyId)
    setWorkspaceSeed(seed ?? null)
    setWorkspaceOpen(true)
    setError(null)
  }, [])

  const hasNewSelection = statusGroup === 'new' && selected.size > 0

  useEffect(() => {
    // Панель появляется/пропадает и меняет высоту (строка блокера длиннее, чем
    // подсказка по умолчанию) — ResizeObserver ловит оба случая без завязки на
    // конкретные брейкпоинты. Когда выбор снят, панель размонтируется и отступ
    // под таблицей сразу убираем.
    if (!hasNewSelection) {
      setSelectionBarHeight(0)
      return
    }
    const node = selectionBarRef.current
    if (!node) return
    const measure = () => setSelectionBarHeight(node.getBoundingClientRect().height)
    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasNewSelection, selectionBlockers.length])

  useEffect(() => {
    const supplyId = new URLSearchParams(location.search).get('supply_id')
    if (!supplyId || openedSupplyFromQuery.current === supplyId) return
    openedSupplyFromQuery.current = supplyId
    setStatusGroup('active')
    openWorkspace(supplyId)
  }, [location.search])

  return (
    <Box
      data-testid="fbs-orders-screen"
      sx={{
        pb: hasNewSelection ? 24 : 3,
        minWidth: 0,
        width: '100%',
        maxWidth: 'calc(100vw - 308px)',
        boxSizing: 'border-box',
        overflowX: 'hidden',
      }}
    >
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        sx={{ justifyContent: 'space-between', gap: 2, mb: 1.5 }}
      >
        <Box>
          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
            <Inventory2OutlinedIcon color="primary" />
            <Typography variant="h5">Заказы FBS</Typography>
          </Stack>
        </Box>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
          {formatFreshness(lastLoadedAt) ? (
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid="fbs-orders-freshness"
              data-task-id="REC-11"
            >
              {formatFreshness(lastLoadedAt)}
            </Typography>
          ) : null}
          <Button
            variant="text"
            size="small"
            startIcon={<RefreshOutlinedIcon />}
            onClick={() => void load()}
            disabled={busy || syncing}
          >
            Обновить
          </Button>
          {isAdmin ? (
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
          ) : null}
        </Stack>
      </Stack>

      <FfFbsSectionNav showStockSync={isAdmin} />
      <WarehouseContextSwitch
        options={wmsWarehouseOptions}
        value={wmsWarehouseId}
        onChange={setWmsWarehouseId}
        loading={busy && wmsWarehouseOptions.length === 0}
        testId="fbs-wms-warehouse-context"
      />

      <Paper variant="outlined" sx={{ overflow: 'hidden', mt: 2 }}>
        <Tabs
          value={statusGroup}
          onChange={(_, value) => {
            setStatusGroup(value)
            setWbWarehouseId('__all__')
          }}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ px: 1.5, borderBottom: 1, borderColor: 'divider' }}
        >
          {TABS.map((tab) => (
            <Tab
              key={tab.key}
              value={tab.key}
              label={tab.label}
              data-task-id={
                tab.key === 'cancelled' ? 'FBS-06' : tab.key === 'expired' ? 'FBS-03' : undefined
              }
            />
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
              <InputLabel id="fbs-worklist-warehouse-label">Склад селлера / WB</InputLabel>
              <Select
                labelId="fbs-worklist-warehouse-label"
                label="Склад селлера / WB"
                value={wbWarehouseId}
                onChange={(event) => {
                  setWbWarehouseId(String(event.target.value))
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
                    {warehouseOptionLabel(warehouse, sellerWarehouseNames)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : null}
          <TextField
            fullWidth
            label="Поиск: заказ, товар, категория, артикул, ШК, SKU, цвет, размер"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setActiveSearch(event.target.value.trim())
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') setActiveSearch(search.trim())
            }}
            data-testid="fbs-worklist-search"
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchOutlinedIcon fontSize="small" />
                  </InputAdornment>
                ),
              },
            }}
          />
          {statusGroup === 'new' ? (
            <Button
              variant="outlined"
              startIcon={<DownloadOutlinedIcon />}
              onClick={downloadExcel}
              disabled={busy}
              data-testid="fbs-orders-download-excel"
              sx={{ minWidth: 170 }}
            >
              Скачать Excel
            </Button>
          ) : null}
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

      {syncError ? (
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          onClose={() => setSyncError(null)}
          data-testid="fbs-orders-sync-error"
          data-task-id="FBS-07"
        >
          {syncError}
        </Alert>
      ) : null}

      {syncWarning ? (
        <Alert
          severity="warning"
          sx={{ mt: 2 }}
          onClose={() => setSyncWarning(null)}
          data-testid="fbs-orders-sync-warning"
          data-task-id="FBS-07"
        >
          {syncWarning}
        </Alert>
      ) : null}

      {notice ? (
        <Alert
          severity={notice.startsWith('Выгружено') ? 'success' : 'info'}
          sx={{ mt: 2 }}
          onClose={() => setNotice(null)}
          data-testid="fbs-orders-notice"
        >
          {notice}
        </Alert>
      ) : null}

      {isFbsSupplyGroup(statusGroup) && visibleExternalOrders.length > 0 ? (
        <Alert severity="info" sx={{ mt: 2 }} data-testid="fbs-06-external-supply-explanation">
          {visibleExternalOrders.length} {ordersWord(visibleExternalOrders.length)} уже видны в WB, но локальной карточки поставки в WMS нет. Они не открываются как поставка здесь.
        </Alert>
      ) : null}

      {isFbsSupplyGroup(statusGroup) ? (
        <TableContainer component={Paper} variant="outlined" sx={{ mt: 2, maxHeight: 'calc(100vh - 330px)' }}>
          <Table stickyHeader size="small" data-testid="fbs-18-supplies-table">
            <TableHead>
              <TableRow>
                <TableCell sx={{ minWidth: 210 }}>Номер / название поставки</TableCell>
                <TableCell sx={{ minWidth: 130 }}>Селлер</TableCell>
                <TableCell sx={{ minWidth: 190 }}>Склад</TableCell>
                <TableCell sx={{ minWidth: 95 }}>Заказы / единицы</TableCell>
                <TableCell sx={{ minWidth: 64 }}>Короба</TableCell>
                <TableCell sx={{ minWidth: 115 }}>Статус</TableCell>
                <TableCell sx={{ minWidth: 135 }}>Дата отгрузки</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleSupplies.map((supply) => (
                <TableRow
                  key={supply.id}
                  hover
                  onClick={() => openWorkspace(supply.id)}
                  sx={{ cursor: 'pointer', '& > td': { py: 1 } }}
                  data-testid={`fbs-18-supply-${supply.id}`}
                >
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 750 }}>
                      {supply.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      WB №{supply.wb_supply_id}
                    </Typography>
                  </TableCell>
                  <TableCell>{supply.seller.name}</TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 650 }}>
                      {supply.wb_warehouse.name || `WB ${supply.wb_warehouse.id}`}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      WMS: {supply.wms_warehouse.name}
                    </Typography>
                  </TableCell>
                  <TableCell>{supply.orders_count} / {supply.units_count}</TableCell>
                  <TableCell>{supply.boxes_count}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      variant="outlined"
                      color={supplyStatusColor(supply.status)}
                      label={supplyStatusLabel(supply.status)}
                      data-testid="fbs-18-supply-status"
                    />
                  </TableCell>
                  <TableCell>{formatNullableDateTime(supply.planned_shipment_date)}</TableCell>
                </TableRow>
              ))}
              {!busy && visibleSupplies.length === 0 && isFbsSupplyGroup(statusGroup) ? (
                <TableRow>
                  <TableCell colSpan={7}>
                    <Box sx={{ py: 8, textAlign: 'center' }}>
                      <Inventory2OutlinedIcon sx={{ fontSize: 42, color: 'text.disabled' }} />
                      <Typography variant="subtitle1" sx={{ mt: 1 }}>
                        {wmsWarehouseId ? `На складе «${wmsWarehouseOptions.find((option) => option.id === wmsWarehouseId)?.name ?? ''}» пока нет поставок.` : SUPPLY_EMPTY_STATE[statusGroup].title}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {SUPPLY_EMPTY_STATE[statusGroup].hint}
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
              <Typography variant="body2">Обновляем поставки…</Typography>
            </Stack>
          ) : null}
        </TableContainer>
      ) : (
      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{
          mt: 2,
          // Резервируем под fbs-selection-bar её реальную высоту + отступ панели от
          // низа вьюпорта (18px) + небольшой воздух, чтобы нижняя строка таблицы
          // никогда не пряталась под панелью, а не «подрезалась» вплотную к ней.
          maxHeight: hasNewSelection
            ? `calc(100vh - 330px - ${selectionBarHeight + 30}px)`
            : 'calc(100vh - 330px)',
          transition: 'max-height 0.15s ease',
        }}
      >
        <Table stickyHeader size="small" data-testid="fbs-worklist-table">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                {statusGroup === 'new' ? (
                  <Checkbox
                    checked={selectableIds.length > 0 && selectableIds.every((id) => selected.has(id))}
                    indeterminate={selected.size > 0 && !selectableIds.every((id) => selected.has(id))}
                    onChange={(_, checked) => toggleVisibleSelectable(checked)}
                  />
                ) : null}
              </TableCell>
              {statusGroup === 'new' ? (
                <>
                  <TableCell sx={{ minWidth: 210 }}>Товар</TableCell>
                  <TableCell sx={{ minWidth: 210 }}>Заказ и сканирование</TableCell>
                  <TableCell sx={{ minWidth: 135 }}>Селлер</TableCell>
                  <TableCell sx={{ minWidth: 180 }}>Склад селлера / WB</TableCell>
                  <TableCell sx={{ minWidth: 140 }}>Создан WB / в сборке</TableCell>
                </>
              ) : (
                <>
                  <TableCell sx={{ minWidth: 270 }}>Товар</TableCell>
                  <TableCell sx={{ minWidth: 125 }}>Селлер</TableCell>
                  <TableCell sx={{ minWidth: 150 }}>Склад селлера / WB</TableCell>
                  <TableCell sx={{ minWidth: 150 }}>Создан WB / в сборке</TableCell>
                  <TableCell sx={{ minWidth: 130 }}>Статус</TableCell>
                </>
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleOrders.map((order) => {
              if (statusGroup === 'new') {
                return (
                  <NewOrderRow
                    key={order.id}
                    order={order}
                    selected={selected.has(order.id)}
                    highlighted={Boolean(searchTerm && matchingIds.has(order.id))}
                    serverNow={serverNow}
                    registerRow={registerRow}
                    onToggle={toggle}
                    onOpenWorkspace={openWorkspace}
                    onGoToStockSync={goToStockSync}
                  />
                )
              }

              const localSupplyMissing = !order.supply_id
              const metaFlag = metadataProblem(order)
              const row = (
                <TableRow
                  key={order.id}
                  ref={(node) => registerRow(order.id, node)}
                  hover={!localSupplyMissing}
                  selected={selected.has(order.id)}
                  sx={{
                    verticalAlign: 'top',
                    cursor: order.supply_id ? 'pointer' : 'default',
                    '& > td': { py: 0.9 },
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
                  <TableCell padding="checkbox" />
                    <>
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
                          </Box>
                        </Stack>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{order.seller.name ?? '—'}</Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 650 }}>
                          {order.wb_warehouse.name || `WB ${order.wb_warehouse.id}`}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          WMS: {order.wms_warehouse.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{formatDateTime(order.created_at_wb)}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          В сборке: {elapsedSince(order.created_at_wb, serverNow)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {/* GLOBAL-02: одно главное состояние на строку. На «Просрочены»
                            статус всегда «Новый» (см. STATUS_GROUP_MAP на бэкенде) — сам
                            факт просрочки уже виден по вкладке, повторять его чипом не
                            нужно, поэтому базовый статус-чип там не рисуем вовсе. Если
                            маркировка отклонена/не хватает — это и есть главное состояние,
                            оно важнее декоративного статуса. Всё остальное — обычным
                            текстом ниже, без цвета. */}
                        {statusGroup === 'expired' && metaFlag ? (
                          <Chip
                            size="small"
                            color={metaFlag.color}
                            label={metaFlag.label}
                            data-testid={`fbs-order-${order.id}-marking-issue`}
                          />
                        ) : statusGroup !== 'expired' ? (
                          // «Отменённые»: заказ уже закрыт, состояние маркировки для решения
                          // не нужно — главное здесь то, чем закончился заказ (Отменён/Дефект).
                          <FbsStatusChip status={order.status} />
                        ) : null}
                        {localSupplyMissing ? (
                          <Tooltip title={EXTERNAL_WB_SUPPLY_HINT}>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ display: 'block', mt: 0.75 }}
                              data-testid={`fbs-order-${order.id}-external-supply`}
                            >
                              Поставка создана в WB, недоступна в WMS
                            </Typography>
                          </Tooltip>
                        ) : null}
                      </TableCell>
                    </>
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
            {!busy && visibleOrders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Box sx={{ py: 8, textAlign: 'center' }}>
                    <Inventory2OutlinedIcon sx={{ fontSize: 42, color: 'text.disabled' }} />
                    <Typography variant="subtitle1" sx={{ mt: 1 }}>
                      {wmsWarehouseId ? `На складе «${wmsWarehouseOptions.find((option) => option.id === wmsWarehouseId)?.name ?? ''}» пока нет заказов.` : 'Заказов в этой группе нет'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {wmsWarehouseId ? 'Выберите другой склад или дождитесь новых заказов.' : 'Измените фильтры или обновите синхронизацию с WB.'}
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
      )}

      {statusGroup === 'new' && selected.size ? (
        <Paper
          ref={selectionBarRef}
          elevation={8}
          sx={{
            position: 'fixed',
            left: { xs: 12, md: 308 },
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
            {/* minWidth:0 + noWrap — рядом четыре кнопки почти впритык по ширине panelю
                (952px на 1280px экране), без этого текстовый блок ужимается флексом до
                ширины одного слова и подпись переносится в 6-8 строк — панель раздувается
                до 280px+ и перекрывает уже не только соседнюю строку, а половину таблицы.
                Полный текст остаётся доступен по hover через Tooltip. */}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="subtitle2" noWrap>
                Выбрано заказов: {selected.size}
              </Typography>
              <Tooltip
                title={
                  selectionBlockers.length
                    ? selectionBlockers[0].blocker.message
                    : 'Следующий шаг — серверная проверка селлера, складов и состава.'
                }
              >
                <Typography
                  variant="caption"
                  color={selectionBlockers.length ? 'error.main' : 'text.secondary'}
                  noWrap
                  sx={{ display: 'block' }}
                >
                  {selectionBlockers.length
                    ? selectionBlockers[0].blocker.message
                    : 'Следующий шаг — серверная проверка селлера, складов и состава.'}
                </Typography>
              </Tooltip>
            </Box>
            <Button onClick={() => setSelectedOpen(true)} data-testid="fbs-selected-open">
              Показать выбранные
            </Button>
            <Button onClick={() => setSelected(new Set())}>Снять выбор</Button>
            <Button
              variant="outlined"
              size="large"
              disabled={selectionBlockers.length > 0 || selectedOrders.length !== selected.size}
              onClick={() => void openAddExistingDialog()}
              data-testid="fbs-05-add-existing-open"
            >
              Добавить в существующую поставку
            </Button>
            <Button
              variant="contained"
              size="large"
              disabled={selectionBlockers.length > 0 || selectedOrders.length !== selected.size}
              onClick={() => setCreateOpen(true)}
            >
              Сформировать поставку
            </Button>
          </Stack>
        </Paper>
      ) : null}

      <Dialog open={selectedOpen} onClose={() => setSelectedOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Выбранные FBS-заказы</DialogTitle>
        <DialogContent dividers>
          {selectedOrders.length === 0 ? (
            <Typography color="text.secondary">Выбранных заказов нет.</Typography>
          ) : (
            <Stack spacing={1.25} data-testid="fbs-selected-list">
              {selectedOrders.map((order) => (
                <Paper key={order.id} variant="outlined" sx={{ p: 1.25 }}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { sm: 'center' } }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        WB №{order.wb_order_id} · {order.product.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {order.seller.name} · {order.wb_warehouse.name || `WB ${order.wb_warehouse.id}`} · {order.product.barcode ?? 'ШК нет'}
                      </Typography>
                      {order.selection_blockers.length ? (
                        <Stack sx={{ mt: 0.5 }} spacing={0.25}>
                          {order.selection_blockers.map((blocker) => (
                            <BlockerLine
                              key={blocker.code}
                              blocker={blocker}
                              onGoToStockSync={() => navigate('/app/ff/fbs/stock-sync')}
                            />
                          ))}
                        </Stack>
                      ) : null}
                    </Box>
                    <Button
                      size="small"
                      onClick={() => setSelected((current) => {
                        const next = new Set(current)
                        next.delete(order.id)
                        return next
                      })}
                    >
                      Убрать
                    </Button>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelected(new Set())}>Снять всё</Button>
          <Button variant="contained" onClick={() => setSelectedOpen(false)}>Закрыть</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={addExistingOpen} onClose={addingExisting ? undefined : () => setAddExistingOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Добавить в существующую поставку</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Выбрано {selectedOrders.length} {ordersWord(selectedOrders.length)}. WMS покажет только поставки того же селлера, WB-склада и допустимого статуса.
            </Typography>
            {compatibleExistingSupplies.length === 0 ? (
              <Alert severity="info" data-testid="fbs-05-no-compatible-supply">
                Совместимых поставок в работе нет. Создайте новую поставку или выберите заказы другого селлера/склада.
              </Alert>
            ) : (
              <FormControl fullWidth>
                <InputLabel id="fbs-05-existing-supply-label">Поставка</InputLabel>
                <Select
                  labelId="fbs-05-existing-supply-label"
                  label="Поставка"
                  value={addExistingSupplyId}
                  onChange={(event) => setAddExistingSupplyId(String(event.target.value))}
                  data-testid="fbs-05-existing-supply-select"
                >
                  {compatibleExistingSupplies.map((supply) => (
                    <MenuItem key={supply.id} value={supply.id}>
                      {supply.name} · {supply.seller.name} · {supply.wb_warehouse.name || `WB ${supply.wb_warehouse.id}`} · {supplyStatusLabel(supply.status)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddExistingOpen(false)} disabled={addingExisting}>
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={!addExistingSupplyId || addingExisting}
            onClick={() => void addSelectedToExistingSupply()}
            data-testid="fbs-05-add-existing-submit"
          >
            Добавить заказы
          </Button>
        </DialogActions>
      </Dialog>

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
