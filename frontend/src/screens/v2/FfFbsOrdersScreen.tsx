import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiUrl } from '../../api'
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
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined'
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined'
import { DeadlinePill, FbsStatusChip } from '../../components/fbs/FbsChips'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { FbsSupplyCreateDialog } from './FbsSupplyCreateDialog'
import { FbsPrintPreviewDialog } from './FbsPrintPreviewDialog'
import { FfFbsSectionNav } from './FfFbsSectionNav'
import {
  FbsMetricPanel,
  type MetricPreset,
} from '../ff/products-fbs/FbsMetricPanel'
import type { MoscowDateRangeValue } from '../../ui-kit'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import {
  buildFbsSyncTargets,
  fbsOrdersSyncErrorMessage,
  mixedMarketplaceSelectionMessage,
  orderStatusForChip,
  ordersWord,
  supplyQrExpectedForStatus,
} from './fbsUx'
import { plural } from '../../utils/plural'
import {
  fetchFbsSellerWarehouses,
  fetchFbsSupplyWorklist,
  fetchFbsWorklist,
  fetchFbsCargoPlaces,
  addFbsOrdersToSupply,
  cancelFbsOrder,
  confirmFbsPrintApplied,
  createFbsIdempotencyKey,
  retryFbsSupplyQr,
  runFbsOrdersSync,
  syncFbsOrderStatuses,
  syncFbsSupplyTracking,
  type FbsPrintAsset,
  type FbsPrintBatch,
  type FbsSupplyWorklistItem,
  type FbsWorklistOrder,
  type FbsWorklistWarehouseOption,
  type FbsWorkspace,
} from './fbsApi'

type SellerRow = { id: string; name: string }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  sellers: SellerRow[]
  isAdmin?: boolean; addressStorageEnabled?: boolean
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

const SEARCH_NO_MATCH_NOTICE = 'Совпадений не найдено, список не изменён.'

function marketplaceLabel(marketplace: 'wb' | 'ozon'): string {
  return marketplace === 'ozon' ? 'Ozon' : 'Wildberries'
}

function orderNumberLabel(order: FbsWorklistOrder): string {
  // В строке заказа маркетплейс называется коротко — «WB №123», как было всегда.
  // Полное «Wildberries» остаётся в поясняющих текстах, где место есть.
  const short = order.marketplace === 'ozon' ? 'Ozon' : 'WB'
  return `${short} №${order.external_order_id ?? order.wb_order_id}`
}

function externalSupplyHint(order: FbsWorklistOrder): string {
  const marketplace = marketplaceLabel(order.marketplace)
  return `Поставку создали в кабинете ${marketplace}, а в WMS она не привязана. Открыть её здесь нельзя.`
}

// WMS-358: маршрут сдачи Ozon — это метод доставки. Отгрузка создаётся по нему
// (`/v1/carriage/create` принимает `delivery_method_id`), значит заказы одного
// метода уезжают одной отгрузкой, разных — разными: тот же смысл, что у
// вайлдберрисовского маршрута. Название приходит в самом отправлении, справочника
// методов у Ozon нет. У WB маршрут прежний — ПВЗ или склад/СЦ.
function deliveryRouteLabel(order: FbsWorklistOrder): string {
  return order.delivery_route?.trim() || (order.can_pvz ? 'ПВЗ' : 'Склад / СЦ')
}

function DeliveryRouteChip({ order }: { order: FbsWorklistOrder }) {
  const label = deliveryRouteLabel(order)
  return (
    <Tooltip title={label}>
      <Chip
        size="small"
        variant="outlined"
        label={label}
        sx={{ maxWidth: 190, '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis' } }}
        data-testid={`fbs-order-${order.id}-delivery-route`}
      />
    </Tooltip>
  )
}

function MissingText({ children }: { children: string }) {
  return (
    <Typography variant="caption" color="error.main" sx={{ fontWeight: 650 }}>
      {children}
    </Typography>
  )
}

// BL-4 (16.08, FBS-02): блокер "склад WB не привязан" — не просто упрёк, а понятная
// подсказка с действием. Настройка остатка и сопоставление складов живут в каталоге.
function BlockerLine({
  blocker,
  onGoToCatalog,
}: {
  blocker: { code: string; message: string }
  onGoToCatalog: () => void
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
          onGoToCatalog()
        }}
        data-testid="fbs-warehouse-unmapped-link"
        data-task-id="FBS-02"
      >
        Склад WB не привязан — настроить в каталоге
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

