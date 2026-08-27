import { Box, Stack, Tooltip, Typography } from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import AddOutlined from '@mui/icons-material/AddOutlined'
import ArrowUpwardOutlined from '@mui/icons-material/ArrowUpwardOutlined'
import DragIndicator from '@mui/icons-material/DragIndicator'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import { DataTable, IconAction, QtyCell, StatusChip } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { objRef, type Holder, type WarehouseObject } from './objectsStub'
import { canPut, objectTitle, type Carried, type ObjectRow } from './objectsRows'

// Одна таблица на весь экран. Вложенность видна отступом, где стоит объект —
// колонкой, а не второй таблицей: две таблицы с двумя шапками читаются как два
// разных отчёта.
//
// Цвета здесь намеренно почти нет. Это складской инструмент: значок отличает
// палету от короба формой, а не цветом, и единственное, что имеет право быть
// заметным, — то, что требует действия.

const INDENT_STEP = 20
const ROW_HEIGHT = 30
// Направляющая вложенности — единственная линия, которую мы рисуем сами.
// Берём цвет разделителя темы, чтобы она была ровно такой же силы, как границы
// строк, и не читалась как ещё один смысл.
const GUIDE = 'rgba(15, 23, 42, 0.11)'
// Ширина названия ограничена намеренно: колонка с автоширинои растягивает
// таблицу шире панели, и её приходится скроллить вбок. Полное значение всегда
// лежит под подсказкой (канон R-02).
const NAME_WIDTH = 200

