import { useCallback, useEffect, useRef, useState } from 'react'
import { Box, Button, Skeleton, Stack, Tab, Tabs, Typography } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { AppDialog, ErrorNotice, ReportMetricStrip } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { ProductCardMainTab } from './ProductCardMainTab'
import { ProductCardMovementsTab } from './ProductCardMovementsTab'
import { ProductCardLocationTab } from './ProductCardLocationTab'
import { ProductCardFbsStockTab } from './ProductCardFbsStockTab'
import type { ProductCardData, ProductCardStockTotals, ProductCardTriggerRow } from './productCardTypes'

type WarehouseRow = { id: string; name: string; code: string; is_operational: boolean }

type TabKey = 'main' | 'movements' | 'location' | 'fbs_stock'

type Props = {
  /**
   * Строка каталога, по которой открыта карточка. Компонент, как и
   * `FbsStockDialogContainer`, монтируется только когда карточка открыта —
   * решает об этом каталог (`{cardRow ? <ProductCardDialog row={cardRow} .../> : null}`).
   */
  row: ProductCardTriggerRow
  token: string
  authHeaders: (t: string) => Record<string, string>
  /** Администратор ФФ — видит «Задать остаток» и может редактировать каталог. */
  canManageCatalog: boolean
  /** Доступен отчёт «Остатки и движения» — то же право, что пункт меню «Отчёты» (R3). */
  canViewMovements: boolean
  /** У организации включено адресное хранение — то же условие, что пункт меню «Ячейки» (R3). */
  addressStorageEnabled: boolean
  warehouses: WarehouseRow[]
  /** Открыть документ приёмки из вкладки «Движения» — как у отчёта «Остатки и движения». */
  onOpenInbound?: (id: string) => void
  /** Карточка закрыта. `changed` — сервер что-то сохранил или товара больше нет: каталог должен перечитаться. */
  onClose: (changed: boolean) => void
}

const emptyTotals: ProductCardStockTotals = { quantity: 0, reserved: 0, available: 0 }