/** Коды, которые показываем как предупреждение, но выбор заказа не запрещают.
 *  «Не опубликован» снят с блокировки 01.09.2026: заказ уже приехал, срок сборки
 *  идёт, публикация остатка на WB к сборке отношения не имеет. */
const NON_BLOCKING_SELECTION_CODES = new Set(['not_published'])

function blockingSelectionBlockers(blockers: Array<{ code: string; message: string }>) {
  return blockers.filter((blocker) => !NON_BLOCKING_SELECTION_CODES.has(blocker.code))
}

type NewOrderRowProps = {
  order: FbsWorklistOrder
  selected: boolean
  highlighted: boolean
  serverNow: string | null
  registerRow: (id: string, node: HTMLTableRowElement | null) => void
  onToggle: (order: FbsWorklistOrder) => void
  onOpenWorkspace: (supplyId: string) => void
  onGoToCatalog: (productId: string | null) => void
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
  onGoToCatalog,
}: NewOrderRowProps) {
  const blocked = blockingSelectionBlockers(order.selection_blockers).length > 0
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
      <TableCell sx={{ minWidth: 300 }}>
        <Stack direction="row" spacing={1.25}>
          <LazyProductPhotoThumb
            src={order.product.image_url}
            alt={order.product.name}
            size={52}
            previewSize={280}
            testId={`fbs-product-photo-${order.id}`}
          />
          <Box sx={{ minWidth: 220 }}>
            <Typography variant="subtitle2" sx={{ lineHeight: 1.25, fontWeight: 700 }}>
              {order.product.id ? order.product.name : 'Товар не сопоставлен'}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
              {orderNumberLabel(order)}
            </Typography>
            {blocked ? (
              <Stack sx={{ mt: 0.75 }} spacing={0.25}>
                {order.selection_blockers.map((blocker) => (
                  <BlockerLine
                    key={blocker.code}
                    blocker={blocker}
                    onGoToCatalog={() => onGoToCatalog(order.product.id)}
                  />
                ))}
              </Stack>
            ) : null}
          </Box>
        </Stack>
      </TableCell>
      <TableCell sx={{ minWidth: 170 }}>
        <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
          {order.product.seller_article ?? '—'}
        </Typography>
        {order.product.wb_article ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', whiteSpace: 'nowrap' }}>
            WB {order.product.wb_article}
          </Typography>
        ) : null}
      </TableCell>
      <TableCell sx={{ minWidth: 170 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
          {order.product.sku ?? '—'}
        </Typography>
      </TableCell>
      <TableCell sx={{ minWidth: 150 }}>
        <Typography variant="body2" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', whiteSpace: 'nowrap' }}>
          {order.product.barcode ?? '—'}
        </Typography>
      </TableCell>
      <TableCell sx={{ minWidth: 80 }}>
        <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
          {order.product.size ?? '—'}
        </Typography>
      </TableCell>
      <TableCell>
        <Tooltip title={order.seller.name ?? '—'}>
          <Typography variant="body2" noWrap sx={{ maxWidth: 125 }}>{order.seller.name ?? '—'}</Typography>
        </Tooltip>
      </TableCell>
      <TableCell>
        <DeliveryRouteChip order={order} />
        {order.buyer_type === 'legal' ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>Юридическое лицо</Typography> : null}
      </TableCell>
      <TableCell>
        <DeadlinePill
          deadlineAt={order.deadline_at}
          serverNow={serverNow}
          cancelled={order.status === 'cancelled'}
        />
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

export function FfFbsOrdersScreen({ token, authHeaders, sellers, isAdmin = false, addressStorageEnabled = true }: Props) {
  // Блок среднего времени сборки над таблицей. Период и продавец свои: сводка
  // отвечает на вопрос «как мы работаем», а фильтры таблицы — «где вот этот
  // заказ», и связывать их значит ломать то и другое.
  const [metricPreset, setMetricPreset] = useState<MetricPreset>('week')
  const [metricSellerId, setMetricSellerId] = useState('')
  const [metricRange, setMetricRange] = useState<MoscowDateRangeValue>({ start: '', end: '' })
  const [metric, setMetric] = useState<{
    hours: number
    orders: number
    in12: number | null
    in24: number | null
  }>({ hours: 0, orders: 0, in12: null, in24: null })
  const [metricLoading, setMetricLoading] = useState(false)
  // Сводка не смогла посчитаться — это не «ноль часов». Ноль читается как
  // отличный результат, и руководитель принимает решение по несуществующей
  // цифре. Держим отказ отдельно и показываем его вместо чисел.
  const [metricError, setMetricError] = useState(false)

  const location = useLocation()
  const navigate = useNavigate()
  const [statusGroup, setStatusGroup] = useState<(typeof TABS)[number]['key']>('new')
  const [sellerId, setSellerId] = useState('__all__')
  const [marketplace, setMarketplace] = useState<'__all__' | 'wb' | 'ozon'>('__all__')
  const [wbWarehouseId, setWbWarehouseId] = useState('__all__')
  const [search, setSearch] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [orders, setOrders] = useState<FbsWorklistOrder[]>([])
  const [activeSupplies, setActiveSupplies] = useState<FbsSupplyWorklistItem[]>([])
  const [externalActiveOrders, setExternalActiveOrders] = useState<FbsWorklistOrder[]>([])
  const [warehouseOptions, setWarehouseOptions] = useState<FbsWorklistWarehouseOption[]>([])
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
  // WMS-360: отмена заказа Ozon. Обычное подтверждение перед необратимым
  // действием — отменённое отправление Ozon восстановить нельзя.
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [workspaceSeed, setWorkspaceSeed] = useState<FbsWorkspace | null>(null)
  const [printingSupplyId, setPrintingSupplyId] = useState<string | null>(null)
  const [supplyQrBatch, setSupplyQrBatch] = useState<FbsPrintBatch | null>(null)
  const [supplyQrPreviewOpen, setSupplyQrPreviewOpen] = useState(false)
  const [supplyQrWarning, setSupplyQrWarning] = useState<string | null>(null)
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const registerRow = useCallback((id: string, node: HTMLTableRowElement | null) => {
    rowRefs.current[id] = node
  }, [])
  const goToCatalog = useCallback((productId: string | null) => {
    navigate(
      productId
        ? `/app/ff/products?fbs_limit=${encodeURIComponent(productId)}`
        : '/app/ff/products',
    )
  }, [navigate])
  const openedSupplyFromQuery = useRef<string | null>(null)
  const loadingRef = useRef(false)
  // Плавающая панель выбора (fbs-selection-bar) прибита к низу вьюпорта и накрывает
  // собой последние строки таблицы — оператор кликал по чекбоксу второго заказа и
  // попадал в панель (см. tests-e2e/ff-fbs-orders.spec.ts:277). Меряем реальную высоту
  // панели и резервируем под неё место в TableContainer, а не поднимаем z-index/двигаем
  // панель — так нижние строки остаются кликабельными при любой высоте панели.
  const selectionBarRef = useRef<HTMLDivElement | null>(null)
  const [selectionBarHeight, setSelectionBarHeight] = useState(0)

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
          marketplace: marketplace === '__all__' ? null : marketplace,
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
        setWarehouseOptions([])
        setServerNow(suppliesPage.server_now)
        setLastLoadedAt(new Date().toISOString())
        return
      }
      const page = await fetchFbsWorklist(token, authHeaders, {
        seller_id: sellerId === '__all__' ? null : sellerId,
        marketplace: marketplace === '__all__' ? null : marketplace,
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
  }, [token, authHeaders, sellerId, marketplace, statusGroup, wbWarehouseId])

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

  useEffect(() => {
    let cancelled = false
    const now = new Date()
    const to = new Date(now)
    const from = new Date(now)
    if (metricPreset === 'week') from.setDate(from.getDate() - 7)
    else if (metricPreset === 'month') from.setMonth(from.getMonth() - 1)
    const useCustom =
      metricPreset === 'custom' && metricRange.start !== '' && metricRange.end !== ''
    // Оператор выбирает московские даты, а не UTC. Написать к ним «Z» значит
    // сдвинуть период на три часа: начало съедало первые три часа первого дня,
    // а конец прихватывал три часа следующего. Указываем московскую зону явно.
    const fromIso = useCustom ? `${metricRange.start}T00:00:00+03:00` : from.toISOString()
    const toIso = useCustom ? `${metricRange.end}T23:59:59+03:00` : to.toISOString()

    void (async () => {
      setMetricLoading(true)
      setMetricError(false)
      try {
        const query = new URLSearchParams({ from: fromIso, to: toIso })
        if (metricSellerId) query.set('seller_id', metricSellerId)
        const res = await fetch(apiUrl(`/fbs/assembly-time?${query.toString()}`), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) throw new Error('assembly_time_failed')
        const body = (await res.json()) as {
          hours: number
          orders: number
          within_12_hours_percent?: number
          within_24_hours_percent?: number
        }
        if (cancelled) return
        setMetric({
          hours: body.hours,
          orders: body.orders,
          // Пороги сервер отдаёт не всегда: пока их нет — не показываем, а не
          // рисуем нули, которые читаются как «ни один заказ не уложился».
          in12: body.within_12_hours_percent ?? null,
          in24: body.within_24_hours_percent ?? null,
        })
      } catch {
        if (!cancelled) {
          setMetric({ hours: 0, orders: 0, in12: null, in24: null })
          setMetricError(true)
        }
      } finally {
        if (!cancelled) setMetricLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token, authHeaders, metricPreset, metricSellerId, metricRange.start, metricRange.end])

  const syncTargets = useMemo(
    () => buildFbsSyncTargets(sellers.map((seller) => seller.id), sellerId),
    [sellerId, sellers],
  )

  const syncOrders = useCallback(async () => {
    if (syncTargets.length === 0) {
      setSyncError('Нет ни одного селлера, по которому можно запросить заказы.')
      return
    }
    setSyncing(true)
    setError(null)
    setSyncNote(null)
    setSyncError(null)
    setSyncWarning(null)
    const received = { wb: 0, ozon: 0 }
    const created = { wb: 0, ozon: 0 }
    const statusesUpdated = { wb: 0, ozon: 0 }
    const completedMarketplaces = new Set<'wb' | 'ozon'>()
    let skippedUnmappedWarehouse = 0
    let skippedMismatchOrders = 0
    const skippedSupplyIds: string[] = []
    const failures: string[] = []
    for (const target of syncTargets) {
      const sellerName = sellers.find((seller) => seller.id === target.sellerId)?.name ?? 'селлер'
      const targetProvider = marketplaceLabel(target.marketplace)
      try {
        const outcome = await runFbsOrdersSync(token, authHeaders, target.sellerId, target.marketplace)
        if (outcome.skipped) continue
        completedMarketplaces.add(target.marketplace)
        received[target.marketplace] += outcome.ordersReceived
        created[target.marketplace] += outcome.ordersCreated
        skippedUnmappedWarehouse += outcome.supplyLinkSkippedUnmappedWarehouse
        skippedMismatchOrders += outcome.supplyLinkSkippedWarehouseMismatchOrders
        skippedSupplyIds.push(...outcome.supplyLinkSkippedUnmappedWarehouseSupplyIds)
      } catch (cause) {
        failures.push(`${sellerName} · ${targetProvider}: ${fbsOrdersSyncErrorMessage(cause)}`)
        continue
      }
      try {
        statusesUpdated[target.marketplace] += await syncFbsOrderStatuses(
          token,
          authHeaders,
          target.sellerId,
          target.marketplace,
        )
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
    if (completedMarketplaces.size > 0) {
      setSyncNote([...completedMarketplaces].map((provider) => (
        `${marketplaceLabel(provider)}: получено ${received[provider]}, новых ${created[provider]}, обновлено статусов ${statusesUpdated[provider]}`
      )).join(' · '))
      // Предупреждение о пропущенных поставках из-за непривязанных складов.
      if (skippedUnmappedWarehouse > 0) {
        const displayedSupplyIds = skippedSupplyIds.slice(0, 5)
        const displayedIds = displayedSupplyIds.join(', ')
        const remaining = skippedSupplyIds.length - displayedSupplyIds.length
        const supplyWord = plural(skippedUnmappedWarehouse, ['поставка', 'поставки', 'поставок'])
        let supplyWarning = `Из кабинетов маркетплейсов не подхватилось ${skippedUnmappedWarehouse} ${supplyWord} — у их складов нет привязки к WMS. Номера: ${displayedIds}`
        if (remaining > 0) {
          supplyWarning += `, и ещё ${remaining}.`
        } else {
          supplyWarning += '.'
        }
        supplyWarning += ' Привязка делается на вкладке «Остатки».'
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
  const mixedMarketplaceMessage = useMemo(
    () => mixedMarketplaceSelectionMessage(selectedOrders.map((order) => order.marketplace)),
    [selectedOrders],
  )
  const compatibleExistingSupplies = useMemo(() => {
    if (selectedOrders.length === 0) return []
    const first = selectedOrders[0]
    const sameSelection = selectedOrders.every(
      (order) =>
        order.seller.id === first.seller.id &&
        order.marketplace === first.marketplace &&
        Number(order.wb_warehouse.id) === Number(first.wb_warehouse.id),
    )
    if (!sameSelection) return []
    return activeSupplies.filter(
      (supply) =>
        supply.can_add_orders &&
        supply.seller.id === first.seller.id &&
        supply.marketplace === first.marketplace &&
        Number(supply.wb_warehouse.id) === Number(first.wb_warehouse.id),
    )
  }, [activeSupplies, selectedOrders])
  const selectionBlockers = useMemo(
    () => selectedOrders.flatMap((order) =>
      blockingSelectionBlockers(order.selection_blockers).map((blocker) => ({ order, blocker })),
    ),
    [selectedOrders],
  )
  const selectableIds = useMemo(
    () => orders.filter((order) => blockingSelectionBlockers(order.selection_blockers).length === 0).map((order) => order.id),
    [orders],
  )
  const searchTerm = normalizeSearch(activeSearch)
  const matchingOrders = useMemo(
    () => (searchTerm ? orders.filter((order) => orderSearchText(order).includes(searchTerm)) : []),
    [orders, searchTerm],
  )
  const matchingIds = useMemo(
    () => new Set(matchingOrders.map((order) => order.id)),
    [matchingOrders],
  )
  const exportRows = selected.size > 0 ? selectedOrders : searchTerm ? matchingOrders : orders

  // WMS-360: отмена доступна только по заказам Ozon. У Wildberries отмена стоит
  // продавцу штрафа и отдельного разговора с маркетплейсом — своей кнопки на
  // этом экране у неё нет и здесь не появляется.
  const ozonSelection = useMemo(
    () =>
      selectedOrders.length > 0 &&
      selectedOrders.length === selected.size &&
      selectedOrders.every((order) => order.marketplace === 'ozon'),
    [selectedOrders, selected],
  )

  const cancelSelectedOzonOrders = async () => {
    setCancelling(true)
    setError(null)
    setNotice(null)
    // Отмена уходит по одному заказу — ручка `PATCH .../{id}/cancel` работает с
    // одним отправлением. Если Ozon отказал на середине, честно говорим, сколько
    // успело отмениться: молча показать «не получилось» после трёх отменённых
    // заказов — соврать оператору.
    let done = 0
    try {
      for (const order of selectedOrders) {
        await cancelFbsOrder(token, authHeaders, order.id)
        done += 1
      }
      setCancelOpen(false)
      setNotice(`Отменено заказов в Ozon: ${done}.`)
      setSelected(new Set())
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : 'Не удалось отменить заказ в Ozon.'
      setError(done > 0 ? `Отменено заказов: ${done}, дальше остановились. ${reason}` : reason)
    } finally {
      setCancelling(false)
      await load()
    }
  }

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

  const openSupplyQrPrint = useCallback(async (supply: FbsSupplyWorklistItem) => {
    const supplyId = supply.id
    setPrintingSupplyId(supplyId)
    setError(null)
    setNotice(null)
    setSupplyQrWarning(null)
    const failures: string[] = []
    let supplyAsset: FbsPrintAsset | null = null
    let cargoAssets: FbsPrintAsset[] = []
    let cargoPlacesCount = 0
    let currentSupplyStatus = supply.status

    try {
      const refreshed = await syncFbsSupplyTracking(token, authHeaders, supplyId)
      currentSupplyStatus = refreshed.supply.status
    } catch (cause) {
      failures.push(cause instanceof Error ? cause.message : 'Статус поставки не обновлён.')
    }
    const expectsSupplyQr = supplyQrExpectedForStatus(currentSupplyStatus)
    if (expectsSupplyQr) {
      try {
        const refreshed = await retryFbsSupplyQr(token, authHeaders, supplyId)
        supplyAsset = refreshed.supply.barcode_asset
      } catch (cause) {
        failures.push(cause instanceof Error ? cause.message : 'QR поставки не получен.')
      }
    }
    try {
      const cargoPlaces = await fetchFbsCargoPlaces(token, authHeaders, supplyId)
      cargoPlacesCount = cargoPlaces.length
      cargoAssets = cargoPlaces
        .map((place) => place.qr_asset)
        .filter((asset): asset is FbsPrintAsset => Boolean(asset))
    } catch (cause) {
      failures.push(cause instanceof Error ? cause.message : 'QR грузомест не получены.')
    }

    const assets = [...new Map(
      [supplyAsset, ...cargoAssets]
        .filter((asset): asset is FbsPrintAsset => Boolean(asset))
        .map((asset) => [asset.id, asset]),
    ).values()]
    const ready = assets.filter((asset) => asset.status === 'ready' && asset.preview_url).length
    const failed = assets.filter((asset) => asset.status === 'error').length
    const requested = cargoPlacesCount + (expectsSupplyQr ? 1 : 0)
    setSupplyQrBatch({
      requested,
      ready,
      failed,
      missing: Math.max(0, requested - ready - failed),
      assets,
      order_errors: [],
    })
    if (ready > 0) {
      setSupplyQrPreviewOpen(true)
      if (failures.length > 0) {
        setSupplyQrWarning(`Часть QR не получена: ${failures.join(' · ')}`)
      }
    } else {
      setError(failures.join(' · ') || 'WB не вернул готовые QR для этой поставки.')
    }
    setPrintingSupplyId(null)
    await load()
  }, [token, authHeaders, load])

  const confirmSupplyQrApplied = useCallback(async (asset: FbsPrintAsset) => {
    await confirmFbsPrintApplied(
      token,
      authHeaders,
      asset.id,
      createFbsIdempotencyKey(),
    )
    setSupplyQrBatch((current) => current ? {
      ...current,
      assets: current.assets.map((item) => item.id === asset.id
        ? { ...item, applied_at: new Date().toISOString() }
        : item),
    } : current)
  }, [token, authHeaders])

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
              onClick={() => void syncOrders()}
              disabled={syncing || busy}
              data-testid="fbs-orders-sync-wb"
              sx={{ minWidth: 214 }}
            >
              {syncing ? 'Синхронизируем заказы…' : 'Синхронизировать заказы'}
            </Button>
          ) : null}
        </Stack>
      </Stack>

      <FfFbsSectionNav />

      {/* Среднее время сборки крупной цифрой над таблицей — согласованный блок.
          До сих пор он жил только в макете: экран его не показывал. */}
      <FbsMetricPanel
        hours={metric.hours}
        orders={metric.orders}
        in12={metric.in12}
        in24={metric.in24}
        sellers={sellers.map((one) => ({ id: one.id, name: one.name }))}
        sellerId={metricSellerId}
        onSellerChange={setMetricSellerId}
        preset={metricPreset}
        onPresetChange={setMetricPreset}
        range={metricRange}
        onRangeChange={setMetricRange}
        loading={metricLoading}
        failed={metricError}
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
          <FormControl sx={{ minWidth: 170 }}>
            <InputLabel id="fbs-worklist-marketplace-label">Маркетплейс</InputLabel>
            <Select
              labelId="fbs-worklist-marketplace-label"
              label="Маркетплейс"
              value={marketplace}
              onChange={(event) => {
                setMarketplace(event.target.value as '__all__' | 'wb' | 'ozon')
                setWbWarehouseId('__all__')
              }}
              data-testid="fbs-worklist-marketplace"
            >
              <MenuItem value="__all__">Все</MenuItem>
              <MenuItem value="wb">Wildberries</MenuItem>
              <MenuItem value="ozon">Ozon</MenuItem>
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

      {isFbsSupplyGroup(statusGroup) && externalActiveOrders.length > 0 ? (
        <Alert severity="info" sx={{ mt: 2 }} data-testid="fbs-06-external-supply-explanation">
          {externalActiveOrders.length} {ordersWord(externalActiveOrders.length)} уже видны в WB, но локальной карточки поставки в WMS нет. Они не открываются как поставка здесь.
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
                <TableCell align="right" sx={{ minWidth: 105 }}>Печать</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {activeSupplies.map((supply) => (
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
                  <TableCell align="right" onClick={(event) => event.stopPropagation()}>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={printingSupplyId === supply.id
                        ? <CircularProgress size={14} />
                        : <PrintOutlinedIcon />}
                      disabled={Boolean(printingSupplyId)}
                      onClick={() => void openSupplyQrPrint(supply)}
                      data-testid={`fbs-supply-qr-print-${supply.id}`}
                    >
                      QR
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!busy && activeSupplies.length === 0 && isFbsSupplyGroup(statusGroup) ? (
                <TableRow>
                  <TableCell colSpan={8}>
                    <Box sx={{ py: 8, textAlign: 'center' }}>
                      <Inventory2OutlinedIcon sx={{ fontSize: 42, color: 'text.disabled' }} />
                      <Typography variant="subtitle1" sx={{ mt: 1 }}>
                        {SUPPLY_EMPTY_STATE[statusGroup].title}
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
                  <TableCell sx={{ minWidth: 300 }}>Товар</TableCell>
                  <TableCell sx={{ minWidth: 170 }}>Артикул продавца</TableCell>
                  <TableCell sx={{ minWidth: 170 }}>SKU</TableCell>
                  <TableCell sx={{ minWidth: 150 }}>ШК</TableCell>
                  <TableCell sx={{ minWidth: 80 }}>Размер</TableCell>
                  <TableCell sx={{ minWidth: 135 }}>Селлер</TableCell>
                  <TableCell sx={{ minWidth: 125 }}>Маршрут сдачи</TableCell>
                  <TableCell sx={{ minWidth: 105 }}>Отгрузить до</TableCell>
                </>
              ) : (
                <>
                  <TableCell sx={{ minWidth: 300 }}>Товар</TableCell>
                  <TableCell sx={{ minWidth: 170 }}>Артикул продавца</TableCell>
                  <TableCell sx={{ minWidth: 170 }}>SKU</TableCell>
                  <TableCell sx={{ minWidth: 150 }}>ШК</TableCell>
                  <TableCell sx={{ minWidth: 80 }}>Размер</TableCell>
                  <TableCell sx={{ minWidth: 125 }}>Селлер</TableCell>
                  <TableCell sx={{ minWidth: 125 }}>Маршрут сдачи</TableCell>
                  <TableCell sx={{ minWidth: 105 }}>Отгрузить до</TableCell>
                  <TableCell sx={{ minWidth: 130 }}>Статус</TableCell>
                </>
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {orders.map((order) => {
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
                    onGoToCatalog={goToCatalog}
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
                      <TableCell sx={{ minWidth: 300 }}>
                        <Stack direction="row" spacing={1.25}>
                          <ProductPhotoThumb
                            src={order.product.image_url}
                            alt={order.product.name}
                            size={56}
                            previewSize={280}
                            testId={`fbs-product-photo-${order.id}`}
                          />
                          <Box sx={{ minWidth: 220 }}>
                            <Typography variant="subtitle2" sx={{ lineHeight: 1.25, fontWeight: 700 }}>
                              {order.product.id ? order.product.name : 'Товар не сопоставлен'}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                              Заказ {orderNumberLabel(order)}
                            </Typography>
                          </Box>
                        </Stack>
                      </TableCell>
                      <TableCell sx={{ minWidth: 170 }}>
                        <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
                          {order.product.seller_article ?? '—'}
                        </Typography>
                        {order.product.wb_article ? (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', whiteSpace: 'nowrap' }}>
                            WB {order.product.wb_article}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell sx={{ minWidth: 170 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {order.product.sku ?? '—'}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ minWidth: 150 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', whiteSpace: 'nowrap' }}>
                          {order.product.barcode ?? '—'}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ minWidth: 80 }}>
                        <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
                          {order.product.size ?? '—'}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{order.seller.name ?? '—'}</Typography>
                      </TableCell>
                      <TableCell>
                        <DeliveryRouteChip order={order} />
                        {order.buyer_type === 'legal' ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>Юридическое лицо</Typography> : null}
                      </TableCell>
                      <TableCell>
                        <DeadlinePill
                          deadlineAt={order.deadline_at}
                          serverNow={serverNow}
                          cancelled={order.status === 'cancelled'}
                        />
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
                          <FbsStatusChip status={orderStatusForChip(order)} />
                        ) : null}
                        {localSupplyMissing ? (
                          <Tooltip title={externalSupplyHint(order)}>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ display: 'block', mt: 0.75 }}
                              data-testid={`fbs-order-${order.id}-external-supply`}
                            >
                              Поставка создана в {marketplaceLabel(order.marketplace)}, недоступна в WMS
                            </Typography>
                          </Tooltip>
                        ) : null}
                      </TableCell>
                    </>
                </TableRow>
              )
              return (
                localSupplyMissing ? (
                  <Tooltip key={order.id} title={externalSupplyHint(order)} placement="top" arrow>
                    {row}
                  </Tooltip>
                ) : row
              )
            })}
            {!busy && orders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={statusGroup === 'new' ? 9 : 10}>
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
            borderColor: selectionBlockers.length || mixedMarketplaceMessage ? 'error.light' : 'primary.light',
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
                  mixedMarketplaceMessage
                    ? mixedMarketplaceMessage
                    : selectionBlockers.length
                    ? selectionBlockers[0].blocker.message
                    : 'Следующий шаг — серверная проверка селлера, складов и состава.'
                }
              >
                <Typography
                  variant="caption"
                  color={selectionBlockers.length || mixedMarketplaceMessage ? 'error.main' : 'text.secondary'}
                  noWrap
                  sx={{ display: 'block' }}
                >
                  {mixedMarketplaceMessage
                    ?? (selectionBlockers.length
                    ? selectionBlockers[0].blocker.message
                    : 'Следующий шаг — серверная проверка селлера, складов и состава.')}
                </Typography>
              </Tooltip>
            </Box>
            <Button onClick={() => setSelectedOpen(true)} data-testid="fbs-selected-open">
              Показать выбранные
            </Button>
            <Button onClick={() => setSelected(new Set())}>Снять выбор</Button>
            {ozonSelection ? (
              <Button
                color="error"
                onClick={() => setCancelOpen(true)}
                data-testid="fbs-orders-cancel-ozon"
              >
                Отменить в Ozon
              </Button>
            ) : null}
            <Button
              variant="outlined"
              size="large"
              disabled={Boolean(mixedMarketplaceMessage) || selectionBlockers.length > 0 || selectedOrders.length !== selected.size}
              onClick={() => void openAddExistingDialog()}
              data-testid="fbs-05-add-existing-open"
            >
              Добавить в существующую поставку
            </Button>
            <Button
              variant="contained"
              size="large"
              disabled={Boolean(mixedMarketplaceMessage) || selectionBlockers.length > 0 || selectedOrders.length !== selected.size}
              onClick={() => setCreateOpen(true)}
            >
              Сформировать поставку
            </Button>
          </Stack>
        </Paper>
      ) : null}

      <Dialog
        open={cancelOpen}
        onClose={() => !cancelling && setCancelOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Отменить заказы в Ozon?</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2">
            Отмена уходит в кабинет Ozon и обратного хода не имеет: восстановить отменённое
            отправление нельзя. Причину Ozon получит стандартную — «товар закончился на складе
            продавца».
          </Typography>
          <Stack spacing={0.5} sx={{ mt: 1.5 }} data-testid="fbs-orders-cancel-list">
            {selectedOrders.map((order) => (
              <Typography key={order.id} variant="caption" color="text.secondary">
                {orderNumberLabel(order)} · {order.product.name}
              </Typography>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelOpen(false)} disabled={cancelling}>
            Не отменять
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => void cancelSelectedOzonOrders()}
            disabled={cancelling || selectedOrders.length === 0}
            data-testid="fbs-orders-cancel-ozon-confirm"
          >
            {cancelling ? 'Отменяем…' : 'Отменить заказы'}
          </Button>
        </DialogActions>
      </Dialog>

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
                        {orderNumberLabel(order)} · {order.product.name}
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
                              onGoToCatalog={() => goToCatalog(order.product.id)}
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
              Выбрано {selectedOrders.length} {ordersWord(selectedOrders.length)}. WMS покажет только поставки того же селлера, маркетплейса, склада и допустимого статуса.
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
        open={workspaceOpen} addressStorageEnabled={addressStorageEnabled}
        onClose={() => {
          setWorkspaceOpen(false)
          setWorkspaceSeed(null)
          void load()
        }}
      />

      <FbsPrintPreviewDialog
        token={token}
        authHeaders={authHeaders}
        batch={supplyQrBatch}
        warning={supplyQrWarning}
        open={supplyQrPreviewOpen}
        onClose={() => setSupplyQrPreviewOpen(false)}
        onApplied={confirmSupplyQrApplied}
      />

    </Box>
  )
}