export function ObjectsTree({
  rows,
  objects,
  carried,
  testId,
  empty,
  onToggle,
  onPlace,
  onDragStart,
  onDragEnd,
  onDropOn,
  onTakeOut,
  onPickCell,
  compact = false,
}: {
  rows: ObjectRow[]
  objects: WarehouseObject[]
  carried: Carried | null
  onToggle: (objectId: string) => void
  onPlace: (row: ObjectRow) => void
  onDragStart: (row: ObjectRow) => void
  onDragEnd: () => void
  onDropOn: (target: Holder) => void
  onTakeOut: (row: ObjectRow) => void
  onPickCell: (cellId: string) => void
  /**
   * Узкий вид для панели ячейки: без колонки «уже лежит».
   * Для того, что уже стоит на полке, подсказка «а ещё этот товар лежит вон
   * там» — не подсказка, а шум, и она же съедала всю ширину у названия.
   */
  compact?: boolean
  testId: string
  empty: { title: string; hint?: string }
}) {
  const alreadyColumn: Column<ObjectRow> = {
      key: 'already',
      header: 'Уже лежит',
      width: 128,
      render: (row) => {
        if (row.kind !== 'goods') return null
        if (row.alreadyAt.length === 0) {
          return (
            <Typography variant="body2" color="text.secondary">
              новый
            </Typography>
          )
        }
        return (
          <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
            {row.alreadyAt.map((place) => (
              <Box
                key={place.cellId}
                onClick={() => onPickCell(place.cellId)}
                sx={{ cursor: 'pointer' }}
                data-testid={`objects-already-${place.cellId}`}
              >
                <StatusChip
                  label={`${place.code} · ${place.qty}`}
                  tone="neutral"
                  hint={`Этот товар уже лежит в ${place.code} — ${place.qty} шт`}
                />
              </Box>
            ))}
          </Stack>
        )
      },
    }

  const columns: Column<ObjectRow>[] = [
    {
      key: 'what',
      header: 'Содержимое',
      render: (row) => (
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: 'center',
            minHeight: ROW_HEIGHT,
            pl: `${row.depth * INDENT_STEP}px`,
            // Направляющие вложенности вместо голого отступа: на третьем уровне
            // глаз перестаёт понимать, чьё это содержимое, и линия отвечает на
            // это без единого лишнего слова и без единого лишнего цвета.
            backgroundImage:
              row.depth === 0
                ? 'none'
                : Array.from({ length: row.depth })
                    .map(() => `linear-gradient(to bottom, ${GUIDE} 0 100%)`)
                    .join(', '),
            backgroundRepeat: 'no-repeat',
            backgroundSize: Array.from({ length: row.depth })
              .map(() => '1px 100%')
              .join(', '),
            backgroundPosition: Array.from({ length: row.depth })
              .map((_, level) => `${level * INDENT_STEP + 14}px 0`)
              .join(', '),
          }}
        >
          <Box sx={{ width: 26, display: 'flex', justifyContent: 'center' }}>
            {row.kind === 'object' && row.expandable ? (
              <IconAction
                title={row.expanded ? `Свернуть ${objectTitle(row.object)}` : `Раскрыть ${objectTitle(row.object)}`}
                onClick={() => onToggle(row.object.id)}
                testId={`${testId}-toggle-${row.object.id}`}
              >
                <ExpandMore
                  fontSize="small"
                  sx={{ transition: 'transform 120ms', transform: row.expanded ? 'rotate(180deg)' : 'none' }}
                />
              </IconAction>
            ) : null}
          </Box>
          <Tooltip title="Можно перетащить в другой объект или на ячейку">
            <DragIndicator fontSize="small" sx={{ color: 'text.disabled' }} />
          </Tooltip>
          <Box sx={{ width: 26, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            {row.kind === 'object' ? (
              row.object.kind === 'pallet' ? (
                <LayersOutlined fontSize="small" sx={{ color: 'text.secondary' }} />
              ) : row.object.kind === 'box' ? (
                <Inventory2Outlined fontSize="small" sx={{ color: 'text.secondary' }} />
              ) : (
                <WidgetsOutlined fontSize="small" sx={{ color: 'text.secondary' }} />
              )
            ) : (
              <ProductPhotoThumb src={row.photo} alt={row.name} size={24} />
            )}
          </Box>
          <Stack sx={{ minWidth: 0 }}>
            <Tooltip title={row.kind === 'object' ? objectTitle(row.object) : row.name}>
              <Typography
                variant="body2"
                sx={{
                  fontWeight: row.kind === 'object' ? 600 : 400,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: NAME_WIDTH,
                }}
              >
                {row.kind === 'object' ? objectTitle(row.object) : row.name}
              </Typography>
            </Tooltip>
            {/* Селлер, состав и штрихкод — подписью, а не своими колонками: в
                узкой панели каждая лишняя колонка отнимает у названия товара то,
                ради чего в строку и смотрят, и в какой-то момент от названия не
                остаётся ничего. */}
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: NAME_WIDTH,
              }}
            >
              {row.kind === 'object'
                ? `${row.inside === 0 ? 'пусто' : `внутри ${row.inside}`} · ${row.object.barcode}`
                : `${row.seller} · ${row.barcode}`}
            </Typography>
          </Stack>
        </Stack>
      ),
    },
    ...(compact ? [] : [alreadyColumn]),
    {
      key: 'qty',
      header: 'Штук',
      width: 76,
      align: 'right',
      render: (row) => <QtyCell value={row.qty} muted={row.qty === 0} />,
    },
    {
      key: 'actions',
      header: '',
      width: 84,
      align: 'right',
      render: (row) => {
        const holder = row.kind === 'object' ? row.object.holder : row.line.holder
        // Кнопка «вынуть» есть только у того, что лежит внутри короба или палеты:
        // у строки на полке вынимать не из чего, и серая кнопка «на всякий
        // случай» только заставляет проверять, работает она сейчас или нет.
        const host =
          holder && holder.startsWith('obj:')
            ? objects.find((one) => objRef(one.id) === holder)
            : undefined
        return (
          <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'flex-end' }}>
            {host ? (
              <IconAction
                title={`Вынуть из ${host.kind === 'pallet' ? 'палеты' : host.kind === 'box' ? 'короба' : 'грузоместа'}`}
                onClick={() => onTakeOut(row)}
                testId={`${testId}-out-${row.key}`}
              >
                <ArrowUpwardOutlined fontSize="small" />
              </IconAction>
            ) : null}
            <IconAction
              title="Положить в место"
              onClick={() => onPlace(row)}
              testId={`${testId}-place-${row.key}`}
            >
              <AddOutlined fontSize="small" />
            </IconAction>
          </Stack>
        )
      },
    },
  ]

  return (
    <DataTable
      testId={testId}
      columns={columns}
      rows={rows}
      getRowKey={(row) => row.key}
      drag={{
        active: carried !== null,
        canDrag: () => true,
        canDrop: (row) =>
          row.kind === 'object' && carried !== null && canPut(carried, objRef(row.object.id), objects),
        onDragStart,
        onDragEnd,
        onDrop: (row) => {
          if (row.kind === 'object') onDropOn(objRef(row.object.id))
        },
      }}
      empty={empty}
    />
  )
}
