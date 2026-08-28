import { Box, Paper, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  ActionGroup,
  DataTable,
  PrimaryAction,
  QtyCell,
  ReportMetricStrip,
  ScannerField,
  ScreenHeader,
  SecondaryAction,
  StatusChip,
  TextCell,
  WarningNotice,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { DOCUMENT, OBJECTS, PICK_CELLS, SELLER, cellRef, objRef } from '../unload-pick/pickStub'
import { PickQtyDialog } from './PickQtyDialog'
import { PlaceCard } from './PlaceCard'
import {
  CATALOG,
  DEFAULT_PLAN,
  ROUTE_STOCK,
  routePlan,
  stopKeyOf,
  stopStatus,
  type PickedMap,
  type RouteItem,
  type RouteStop,
} from './routeRows'

// Подбор на отгрузку, вариант Б: экран маршрута.
//
// Вариант А был списком товаров: строка товара, под ней перечислены места, где
// он лежит. Это верный ответ на вопрос «что снять» и никакой ответ на вопрос
// «куда идти»: человек с документом на шесть строк подходил к одной палете
// трижды, потому что трижды видел её в разных строках.
//
// Здесь единица экрана — место обхода. Сначала маршрут: к чему подойти, что там
// взять, сколько штук. Подошёл, пикнул палету — она стала местом в работе, и всё
// её содержимое видно целиком, вместе с тем, чего в отгрузке нет. Снял — числа
// уменьшились на глазах, место закрылось, к нему возвращаться не надо.
//
// Плановое количество раздаётся местам по порядку обхода (см. routePlan), и это
// главная прибавка к информативности: место, без которого план всё равно
// закроется, честно помечено «не нужно» — к нему не идут.

type PickOp = { stopKey: string; itemKey: string; qty: number }

export function UnloadPickRouteScreen({ onNote }: { onNote: (note: string) => void }) {
  const [picked, setPicked] = useState<PickedMap>({})
  const [history, setHistory] = useState<PickOp[]>([])
  const [skipped, setSkipped] = useState<string[]>([])
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [openKeys, setOpenKeys] = useState<string[]>([])
  const [scanValue, setScanValue] = useState('')
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)
  const [asking, setAsking] = useState<RouteItem | null>(null)

  const plan = routePlan(DEFAULT_PLAN, ROUTE_STOCK, OBJECTS, PICK_CELLS, picked, skipped)
  const active = plan.stops.find((stop) => stop.key === activeKey) ?? null
  const leftQty = plan.planQty - plan.pickedQty
  const shortQty = plan.shortfall.reduce((sum, one) => sum + one.qty, 0)

  function stopLabel(stop: RouteStop): string {
    return stop.cellCode ? `${stop.standing}, ячейка ${stop.cellCode}` : `${stop.standing}, без ячейки`
  }

  function take(stop: RouteStop, item: RouteItem, qty: number) {
    setPicked((current) => ({ ...current, [item.key]: (current[item.key] ?? 0) + qty }))
    setHistory((current) => [...current, { stopKey: stop.key, itemKey: item.key, qty }])
    setScanError(null)
    setScanNotice(`${item.product.sku}: снято ${qty} шт — ${item.inside.toLowerCase()}`)
    onNote(`Заглушка: ${item.product.sku}, снято ${qty} шт — ${stopLabel(stop)}`)
  }

  /**
   * Обратный ход по текущему месту.
   *
   * Списание физическое: товар уехал с полки в отгрузку. Поэтому отмена именно
   * обратный ход последнего снятия, а не правка числа: количество возвращается
   * ровно в ту строку остатка, откуда его сняли.
   */
  function undoLast() {
    if (!active) return
    const index = history.map((one) => one.stopKey).lastIndexOf(active.key)
    if (index < 0) return
    const operation = history[index]
    setPicked((current) => ({
      ...current,
      [operation.itemKey]: Math.max(0, (current[operation.itemKey] ?? 0) - operation.qty),
    }))
    setHistory((current) => current.filter((_, position) => position !== index))
    setScanNotice(`Снятие ${operation.qty} шт отменено`)
    onNote(`Заглушка: возврат ${operation.qty} шт — ${stopLabel(active)}`)
  }

  /** Следующее место, к которому надо подойти. */
  function goNext(from: string | null) {
    const next = plan.stops.find((stop) => stop.key !== from && stop.need > 0 && !stop.skipped)
    setActiveKey(next ? next.key : null)
    setScanNotice(
      next
        ? `Дальше: ${stopLabel(next)} — снять ${next.need} шт`
        : 'Мест для обхода больше нет',
    )
  }

  function skipActive() {
    if (!active) return
    setSkipped((current) => [...current, active.key])
    onNote(`Заглушка: место пропущено — ${stopLabel(active)}`)
    goNext(active.key)
  }

  function activate(stop: RouteStop) {
    setSkipped((current) => current.filter((key) => key !== stop.key))
    setActiveKey(stop.key)
    setScanError(null)
    setScanNotice(`${stopLabel(stop)} — снять ${stop.need} шт`)
  }

  function handleScan(code: string) {
    setScanValue('')
    const lower = code.toLowerCase()

    const cell = PICK_CELLS.find((one) => one.barcode === code || one.code.toLowerCase() === lower)
    if (cell) {
      const stop = plan.stops.find((one) => one.key === cellRef(cell.id))
      if (!stop) {
        setScanNotice(null)
        setScanError(`В ячейке ${cell.code} ничего из этой отгрузки не лежит`)
        return
      }
      activate(stop)
      return
    }

    const object = OBJECTS.find((one) => one.barcode === code || one.code.toLowerCase() === lower)
    if (object) {
      const key = stopKeyOf(objRef(object.id), OBJECTS, PICK_CELLS)
      const stop = key ? plan.stops.find((one) => one.key === key) : null
      if (!stop) {
        setScanNotice(null)
        setScanError(`В ${object.code} ничего из этой отгрузки не лежит`)
        return
      }
      activate(stop)
      return
    }

    const product = CATALOG.find((one) => one.barcode === code || one.sku.toLowerCase() === lower)
    if (!product) {
      setScanNotice(null)
      setScanError(`Штрихкод ${code} — ни место, ни товар этой отгрузки`)
      return
    }

    // Место уже в руках — снимаем оттуда и никуда не переезжаем. Сканер тупой,
    // решает экран (канон R-26): он плюсует единицу к той строке места, где этот
    // товар лежит и где он ещё нужен.
    if (active) {
      const item = active.items.find((one) => one.product.id === product.id && one.need > 0)
      if (item) {
        take(active, item, 1)
        return
      }
      const lying = active.items.find((one) => one.product.id === product.id)
      setScanNotice(null)
      setScanError(
        lying
          ? `${product.sku} здесь лежит, но по документу отсюда снимать не надо`
          : `${product.sku} в этом месте не лежит`,
      )
      return
    }

    // Место не выбрано: находим то, откуда этот товар положено снять первым.
    const stop = plan.stops.find((one) =>
      one.items.some((item) => item.product.id === product.id && item.need > 0),
    )
    if (!stop) {
      setScanNotice(null)
      setScanError(
        DEFAULT_PLAN.some((line) => line.productId === product.id)
          ? `${product.sku} — снимать по документу больше не надо`
          : `${product.sku} не входит в эту отгрузку`,
      )
      return
    }
    const item = stop.items.find((one) => one.product.id === product.id && one.need > 0)!
    setActiveKey(stop.key)
    take(stop, item, 1)
  }

  const columns: Column<RouteStop>[] = [
    {
      key: 'address',
      header: 'Адрес',
      render: (stop) => <TextCell value={stop.address} />,
    },
    {
      key: 'standing',
      header: 'Что стоит',
      render: (stop) => <TextCell value={stop.standing} />,
    },
    {
      key: 'lines',
      header: 'Позиций',
      align: 'right',
      width: 88,
      render: (stop) => <QtyCell value={stop.lines} muted={stop.lines === 0} />,
    },
    {
      key: 'need',
      header: 'Снять',
      align: 'right',
      width: 80,
      render: (stop) => <QtyCell value={stop.need} muted={stop.need === 0} />,
    },
    {
      key: 'picked',
      header: 'Снято',
      align: 'right',
      width: 80,
      render: (stop) => <QtyCell value={stop.picked} muted={stop.picked === 0} />,
    },
    {
      // Сколько ещё лежит на этом месте помимо отгрузки. Человек, открывший
      // короб, должен заранее знать, что там будет чужое, иначе решит, что
      // ошибся коробом, и пойдёт искать другой.
      key: 'foreign',
      header: 'Ещё лежит',
      align: 'right',
      width: 104,
      render: (stop) => <QtyCell value={stop.foreign} muted />,
    },
    {
      key: 'status',
      header: 'Состояние',
      render: (stop) => {
        const status = stopStatus(stop)
        return <StatusChip label={status.label} tone={status.tone} hint={status.hint} />
      },
    },
    {
      key: 'action',
      header: '',
      align: 'right',
      render: (stop) => (
        <PrimaryAction
          onClick={() => activate(stop)}
          disabledReason={
            stop.key === activeKey
              ? 'Это место уже в работе'
              : stop.need === 0 && !stop.skipped
                ? 'Сюда идти не нужно — количество закрывают другие места'
                : undefined
          }
          data-testid={`route-open-${stop.key}`}
        >
          {stop.skipped ? 'Вернуть в маршрут' : 'Взять в работу'}
        </PrimaryAction>
      ),
    },
  ]

  return (
    <Box data-testid="unload-pick-route-screen">
      <ScreenHeader
        title="Подбор на отгрузку"
        purpose={`${DOCUMENT}. Продавец ${SELLER}. Маршрут обхода: к чему подойти и что с этого снять.`}
      />

      <ReportMetricStrip
        testId="route-metrics"
        items={[
          {
            key: 'lines',
            label: 'Позиции документа',
            value: plan.linesDone,
            unit: `из ${plan.linesTotal}`,
          },
          { key: 'qty', label: 'Снято штук', value: plan.pickedQty, unit: `из ${plan.planQty}` },
          {
            key: 'stops',
            label: 'Мест обойти',
            value: plan.stopsLeft,
            unit: `из ${plan.stopsTotal}`,
          },
          { key: 'short', label: 'Нечем закрыть', value: shortQty, unit: 'шт' },
        ]}
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <ScannerField
          value={scanValue}
          onChange={(value) => {
            setScanValue(value)
            setScanError(null)
          }}
          onScan={handleScan}
          expects={active ? 'товар, который снимаете' : 'место или товар'}
          error={scanError}
          notice={scanNotice}
          testId="route-scan"
        />
      </Paper>

      {plan.shortfall.length > 0 ? (
        <WarningNotice testId="route-shortfall">
          Нечем закрыть:{' '}
          {plan.shortfall
            .map((one) => `${one.product.name} (${one.product.sku}) — ${one.qty} шт`)
            .join('; ')}
          . Столько не даёт ни одно место маршрута: этого нет на складе либо место пропущено.
        </WarningNotice>
      ) : null}

      <PlaceCard
        stop={active}
        canUndo={Boolean(active && history.some((one) => one.stopKey === active.key))}
        onTake={(item) => setAsking(item)}
        onUndo={undoLast}
        onSkip={skipActive}
        onDone={() => goNext(active?.key ?? null)}
      />

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        Маршрут обхода
      </Typography>
      <DataTable
        columns={columns}
        rows={plan.stops}
        getRowKey={(stop) => stop.key}
        testId="route-table"
        highlightedKey={activeKey}
        expand={{
          isExpanded: (stop) => openKeys.includes(stop.key),
          label: (stop) => `Показать, что лежит: ${stop.standing}`,
          onToggle: (stop) =>
            setOpenKeys((current) =>
              current.includes(stop.key)
                ? current.filter((key) => key !== stop.key)
                : [...current, stop.key],
            ),
          render: (stop) => (
            <Stack spacing={0.5} sx={{ px: 2, py: 1.5 }}>
              {stop.items.map((item) => (
                <Typography
                  key={item.key}
                  variant="body2"
                  color={item.need > 0 ? 'text.primary' : 'text.secondary'}
                >
                  {item.inside} · {item.product.name} ({item.product.sku}) — лежит {item.qty} шт
                  {item.need > 0 ? `, снять ${item.need} шт` : ''}
                  {!item.inPlan ? ', не в этой отгрузке' : ''}
                </Typography>
              ))}
            </Stack>
          ),
        }}
        empty={{
          title: 'Обходить нечего',
          hint: 'Ни один товар отгрузки не лежит на складе — подбирать нечего.',
        }}
      />

      <Stack direction="row" sx={{ mt: 2, justifyContent: 'flex-end' }}>
        <ActionGroup>
          <SecondaryAction
            onClick={() => onNote('Заглушка: подбор отложен')}
            data-testid="route-pause"
          >
            Отложить
          </SecondaryAction>
          <PrimaryAction
            onClick={() => onNote('Заглушка: подбор завершён')}
            disabledReason={leftQty > 0 ? 'Собран не весь план отгрузки' : undefined}
            data-testid="route-complete"
          >
            Завершить подбор
          </PrimaryAction>
        </ActionGroup>
      </Stack>

      <PickQtyDialog
        open={asking !== null}
        item={asking}
        placeLabel={active ? stopLabel(active) : ''}
        onClose={() => setAsking(null)}
        onConfirm={(qty) => {
          if (active && asking) take(active, asking, qty)
          setAsking(null)
        }}
      />
    </Box>
  )
}
