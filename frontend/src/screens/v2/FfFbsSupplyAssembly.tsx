import { FbsPackingScanBar } from './FbsPackingScanBar'
import { FbsPackingActionsToolbar, type FbsPackingActions } from './FbsPackingActionsToolbar'
import type { PackingScanController } from './fbsSequentialPacking'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogContent,
  IconButton,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import { ErrorBoundary } from '../../components/errors/ErrorBoundary'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { plural } from '../../utils/plural'
import { FbsSupplyHistoryDialog } from './FbsSupplyHistoryDialog'
import { FfFbsAssemblyPick } from './FfFbsAssemblyPick'
import { FfFbsSupplyWorkspace } from './FfFbsSupplyWorkspace'
import {
  fetchFbsWorkspace,
  getFbsPickOptions,
  getFbsPickingContext,
  type FbsPickOptionProduct,
  type FbsWorkspace,
} from './fbsApi'
import {
  buildFbsPickingListPrintHtml,
  fbsErrorText,
  fbsOrderKizRejectedByWb,
  fbsPickSourceLabels,
  ordersWord,
} from './fbsUx'
import {
  fbsAssemblyPickingRows,
  fbsAssemblyReadiness,
  fbsAssemblySupplyTitle,
  fbsSupplyRouteLabel,
  readFbsAssemblyStage,
  saveFbsAssemblyStage,
  type FbsAssemblyStageKey,
} from './fbsSupplyAssembly'

// WMS-574 R5–R7, R12–R15: окно «Сборка · K поставок». Оформление и размеры —
// как у карточки поставки (FfFbsSupplyWorkspace): тот же Dialog, та же шапка
// с грузовиком и полосой прогресса, те же вкладки. Группа — только перечень
// поставок в адресе (supply_ids, Д4); вся работа хранится у каждой поставки
// на сервере, поэтому после перезагрузки окно читает её заново.

const STAGES: Array<{ key: FbsAssemblyStageKey; label: string }> = [
  { key: 'composition', label: 'Состав' },
  { key: 'picking', label: 'Подбор' },
  { key: 'packing', label: 'Упаковка и маркировка' },
  { key: 'boxes', label: 'Короба' },
]

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  supplyIds: string[]
  open: boolean
  onClose: () => void
}