export function ProductCardDialog({
  row,
  token,
  authHeaders,
  canManageCatalog,
  canViewMovements,
  addressStorageEnabled,
  warehouses,
  onOpenInbound,
  onClose,
}: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>('main')
  const [visitedTabs, setVisitedTabs] = useState<Set<TabKey>>(new Set(['main']))
  const [notFound, setNotFound] = useState(false)
  const changedRef = useRef(false)

  const [cardStatus, setCardStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [cardData, setCardData] = useState<ProductCardData | null>(null)
  const [cardError, setCardError] = useState<string | null>(null)
  const cardAbortRef = useRef<AbortController | null>(null)

  const [metricsStatus, setMetricsStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [metrics, setMetrics] = useState<ProductCardStockTotals>(emptyTotals)
  const metricsAbortRef = useRef<AbortController | null>(null)

  const markChanged = useCallback(() => {
    changedRef.current = true
  }, [])

  const loadCard = useCallback(
    async (productId: string) => {
      cardAbortRef.current?.abort()
      const controller = new AbortController()
      cardAbortRef.current = controller
      setCardStatus('loading')
      setCardError(null)
      try {
        const res = await fetch(apiUrl(`/products/${productId}/card`), {
          headers: { ...authHeaders(token) },
          signal: controller.signal,
        })
        if (res.status === 404) {
          if (controller.signal.aborted) return
          setNotFound(true)
          return
        }
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res))
        }
        const body = (await res.json()) as ProductCardData
        if (controller.signal.aborted) return
        setCardData(body)
        setCardStatus('ready')
      } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return
        setCardError(e instanceof Error ? e.message : 'Не удалось загрузить данные товара.')
        setCardStatus('error')
      }
    },
    [authHeaders, token],
  )

  const loadMetrics = useCallback(
    async (productId: string) => {
      metricsAbortRef.current?.abort()
      const controller = new AbortController()
      metricsAbortRef.current = controller
      setMetricsStatus('loading')
      try {
        const params = new URLSearchParams()
        params.append('product_id', productId)
        const res = await fetch(apiUrl(`/operations/inventory-balances/summary?${params.toString()}`), {
          headers: { ...authHeaders(token) },
          signal: controller.signal,
        })
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res))
        }
        const body = (await res.json()) as Array<{ quantity: number; reserved: number; available: number }>
        if (controller.signal.aborted) return
        const first = body[0]
        setMetrics({
          quantity: first?.quantity ?? 0,
          reserved: first?.reserved ?? 0,
          available: first?.available ?? 0,
        })
        setMetricsStatus('ready')
      } catch (e) {
        if ((e as { name?: string }).name === 'AbortError') return
        setMetricsStatus('error')
      }
    },
    [authHeaders, token],
  )

  // Открытие карточки (или переключение на другой товар) — сброс на «Основное»
  // и перечитывание с нуля. Само открытие ничего не сохраняет (R1).
  useEffect(() => {
    setActiveTab('main')
    setVisitedTabs(new Set(['main']))
    setNotFound(false)
    changedRef.current = false
    setCardData(null)
    setFbsStockBusy(false)
    void loadCard(row.id)
    void loadMetrics(row.id)
    return () => {
      cardAbortRef.current?.abort()
      metricsAbortRef.current?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when the product changes
  }, [row.id])

  // Идёт запись во вкладке «Задать остаток» — тело окна «Остаток для FBS»
  // остаётся смонтированным при переключении вкладок (R9-подобный принцип:
  // скрытая вкладка не теряет состояние), поэтому запрос переживёт уход с
  // вкладки; но закрыть карточку или уйти с вкладки, пока ответ не пришёл, —
  // значит либо потерять обратную связь о сохранении, либо неожиданно
  // захлопнуть карточку, когда ответ придёт позже (R12, R16-подобная защита
  // «конец одного действия не должен разблокировать…», перенесена на уровень
  // карточки).
  const [fbsStockBusy, setFbsStockBusy] = useState(false)

  const handleClose = useCallback(() => {
    if (fbsStockBusy) return
    onClose(changedRef.current || notFound)
  }, [fbsStockBusy, notFound, onClose])

  // Закрытие, которым сама вкладка «Задать остаток» решает завершить
  // карточку («Сохранить»/«Отмена», R12) — в отличие от `handleClose`
  // (Закрыть/Escape/фон), не смотрит на `fbsStockBusy`: в момент вызова
  // запрос только что успешно завершился, но `busy` ещё не долетел до этого
  // состояния через эффект контейнера (пришлось бы ждать лишний рендер и
  // карточка осталась бы открытой после удачного сохранения).
  const closeCardFromFbsTab = useCallback(
    (changed: boolean) => {
      if (changed) markChanged()
      onClose(changedRef.current || notFound)
    },
    [markChanged, notFound, onClose],
  )

  const selectTab = useCallback(
    (key: TabKey) => {
      if (fbsStockBusy && key !== 'fbs_stock') return
      setActiveTab(key)
      setVisitedTabs((current) => {
        if (current.has(key)) return current
        const next = new Set(current)
        next.add(key)
        return next
      })
    },
    [fbsStockBusy],
  )

  // Нижняя панель окна «Остаток для FBS» портaлится сюда, пока вкладка
  // «Задать остаток» активна (решение 7 в требованиях; портал — не состояние
  // React, чтобы обновление кнопок не гоняло лишний ререндер карточки).
  const [footerSlotEl, setFooterSlotEl] = useState<HTMLDivElement | null>(null)

  const tabs: { key: TabKey; label: string }[] = [{ key: 'main', label: 'Основное' }]
  if (canViewMovements) tabs.push({ key: 'movements', label: 'Движения' })
  if (addressStorageEnabled) tabs.push({ key: 'location', label: 'Расположение' })
  if (canManageCatalog && row.seller_id) tabs.push({ key: 'fbs_stock', label: 'Задать остаток' })

  const displayName = cardData?.name ?? row.name
  const displayPhoto = cardData?.wb_primary_image_url ?? row.wb_primary_image_url

  const title = notFound ? (
    'Товар не найден'
  ) : (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', minWidth: 0 }}>
      <ProductPhotoThumb src={displayPhoto} size={36} testId="product-card-photo" />
      <Typography variant="h6" component="span" sx={{ wordBreak: 'break-word' }} data-testid="product-card-title">
        {displayName}
      </Typography>
    </Stack>
  )

  // Нижняя панель — «Закрыть» на всех вкладках, кроме «Задать остаток»: там
  // «Отмена»/«Сохранить» из общего компонента окна «Остаток для FBS» (R12),
  // порталятся в footerSlot ниже. Слот смонтирован всегда (как только вкладка
  // «Задать остаток» вообще доступна), чтобы тело вкладки, оставаясь
  // смонтированным при уходе с неё, не теряло цель для портала.
  const footerSlot = tabs.some((t) => t.key === 'fbs_stock') ? (
    <Box
      ref={setFooterSlotEl}
      sx={{ display: activeTab === 'fbs_stock' ? 'contents' : 'none' }}
      data-testid="product-card-fbs-footer-slot"
    />
  ) : null

  const footer = notFound ? (
    <Button onClick={handleClose} data-testid="product-card-close">
      Закрыть
    </Button>
  ) : (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      {footerSlot}
      {activeTab !== 'fbs_stock' ? (
        <Button onClick={handleClose} disabled={fbsStockBusy} data-testid="product-card-close">
          Закрыть
        </Button>
      ) : null}
    </Stack>
  )

  return (
    <AppDialog
      open
      onClose={handleClose}
      maxWidth="lg"
      title={title}
      actions={footer}
      testId="product-card-dialog"
    >
      {notFound ? (
        <ErrorNotice testId="product-card-not-found">Товар не найден.</ErrorNotice>
      ) : (
        <>
          {metricsStatus === 'error' ? (
            <ErrorNotice testId="product-card-metrics-error">
              Не удалось загрузить остаток.{' '}
              <Button size="small" onClick={() => void loadMetrics(row.id)} data-testid="product-card-metrics-retry">
                Повторить
              </Button>
            </ErrorNotice>
          ) : (
            <ReportMetricStrip
              items={[
                { key: 'quantity', label: 'Остаток', value: metrics.quantity },
                { key: 'reserved', label: 'Резерв', value: metrics.reserved },
                { key: 'available', label: 'Доступно', value: metrics.available },
              ]}
              loading={metricsStatus === 'loading'}
              testId="product-card-metrics"
            />
          )}

          <Tabs
            value={activeTab}
            onChange={(_, value: TabKey) => selectTab(value)}
            aria-label="Вкладки карточки товара"
            data-testid="product-card-tabs"
            sx={{ mb: 2, borderBottom: '1px solid', borderColor: 'divider' }}
          >
            {tabs.map((tab) => (
              <Tab key={tab.key} value={tab.key} label={tab.label} data-testid={`product-card-tab-${tab.key}`} />
            ))}
          </Tabs>

          <Box hidden={activeTab !== 'main'} sx={{ minWidth: 0 }} data-testid="product-card-panel-main">
            {cardStatus === 'loading' ? (
              <Stack spacing={1}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} variant="rounded" height={22} />
                ))}
              </Stack>
            ) : cardStatus === 'error' || !cardData ? (
              <ErrorNotice testId="product-card-main-error">
                {cardError ?? 'Не удалось загрузить данные товара.'}{' '}
                <Button size="small" onClick={() => void loadCard(row.id)} data-testid="product-card-main-retry">
                  Повторить
                </Button>
              </ErrorNotice>
            ) : (
              <ProductCardMainTab data={cardData} />
            )}
          </Box>

          {tabs.some((t) => t.key === 'movements') ? (
            <Box hidden={activeTab !== 'movements'} sx={{ minWidth: 0 }} data-testid="product-card-panel-movements">
              {visitedTabs.has('movements') ? (
                <ProductCardMovementsTab
                  productId={row.id}
                  token={token}
                  authHeaders={authHeaders}
                  onNotFound={() => setNotFound(true)}
                  onOpenInbound={onOpenInbound}
                />
              ) : null}
            </Box>
          ) : null}

          {tabs.some((t) => t.key === 'location') ? (
            <Box hidden={activeTab !== 'location'} sx={{ minWidth: 0 }} data-testid="product-card-panel-location">
              {visitedTabs.has('location') ? (
                <ProductCardLocationTab
                  productId={row.id}
                  token={token}
                  authHeaders={authHeaders}
                  locationWarehouses={cardData?.location_warehouses ?? []}
                  onNotFound={() => setNotFound(true)}
                  onStockChanged={() => {
                    markChanged()
                    void loadCard(row.id)
                    void loadMetrics(row.id)
                  }}
                />
              ) : null}
            </Box>
          ) : null}

          {tabs.some((t) => t.key === 'fbs_stock') && row.seller_id ? (
            // Решение 12 (27.09): тело «Задать остаток» не шире содержимого окна
            // «Остаток для FBS» (оно AppDialog md — 900px по умолчанию темы MUI),
            // хотя окно карточки шире (lg).
            <Box hidden={activeTab !== 'fbs_stock'} sx={{ minWidth: 0, maxWidth: 900 }} data-testid="product-card-panel-fbs-stock">
              {visitedTabs.has('fbs_stock') ? (
                <ProductCardFbsStockTab
                  productId={row.id}
                  productName={row.name}
                  productSku={row.sku_code}
                  productSize={row.wb_size}
                  sellerId={row.seller_id}
                  sellerName={row.seller_name}
                  token={token}
                  warehouses={warehouses}
                  canEditBindings={canManageCatalog}
                  footerSlotEl={footerSlotEl}
                  onCardClose={closeCardFromFbsTab}
                  onBusyChange={setFbsStockBusy}
                />
              ) : null}
            </Box>
          ) : null}
        </>
      )}
    </AppDialog>
  )
}
