import { Box, LinearProgress, Paper, Stack, Typography } from '@mui/material'
import UndoOutlined from '@mui/icons-material/UndoOutlined'
import {
  ActionGroup,
  DataTable,
  EmptyState,
  IconAction,
  PrimaryAction,
  ProductCell,
  QtyCell,
  SecondaryAction,
  StatusChip,
  TextCell,
} from '../../../ui-kit'
import type { Column, StatusTone } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { stopStatus, type RouteItem, type RouteStop } from './routeRows'

// Место, которое сейчас в руках.
//
// Это главный блок экрана и единственный, где что-то снимают. В маршруте ниже
// кнопок снятия нет намеренно: снимать можно только с того места, к которому
// подошёл, и два места одновременно в руках не бывает. Одно действие — одно
// место на экране, где его делают.
//
// Внутри показан ВЕСЬ состав места, включая то, чего в отгрузке нет. Человек,
// открывший короб, видит его целиком; экран, показывающий только плановые
// строки, заставляет думать, что короб не тот.

function itemStatus(item: RouteItem): { label: string; tone: StatusTone; hint: string } {
  if (!item.inPlan) {
    return {
      label: 'Не в отгрузке',
      tone: 'neutral',
      hint: 'Этого товара нет в документе — он просто лежит здесь, брать его не надо',
    }
  }
  if (item.need === 0 && item.picked > 0) {
    return { label: 'Снято', tone: 'ok', hint: 'Отсюда взято всё, что требовалось' }
  }
  if (item.need === 0) {
    return {
      label: 'Не нужно',
      tone: 'neutral',
      hint: 'Количество по документу закрывается другими местами маршрута',
    }
  }
  return { label: 'Снять', tone: 'warn', hint: 'Эту строку ещё надо снять с этого места' }
}

export function PlaceCard({
  stop,
  canUndo,
  onTake,
  onUndo,
  onSkip,
  onDone,
}: {
  stop: RouteStop | null
  canUndo: boolean
  onTake: (item: RouteItem) => void
  onUndo: () => void
  onSkip: () => void
  onDone: () => void
}) {
  if (!stop) {
    return (
      <Paper variant="outlined" sx={{ mb: 2 }} data-testid="route-place-empty">
        <EmptyState
          title="Место не в работе"
          hint="Пикните штрихкод ячейки, палеты, короба или грузоместа — или нажмите «Взять в работу» в маршруте ниже."
        />
      </Paper>
    )
  }

  const status = stopStatus(stop)
  const done = stop.picked
  const total = stop.picked + stop.need

  const columns: Column<RouteItem>[] = [
    {
      key: 'product',
      header: 'Товар',
      render: (item) => (
        <ProductCell
          photo={<ProductPhotoThumb src={item.product.photo} alt={item.product.name} size={32} />}
          sku={item.product.sku}
        />
      ),
    },
    {
      key: 'name',
      header: 'Наименование',
      render: (item) => <TextCell value={item.product.name} />,
    },
    {
      key: 'inside',
      header: 'В чём лежит',
      render: (item) => <TextCell value={item.inside} />,
    },
    {
      key: 'need',
      header: 'Снять',
      align: 'right',
      width: 80,
      render: (item) => <QtyCell value={item.need} muted={item.need === 0} />,
    },
    {
      key: 'qty',
      header: 'Лежит',
      align: 'right',
      width: 80,
      render: (item) => <QtyCell value={Math.max(0, item.qty - item.picked)} muted />,
    },
    {
      key: 'picked',
      header: 'Снято',
      align: 'right',
      width: 80,
      render: (item) => <QtyCell value={item.picked} muted={item.picked === 0} />,
    },
    {
      key: 'status',
      header: 'Состояние',
      render: (item) => {
        const one = itemStatus(item)
        return <StatusChip label={one.label} tone={one.tone} hint={one.hint} />
      },
    },
    {
      key: 'action',
      header: '',
      align: 'right',
      render: (item) => (
        <PrimaryAction
          onClick={() => onTake(item)}
          disabledReason={
            !item.inPlan
              ? 'Этого товара нет в отгрузке'
              : item.need === 0
                ? 'По документу отсюда больше не нужно'
                : undefined
          }
          data-testid={`route-take-${item.key}`}
        >
          Снять
        </PrimaryAction>
      ),
    },
  ]

  return (
    <Box sx={{ mb: 2 }} data-testid="route-place-card">
      <Paper variant="outlined" sx={{ p: 2, mb: 1 }}>
        <Stack spacing={1.5}>
          <Stack
            direction="row"
            spacing={2}
            sx={{ alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap' }}
          >
            <Stack spacing={0.75}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography variant="h6" data-testid="route-place-standing">
                  {stop.standing}
                </Typography>
                <StatusChip label={status.label} tone={status.tone} hint={status.hint} />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {stop.cellCode ? `Ячейка ${stop.cellCode}` : 'Стоит без ячейки'} · закрывает{' '}
                {stop.lines} позиц. документа
                {stop.foreign > 0 ? ` · ещё ${stop.foreign} шт не из этой отгрузки` : ''}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
              <Stack sx={{ alignItems: 'flex-end' }}>
                <Typography
                  variant="h4"
                  sx={{ fontVariantNumeric: 'tabular-nums' }}
                  data-testid="route-place-need"
                >
                  {stop.need.toLocaleString('ru-RU')}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  штук снять здесь · снято {done.toLocaleString('ru-RU')}
                </Typography>
              </Stack>
              <IconAction
                title="Отменить последнее снятие на этом месте"
                onClick={onUndo}
                disabledReason={canUndo ? undefined : 'На этом месте ещё ничего не снимали'}
                testId="route-undo"
              >
                <UndoOutlined fontSize="small" />
              </IconAction>
            </Stack>
          </Stack>
          <LinearProgress
            variant="determinate"
            value={total === 0 ? 100 : (done / total) * 100}
            sx={{ height: 8, borderRadius: 4 }}
          />
          <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
            <ActionGroup>
              <SecondaryAction onClick={onSkip} data-testid="route-skip">
                Пропустить место
              </SecondaryAction>
              <PrimaryAction
                onClick={onDone}
                disabledReason={
                  stop.need > 0 && stop.picked === 0 ? 'Здесь ещё ничего не снято' : undefined
                }
                data-testid="route-next"
              >
                Дальше по маршруту
              </PrimaryAction>
            </ActionGroup>
          </Stack>
        </Stack>
      </Paper>

      <DataTable
        columns={columns}
        rows={stop.items}
        getRowKey={(item) => item.key}
        testId="route-place-table"
        empty={{
          title: 'Место пустое',
          hint: 'Здесь ничего не лежит — снимать нечего.',
        }}
      />
    </Box>
  )
}