export function FfFbsSupplyAssembly({ token, authHeaders, supplyIds, open, onClose }: Props) {
  const idsKey = supplyIds.join(',')
  const [workspaces, setWorkspaces] = useState<Record<string, FbsWorkspace>>({})
  const [stage, setStage] = useState<FbsAssemblyStageKey>('composition')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [historySupplyId, setHistorySupplyId] = useState<string | null>(null)
  // Рамки поставок — карточки поставок в режиме рамки. Они монтируются при
  // первом открытии «Упаковки» и живут до закрытия окна, чтобы активная
  // поставка и открытый короб не терялись при переходе между вкладками.
  const [framesMounted, setFramesMounted] = useState(false)
  const [packingHost, setPackingHost] = useState<HTMLDivElement | null>(null)
  const [packingActions, setPackingActions] = useState<Record<string, FbsPackingActions>>({})
  const registerPackingActions = useCallback((id: string, actions: FbsPackingActions | null) => {
    setPackingActions(current => {
      if (actions) return current[id] === actions ? current : { ...current, [id]: actions }
      if (!current[id]) return current
      const next = { ...current }
      delete next[id]
      return next
    })
  }, [])
  const [packingColumnsBySupply, setPackingColumnsBySupply] = useState<Record<string, { size: boolean; markingAvailable: boolean }>>({})
  const reportPackingColumns = useCallback((id: string, columns: { size: boolean; markingAvailable: boolean }) => {
    setPackingColumnsBySupply(current => current[id]?.size === columns.size && current[id]?.markingAvailable === columns.markingAvailable
      ? current : { ...current, [id]: columns })
  }, [])
  const scanners = useRef(new Map<string, PackingScanController>())
  const [, setScannerVersion] = useState(0)
  const [promotedSupplyId, setPromotedSupplyId] = useState<string | null>(null)
  const onScanChange = useCallback(() => setScannerVersion((value) => value + 1), [])
  const onPromotePackingOrder = useCallback((supplyId: string) => setPromotedSupplyId(supplyId), [])
  // WMS-636: фильтр «Не принятые WB КИЗ» по всем поставкам сборки; выключен по умолчанию.
  const [rejectedFilter, setRejectedFilter] = useState(false)
  const registerScanner = useCallback((id: string, scanner: PackingScanController | null) => {
    if (scanner) scanners.current.set(id, scanner)
    else scanners.current.delete(id)
    setScannerVersion((value) => value + 1)
  }, [])
  const escapeHandlerRef = useRef<(() => boolean) | null>(null)
  const openGeneration = useRef(0)
  const initialStageGeneration = useRef<number | null>(null)
  const writeSeq = useRef(new Map<string, number>())
  const silentRefreshInFlight = useRef(false)

  const selectStage = (next: FbsAssemblyStageKey) => {
    initialStageGeneration.current = null
    if (supplyIds.length) saveFbsAssemblyStage(supplyIds, next)
    setStage(next)
    setError(null)
    if (next === 'packing' || next === 'boxes') setFramesMounted(true)
  }

  /** Читает одну поставку; применяет только последний начатый ответ по ней. */
  const loadOne = useCallback(async (supplyId: string) => {
    const generation = openGeneration.current
    const seq = (writeSeq.current.get(supplyId) ?? 0) + 1
    writeSeq.current.set(supplyId, seq)
    const next = await fetchFbsWorkspace(token, authHeaders, supplyId)
    if (generation !== openGeneration.current || writeSeq.current.get(supplyId) !== seq) return
    setWorkspaces((current) => ({ ...current, [supplyId]: next }))
    return next
  }, [token, authHeaders])

  const loadAll = useCallback(async (silent = false) => {
    const ids = idsKey ? idsKey.split(',') : []
    if (!open || ids.length === 0) return
    const generation = openGeneration.current
    if (!silent) setBusy(true)
    try {
      const loaded = await Promise.all(ids.map((id) => loadOne(id)))
      if (!silent && initialStageGeneration.current === generation) {
        initialStageGeneration.current = null
        // The default for a completed task applies only when opening it. A refresh
        // must not move the operator away from the tab they chose while working.
        if (loaded.every((one) => one && one.progress.total > 0 && one.progress.picked === one.progress.total)) {
          setStage('packing')
          setFramesMounted(true)
        }
      }
    } catch (cause) {
      if (generation === openGeneration.current && !silent) {
        setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Не удалось загрузить поставки.')
      }
    } finally {
      if (generation === openGeneration.current && !silent) setBusy(false)
    }
  }, [idsKey, loadOne, open])

  useEffect(() => {
    openGeneration.current += 1
    writeSeq.current = new Map()
    initialStageGeneration.current = null
    if (!open || !idsKey) return
    initialStageGeneration.current = openGeneration.current
    const ids = idsKey.split(',')
    setWorkspaces({})
    setPackingActions({})
    setError(null)
    setBusy(false)
    setHistorySupplyId(null)
    setRejectedFilter(false)
    const restoredStage = readFbsAssemblyStage(ids) ?? 'composition'
    setStage(restoredStage)
    setFramesMounted(restoredStage === 'packing' || restoredStage === 'boxes')
    void loadAll()
  }, [open, idsKey, loadAll])

  // Тихое обновление раз в 15 с — как у карточки поставки на рабочих вкладках.
  // На «Упаковке» рамки обновляются сами (карточка) и присылают снимок сюда.
  useEffect(() => {
    if (!open || !idsKey || stage !== 'picking') return
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible' || silentRefreshInFlight.current) return
      silentRefreshInFlight.current = true
      void loadAll(true).finally(() => { silentRefreshInFlight.current = false })
    }, 15_000)
    return () => window.clearInterval(timer)
  }, [open, idsKey, stage, loadAll])

  const ordered = useMemo(
    () => supplyIds.map((id) => workspaces[id]).filter((one): one is FbsWorkspace => Boolean(one)),
    [supplyIds, workspaces],
  )
  const packingColumns = {
    size: supplyIds.some(id => packingColumnsBySupply[id]?.size),
    markingAvailable: supplyIds.some(id => packingColumnsBySupply[id]?.markingAvailable),
  }
  const allLoaded = ordered.length === supplyIds.length && supplyIds.length > 0
  const ozonOnly = ordered.every((one) => one.supply.marketplace === 'ozon')
  const { ready, total } = fbsAssemblyReadiness(ordered)
  const percent = total ? Math.round((ready / total) * 100) : 0
  const sellerNames = [...new Set(ordered.map((one) => one.supply.seller.name))].join(', ')
  const ordersCount = ordered.reduce((sum, one) => sum + one.orders.length, 0)
  // WMS-636 R1, C10: N — сумма по WB-поставкам; шапку рисует поставка последнего скана,
  // а без скана — первая поставка с непринятыми КИЗ (выше неё в ленте красных строк нет).
  const rejectedBySupply = ordered
    .filter((one) => one.supply.marketplace === 'wb')
    .map((one) => ({ id: one.supply.id, count: one.orders.filter(fbsOrderKizRejectedByWb).length }))
  const rejectedCount = rejectedBySupply.reduce((sum, one) => sum + one.count, 0)
  const rejectedFilterOn = rejectedFilter && rejectedCount > 0
  useEffect(() => { if (rejectedCount === 0) setRejectedFilter(false) }, [rejectedCount])
  const rejectedHeaderSupplyId = rejectedBySupply.some((one) => one.id === promotedSupplyId)
    ? promotedSupplyId
    : rejectedBySupply.find((one) => one.count > 0)?.id ?? null

  const requestClose = () => {
    onClose()
  }

  // Снимок поставки из рамки — для шапки окна и «Состава».
  const onFrameWorkspace = useCallback((next: FbsWorkspace) => {
    writeSeq.current.set(next.supply.id, (writeSeq.current.get(next.supply.id) ?? 0) + 1)
    setWorkspaces((current) => (current[next.supply.id] === next ? current : { ...current, [next.supply.id]: next }))
  }, [])

  const registerEscape = useCallback((handler: (() => boolean) | null) => {
    escapeHandlerRef.current = handler
  }, [])

  // Д14: лист подбора по всей группе — тот же шаблон, что у карточки; строки —
  // суммарный план, в шапке — номера всех поставок группы.
  const printPickingList = async () => {
    if (!allLoaded) return
    const printWindow = window.open('', '_blank')
    if (!printWindow) {
      setError('Браузер заблокировал окно печати. Разрешите всплывающие окна и повторите.')
      return
    }
    printWindow.opener = null
    setError(null)
    printWindow.document.write('<title>Лист подбора</title><p style="font:14px Arial,sans-serif">Готовим лист подбора…</p>')
    let rows = fbsAssemblyPickingRows(ordered)
    try {
      const optionLists = await Promise.all(ordered.map((one) => getFbsPickOptions(token, authHeaders, one.supply.id)))
      const byProduct = new Map<string, FbsPickOptionProduct[]>()
      for (const list of optionLists) {
        for (const option of list) byProduct.set(option.product_id, [...(byProduct.get(option.product_id) ?? []), option])
      }
      rows = rows.map((row) => {
        const options = byProduct.get(row.key)
        if (!options?.length) return row
        const picked = Math.min(options.reduce((sum, option) => sum + option.picked_qty, 0), row.required)
        return { ...row, picked, locations: fbsPickSourceLabels(options[0].locations, row.required - picked) }
      })
    } catch {
      rows = rows.map((row) => (row.locations.length ? row : { ...row, locations: ['—'] }))
      setError('Не удалось получить ячейки и тару — лист подбора напечатан без них.')
    }
    try {
      const lists = await Promise.all(ordered.map((one) => getFbsPickingContext(token, authHeaders, one.supply.id)))
      const context = new Map<string, { locations: string[]; inbound_supplies: string[]; source_groups: Array<{ key: string; title: string; lines: string[] }> }>()
      for (const list of lists) for (const item of list) {
        const previous = context.get(item.product_id)
        const mergedGroups = new Map((previous?.source_groups ?? []).map((group) => [group.key, group]))
        for (const group of item.source_groups) {
          const earlier = mergedGroups.get(group.key)
          mergedGroups.set(group.key, { ...group, lines: [...new Set([...(earlier?.lines ?? []), ...group.lines])] })
        }
        context.set(item.product_id, {
          locations: [...new Set([...(previous?.locations ?? []), ...item.locations])],
          inbound_supplies: [...new Set([...(previous?.inbound_supplies ?? []), ...item.inbound_supplies])],
          source_groups: [...mergedGroups.values()],
        })
      }
      rows = rows.map((row) => {
        const item = context.get(row.key)
        return item ? { ...row, locations: item.locations, inboundSupplies: item.inbound_supplies, sourceGroups: item.source_groups } : row
      })
    } catch {
      setError('Не удалось получить приёмки и все места хранения — обновите лист подбора.')
      printWindow.close()
      return
    }
    if (printWindow.closed) return
    const distinct = (values: string[]) => [...new Set(values)].join(', ')
    const earliestDeadline = ordered
      .map((one) => one.supply.nearest_deadline_at)
      .sort((a, b) => new Date(a).getTime() - new Date(b).getTime())[0]
    const marketplace = ordered.every((one) => one.supply.marketplace === 'wb')
      ? 'wb'
      : ordered.every((one) => one.supply.marketplace === 'ozon')
        ? 'ozon'
        : 'mixed'
    printWindow.document.open()
    printWindow.document.write(buildFbsPickingListPrintHtml({
      supplyName: `Сборка · ${ordered.length} ${plural(ordered.length, ['поставка', 'поставки', 'поставок'])}`,
      wbSupplyId: ordered.map((one) => one.supply.wb_supply_id).filter(Boolean).join(', ') || null,
      marketplace,
      sellerName: distinct(ordered.map((one) => one.supply.seller.name)),
      wmsWarehouseName: distinct(ordered.map((one) => one.supply.wms_warehouse.name)),
      routeLabel: distinct(ordered.map(fbsSupplyRouteLabel)),
      deadlineLabel: earliestDeadline ? new Date(earliestDeadline).toLocaleString('ru-RU') : '—',
      printedAtLabel: new Date().toLocaleString('ru-RU'),
      rows,
    }))
    printWindow.document.close()
  }

  const pickSupplies = useMemo(
    () => ordered.map((one) => ({ id: one.supply.id, sellerId: one.supply.seller.id, marketplace: one.supply.marketplace })),
    [ordered],
  )

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : (_event, reason) => {
        // Esc при ожидании ЧЗ снимает ожидание в активной рамке, как в карточке.
        if (reason === 'escapeKeyDown' && escapeHandlerRef.current?.()) return
        requestClose()
      }}
      maxWidth={false}
      fullScreen={false}
      slotProps={{ paper: { sx: { width: 'min(1500px, 98vw)', height: '94vh', m: 1 } } }}
      data-testid="fbs-assembly"
    >
      <Box sx={{ px: 2.5, py: 2, borderBottom: 1, borderColor: 'divider', bgcolor: '#fff' }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'flex-start' }}>
          <LocalShippingOutlinedIcon color="primary" sx={{ mt: 0.4 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6">
              Сборка · {supplyIds.length} {plural(supplyIds.length, ['поставка', 'поставки', 'поставок'])}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {allLoaded ? sellerNames : 'Загружаем данные поставок…'}
            </Typography>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mt: 1.25 }}>
              <LinearProgress variant="determinate" value={percent} sx={{ flex: 1, maxWidth: 480, height: 8, borderRadius: 4 }} />
              <Typography variant="caption" sx={{ fontWeight: 750 }}>{ready} из {total} подготовлено к отгрузке</Typography>
            </Stack>
          </Box>
          <Button
            variant="outlined"
            startIcon={<PrintOutlinedIcon />}
            onClick={() => void printPickingList()}
            disabled={!allLoaded}
            data-testid="fbs-pick-list-print"
          >
            Печать листа подбора
          </Button>
          <IconButton onClick={requestClose} disabled={busy} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Stack>
      </Box>

      <Tabs
        value={stage}
        onChange={(_, value: FbsAssemblyStageKey) => selectStage(value)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2, borderBottom: 1, borderColor: 'divider', bgcolor: 'rgba(91,33,182,.035)' }}
      >
        {STAGES.map((item) => <Tab key={item.key} value={item.key} label={item.label} />)}
      </Tabs>

      {busy ? <LinearProgress /> : null}
      <DialogContent sx={{ p: 0, bgcolor: '#f4f6fb' }}>
        <Box sx={{ p: { xs: 1.5, md: 2.5 }, minHeight: '100%' }}>
          {error ? <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert> : null}

          {!allLoaded ? (
            <Stack spacing={2} sx={{ alignItems: 'center', justifyContent: 'center', py: 10 }}>
              <CircularProgress />
              <Typography>Загружаем актуальное состояние поставок…</Typography>
            </Stack>
          ) : null}

          {allLoaded && stage === 'composition' ? (
            <Paper variant="outlined" sx={{ p: 2 }} data-testid="fbs-assembly-composition">
              <Box sx={{ mb: 2 }}>
                <Typography variant="h6">Состав сборки</Typography>
                <Typography variant="body2" color="text.secondary">
                  {ordersCount} {ordersWord(ordersCount)} в {ordered.length} поставках
                </Typography>
              </Box>
              <Table size="small">
                <TableHead><TableRow><TableCell>Фото</TableCell><TableCell>Заказ WB</TableCell><TableCell>Товар и идентификаторы</TableCell><TableCell>Количество</TableCell><TableCell>Маркировка</TableCell><TableCell>Подбор</TableCell></TableRow></TableHead>
                <TableBody>
                  {ordered.map((workspace) => (
                    <Fragment key={workspace.supply.id}>
                      <TableRow sx={{ bgcolor: 'action.hover' }} data-testid={`fbs-assembly-composition-supply-${workspace.supply.id}`}>
                        <TableCell colSpan={6}>
                          <Typography variant="subtitle2">{fbsAssemblySupplyTitle(workspace)}</Typography>
                        </TableCell>
                      </TableRow>
                      {/* Строка — та же, что в «Составе» карточки поставки (WB). */}
                      {workspace.orders.map((order) => {
                        const positions = order.positions.length ? order.positions : [{ product_id: order.product.id, name: order.product.name, seller_article: order.product.seller_article, sku: order.product.sku, quantity: 1, picked_quantity: order.pick.status === 'picked' ? 1 : 0 }]
                        return <TableRow key={order.id}>
                          <TableCell><ProductPhotoThumb src={order.product.image_url} alt={order.product.name} size={42} previewSize={280} testId={`fbs-composition-photo-${order.id}`} /></TableCell><TableCell><Link component="button" type="button" underline="hover" sx={{ textAlign: 'left' }} onClick={() => setHistorySupplyId(workspace.supply.id)} data-testid={`fbs-composition-history-${order.id}`}>{`№${order.wb_order_id}`}</Link></TableCell>
                          <TableCell><Stack spacing={0.5}>{positions.map((position, index) => <Box key={`${position.sku ?? position.product_id ?? position.name}-${index}`}><Typography variant="body2" sx={{ fontWeight: 700 }}>{position.name}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Артикул: {position.seller_article ?? '—'}{position.sku ? ` · SKU: ${position.sku}` : ''}</Typography></Box>)}</Stack></TableCell>
                          <TableCell><Stack spacing={0.5}>{positions.map((position, index) => <Typography key={`${position.sku ?? position.product_id ?? position.name}-${index}`} variant="body2">{order.positions.length ? `${position.picked_quantity} из ${position.quantity} шт.` : '1 шт.'}</Typography>)}</Stack></TableCell>
                          <TableCell>{order.metadata.required.length ? order.metadata.required.join(', ') : 'Не требуется'}</TableCell><TableCell>{order.pick.status === 'picked' ? 'Подобран' : 'Ожидает'}</TableCell>
                        </TableRow>
                      })}
                    </Fragment>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          ) : null}

          {allLoaded && stage === 'picking' ? (
            <Box data-testid="fbs-pick-unified">
              <FfFbsAssemblyPick token={token} supplies={pickSupplies} />
            </Box>
          ) : null}

          {/* Рамки держатся смонтированными после первого открытия «Упаковки»;
              на других вкладках они скрыты и сканер не слушают. */}
          {allLoaded && framesMounted ? (
            <Stack
              spacing={2}
              sx={{ display: stage === 'packing' || stage === 'boxes' ? 'flex' : 'none' }}
              data-testid="fbs-assembly-packing"
            >
              <Paper variant="outlined" sx={{ overflow: 'hidden', display: stage === 'packing' ? undefined : 'none' }}>
                <FbsPackingScanBar token={token} contextKey={supplyIds.join(',')} qrDisabled={ozonOnly} rejected={{
                  count: rejectedCount, active: rejectedFilterOn, onToggle: () => setRejectedFilter((current) => !current),
                }} enabled={open && stage === 'packing' && scanners.current.size > 0} controllers={supplyIds.flatMap((id) => {
                  const scanner = scanners.current.get(id)
                  return scanner ? [scanner] : []
                })} />
                <FbsPackingActionsToolbar entries={supplyIds.flatMap(id => packingActions[id] ? [packingActions[id]] : [])}
                  active={open && stage === 'packing'} contextKey={idsKey} />
                <Box ref={setPackingHost} sx={{ display: 'flex', flexDirection: 'column' }} data-testid="fbs-unified-packing-rows" />
              </Paper>
              {ordered.map((workspace) => {
                const supplyId = workspace.supply.id
                return (
                  <FfFbsSupplyWorkspace
                    key={supplyId}
                    token={token}
                    authHeaders={authHeaders}
                    supplyId={supplyId}
                    open={open}
                    onClose={() => undefined}
                    assemblyFrame={{
                      packingHost, registerScanner, registerPackingActions, onScanChange, promotedSupplyId, onPromotePackingOrder,
                      packingColumns,
                      onPackingColumnsChange: columns => reportPackingColumns(supplyId, columns),
                      rejectedFilter: { active: rejectedFilterOn, count: rejectedCount, headerSupplyId: rejectedHeaderSupplyId },
                      active: true,
                      expanded: true,
                      stage: stage === 'boxes' ? 'boxes' : 'packing',
                      visible: stage === 'packing' || stage === 'boxes',
                      onToggleExpanded: () => undefined,
                      onActivate: () => undefined,
                      onDeactivate: () => undefined,
                      onWorkspaceChange: onFrameWorkspace,
                      registerEscape,
                    }}
                  />
                )
              })}
            </Stack>
          ) : null}
        </Box>
      </DialogContent>

      <ErrorBoundary component="FbsSupplyHistoryDialog"><FbsSupplyHistoryDialog
        token={token}
        supplyId={historySupplyId}
        open={Boolean(historySupplyId)}
        onClose={() => setHistorySupplyId(null)}
      /></ErrorBoundary>
    </Dialog>
  )
}
