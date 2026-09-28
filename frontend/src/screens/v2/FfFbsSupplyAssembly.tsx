import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
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
import { alpha } from '@mui/material/styles'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import CloseIcon from '@mui/icons-material/Close'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import LocalShippingOutlinedIcon from '@mui/icons-material/LocalShippingOutlined'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import { ErrorBoundary } from '../../components/errors/ErrorBoundary'
import { ProductPhotoThumb } from '../../components/ProductPhotoThumb'
import { plural } from '../../utils/plural'
import { FbsSupplyHistoryDialog } from './FbsSupplyHistoryDialog'
import { FfFbsAssemblyPick } from './FfFbsAssemblyPick'
import {
  fetchFbsWorkspace,
  getFbsPickOptions,
  startFbsSupplyWork,
  type FbsPickOptionProduct,
  type FbsWorkspace,
} from './fbsApi'
import {
  buildFbsPickingListPrintHtml,
  fbsErrorText,
  fbsPickSourceLabels,
  ordersWord,
} from './fbsUx'
import {
  fbsAssemblyPickingRows,
  fbsAssemblyReadiness,
  fbsAssemblySupplyTitle,
  fbsSupplyRouteLabel,
  fbsSupplyTransferred,
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
  // Активная поставка и развёрнутые рамки — состояние экрана (Д4): после
  // перезагрузки оператор снова жмёт «Начать работу с поставкой».
  const [activeSupplyId, setActiveSupplyId] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set())
  const [startingSupplyId, setStartingSupplyId] = useState<string | null>(null)
  const openGeneration = useRef(0)
  const writeSeq = useRef(new Map<string, number>())
  const silentRefreshInFlight = useRef(false)

  const selectStage = (next: FbsAssemblyStageKey) => {
    if (supplyIds.length) saveFbsAssemblyStage(supplyIds, next)
    setStage(next)
    setError(null)
  }

  /** Читает одну поставку; применяет только последний начатый ответ по ней. */
  const loadOne = useCallback(async (supplyId: string) => {
    const generation = openGeneration.current
    const seq = (writeSeq.current.get(supplyId) ?? 0) + 1
    writeSeq.current.set(supplyId, seq)
    const next = await fetchFbsWorkspace(token, authHeaders, supplyId)
    if (generation !== openGeneration.current || writeSeq.current.get(supplyId) !== seq) return
    setWorkspaces((current) => ({ ...current, [supplyId]: next }))
  }, [token, authHeaders])

  const loadAll = useCallback(async (silent = false) => {
    const ids = idsKey ? idsKey.split(',') : []
    if (!open || ids.length === 0) return
    const generation = openGeneration.current
    if (!silent) setBusy(true)
    try {
      await Promise.all(ids.map((id) => loadOne(id)))
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
    if (!open || !idsKey) return
    const ids = idsKey.split(',')
    setWorkspaces({})
    setError(null)
    setBusy(false)
    setActiveSupplyId(null)
    setExpandedIds(new Set())
    setStartingSupplyId(null)
    setHistorySupplyId(null)
    setStage(readFbsAssemblyStage(ids) ?? 'composition')
    void loadAll()
  }, [open, idsKey, loadAll])

  // Тихое обновление раз в 15 с — как у карточки поставки на рабочих вкладках.
  useEffect(() => {
    if (!open || !idsKey || stage === 'composition') return
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
  const allLoaded = ordered.length === supplyIds.length && supplyIds.length > 0
  const { ready, total } = fbsAssemblyReadiness(ordered)
  const percent = total ? Math.round((ready / total) * 100) : 0
  const sellerNames = [...new Set(ordered.map((one) => one.supply.seller.name))].join(', ')
  const ordersCount = ordered.reduce((sum, one) => sum + one.orders.length, 0)

  const requestClose = () => {
    onClose()
  }

  // R13: «Начать работу с поставкой» — тот же start-work, что у одноимённой
  // кнопки карточки, и только если у поставки ещё нет задания упаковки (Д6).
  // Активной бывает одна рамка: прежняя завершается без запросов (R15).
  const startWork = async (supplyId: string) => {
    const workspace = workspaces[supplyId]
    if (!workspace || startingSupplyId) return
    setError(null)
    if (!workspace.supply.packaging_task_id) {
      const generation = openGeneration.current
      setStartingSupplyId(supplyId)
      try {
        const next = await startFbsSupplyWork(token, authHeaders, supplyId)
        if (generation !== openGeneration.current) return
        writeSeq.current.set(supplyId, (writeSeq.current.get(supplyId) ?? 0) + 1)
        setWorkspaces((current) => ({ ...current, [supplyId]: next }))
      } catch (cause) {
        if (generation === openGeneration.current) {
          setError(cause instanceof Error ? fbsErrorText(cause.message) : 'Операция не выполнена.')
        }
        return
      } finally {
        if (generation === openGeneration.current) setStartingSupplyId(null)
      }
    }
    setActiveSupplyId(supplyId)
    setExpandedIds((current) => {
      const next = new Set(current)
      if (activeSupplyId && activeSupplyId !== supplyId) next.delete(activeSupplyId)
      next.add(supplyId)
      return next
    })
  }

  const finishWork = (supplyId: string) => {
    if (activeSupplyId === supplyId) setActiveSupplyId(null)
    setExpandedIds((current) => {
      const next = new Set(current)
      next.delete(supplyId)
      return next
    })
  }

  const toggleExpanded = (supplyId: string) => {
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(supplyId)) next.delete(supplyId)
      else next.add(supplyId)
      return next
    })
  }

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
    if (printWindow.closed) return
    const distinct = (values: string[]) => [...new Set(values)].join(', ')
    const earliestDeadline = ordered
      .map((one) => one.supply.nearest_deadline_at)
      .sort((a, b) => new Date(a).getTime() - new Date(b).getTime())[0]
    printWindow.document.open()
    printWindow.document.write(buildFbsPickingListPrintHtml({
      supplyName: `Сборка · ${ordered.length} ${plural(ordered.length, ['поставка', 'поставки', 'поставок'])}`,
      wbSupplyId: ordered.map((one) => one.supply.wb_supply_id).filter(Boolean).join(', ') || null,
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
    () => ordered.map((one) => ({ id: one.supply.id, sellerId: one.supply.seller.id })),
    [ordered],
  )

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : requestClose}
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
            <Stack spacing={2}>
              <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
                <Button variant="outlined" startIcon={<PrintOutlinedIcon />} onClick={() => void printPickingList()} data-testid="fbs-pick-list-print">
                  Печать листа подбора
                </Button>
              </Stack>
              <Box data-testid="fbs-pick-unified">
                <FfFbsAssemblyPick token={token} supplies={pickSupplies} />
              </Box>
            </Stack>
          ) : null}

          {allLoaded && stage === 'packing' ? (
            <Stack spacing={2} data-testid="fbs-assembly-packing">
              {ordered.map((workspace) => (
                <AssemblySupplyFrame
                  key={workspace.supply.id}
                  workspace={workspace}
                  active={activeSupplyId === workspace.supply.id}
                  expanded={activeSupplyId === workspace.supply.id || expandedIds.has(workspace.supply.id)}
                  starting={startingSupplyId === workspace.supply.id}
                  startDisabled={Boolean(startingSupplyId)}
                  onToggle={() => toggleExpanded(workspace.supply.id)}
                  onStart={() => void startWork(workspace.supply.id)}
                  onFinish={() => finishWork(workspace.supply.id)}
                >
                  {null}
                </AssemblySupplyFrame>
              ))}
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

/**
 * Рамка поставки на «Упаковке и маркировке» (R12, R13, R15): шапка
 * «Поставка … · WB № … · селлер · Склад WB … · Склад / СЦ», «Упаковано X из Y»,
 * чипы по фактам поставки и «Начать / Завершить работу с поставкой».
 * Активная рамка — обводка success.main 2px и светло-зелёная шапка, как в макете.
 */
function AssemblySupplyFrame({
  workspace,
  active,
  expanded,
  starting,
  startDisabled,
  onToggle,
  onStart,
  onFinish,
  children,
}: {
  workspace: FbsWorkspace
  active: boolean
  expanded: boolean
  starting: boolean
  startDisabled: boolean
  onToggle: () => void
  onStart: () => void
  onFinish: () => void
  children: ReactNode
}) {
  const supplyId = workspace.supply.id
  const transferred = fbsSupplyTransferred(workspace)
  return (
    <Paper
      variant="outlined"
      sx={{
        overflow: 'hidden',
        borderColor: active ? 'success.main' : 'divider',
        borderWidth: active ? 2 : 1,
      }}
      data-testid={`fbs-assembly-supply-${supplyId}`}
      data-active={active ? 'true' : 'false'}
    >
      <Box
        sx={{
          px: 2,
          py: 1.5,
          bgcolor: active ? (theme) => alpha(theme.palette.success.main, 0.12) : 'background.paper',
          borderBottom: expanded && children ? 1 : 0,
          borderColor: 'divider',
        }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
            <IconButton size="small" onClick={onToggle} aria-label="Свернуть или развернуть поставку" data-testid={`fbs-assembly-supply-toggle-${supplyId}`}>
              {expanded ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
            </IconButton>
            <Box sx={{ minWidth: 0 }}>
              {/* Без noWrap: длинная шапка переносится целиком, без многоточия (R12). */}
              <Typography variant="subtitle1" sx={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                {fbsAssemblySupplyTitle(workspace)} · {fbsSupplyRouteLabel(workspace)}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 0.25, flexWrap: 'wrap' }} useFlexGap>
                <Typography variant="body2" color="text.secondary">
                  Упаковано {workspace.progress.packed} из {workspace.progress.total}
                </Typography>
                {workspace.supply.honest_sign_skipped ? <Chip size="small" color="warning" label="Сдаём без Честного знака" /> : null}
                {transferred ? <Chip size="small" color="success" label="Передана в WB" /> : null}
              </Stack>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
            {active ? (
              <Button variant="contained" onClick={onFinish} data-testid={`fbs-assembly-supply-finish-${supplyId}`}>
                Завершить работу с поставкой
              </Button>
            ) : (
              <Button
                variant="contained"
                onClick={onStart}
                disabled={startDisabled}
                startIcon={starting ? <CircularProgress size={18} color="inherit" /> : undefined}
                data-testid={`fbs-assembly-supply-start-${supplyId}`}
              >
                Начать работу с поставкой
              </Button>
            )}
          </Stack>
        </Stack>
      </Box>
      <Collapse in={expanded}>{children}</Collapse>
    </Paper>
  )
}
