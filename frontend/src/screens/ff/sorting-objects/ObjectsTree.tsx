import { Box, Stack, Tooltip, Typography } from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import AddOutlined from '@mui/icons-material/AddOutlined'
import ArrowUpwardOutlined from '@mui/icons-material/ArrowUpwardOutlined'
import RemoveOutlined from '@mui/icons-material/RemoveOutlined'
import DragIndicator from '@mui/icons-material/DragIndicator'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import { DataTable, IconAction, PrintAction, QtyCell, StatusChip } from '../../../ui-kit'
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
const INDENT_STEP_COMPACT = 14
const ROW_HEIGHT = 30
// Направляющая вложенности — единственная линия, которую мы рисуем сами.
// Берём цвет разделителя темы, чтобы она была ровно такой же силы, как границы
// строк, и не читалась как ещё один смысл.
const GUIDE = 'rgba(15, 23, 42, 0.11)'

/**
 * Товар внутри закрытой тары нельзя переложить одним движением — сначала его
 * надо вынуть. Это не придирка интерфейса, а порядок работы руками: короб и
 * грузоместо закрыты, и «переложить из закрытого короба сразу на палету» на
 * складе не происходит. Поэтому у такой строки нет ни плюса, ни возможности
 * утащить её мышкой — доступно только «вынуть».
 *
 * С палеты брать напрямую можно: там вещи лежат открыто, ничего не вскрывают.
 */
function insideClosed(row: ObjectRow, objects: WarehouseObject[]): boolean {
  const holder = row.kind === 'object' ? row.object.holder : row.line.holder
  if (row.kind !== 'goods' || !holder || !holder.startsWith('obj:')) return false
  const host = objects.find((one) => objRef(one.id) === holder)
  return host?.kind === 'box' || host?.kind === 'cargo_place'
}

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
  onMinus,
  onPrint,
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
  /** Снять с ячейки целиком — обратный ход к «поставить». */
  onMinus: (row: ObjectRow) => void
  onPrint: (row: ObjectRow) => void
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
      width: 88,
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

  const barcodeColumn: Column<ObjectRow> = {
      key: 'barcode',
      header: 'ШК',
      width: 134,
      render: (row) => (
        <Typography
          variant="body2"
          sx={{
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontSize: 12.5,
            color: 'text.secondary',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {row.kind === 'object' ? row.object.barcode : row.barcode}
        </Typography>
      ),
    }

  const hasSize = rows.some((row) => row.kind === 'goods' && Boolean(row.size))

  const sizeColumn: Column<ObjectRow> = {
    key: 'size',
    header: 'Размер',
    width: 72,
    render: (row) =>
      row.kind === 'goods' && row.size ? (
        <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>
          {row.size}
        </Typography>
      ) : null,
  }

  const columns: Column<ObjectRow>[] = [
    {
      key: 'what',
      header: 'Содержимое',
      render: (row) => (
        <Stack
          direction="row"
          spacing={0.5}
          sx={{
            alignItems: 'center',
            minHeight: ROW_HEIGHT,
            pl: `${row.depth * (compact ? INDENT_STEP_COMPACT : INDENT_STEP)}px`,
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
              .map((_, level) => `${level * (compact ? INDENT_STEP_COMPACT : INDENT_STEP) + 12}px 0`)
              .join(', '),
          }}
        >
          <Box
            sx={{
              width: row.kind === 'object' ? 22 : 0,
              display: 'flex',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
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
          {/* Ручка есть только там, где строку действительно можно взять.
              Нарисованная ручка у строки, которая не тащится, — прямой обман:
              оператор тянет, ничего не происходит, и он решает, что сломалось. */}
          <Box sx={{ width: 16, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
            {insideClosed(row, objects) ? null : (
              <Tooltip title="Можно перетащить в другой объект или на ячейку">
                <DragIndicator sx={{ color: 'text.disabled', fontSize: 16 }} />
              </Tooltip>
            )}
          </Box>
          <Box sx={{ width: 22, display: 'flex', justifyContent: 'center', alignItems: 'center', flexShrink: 0 }}>
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
          <Stack sx={{ minWidth: 0, flexGrow: 1, flexBasis: 0 }}>
            <Tooltip title={row.kind === 'object' ? objectTitle(row.object) : row.name}>
              <Typography
                variant="body2"
                sx={{
                  fontWeight: row.kind === 'object' ? 600 : 400,
                  // Перенос по словам: длинное название уходит на вторую строку
                  // целыми словами, а не рассыпается по буквам в столбик.
                  whiteSpace: 'normal',
                  overflowWrap: 'break-word',
                  wordBreak: 'normal',
                }}
              >
                {row.kind === 'object' ? objectTitle(row.object) : row.name}
              </Typography>
            </Tooltip>
            {row.kind === 'object' ? (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
              >
                {row.inside === 0 ? 'пусто' : `внутри ${row.inside}`}
              </Typography>
            ) : null}
          </Stack>
        </Stack>
      ),
    },
    ...(compact ? [] : [alreadyColumn]),
    // Размер и ШК — только в большой таблице. Компактное дерево живёт в узкой
    // приставке справа (панель 286 px), а ширины колонок в нём фиксированы:
    // размер 72 + ШК 134 + штук 56 + действия 92 = 354 px. Таблица не влезала,
    // и «Содержимое» схлопывалось в НОЛЬ пикселей — название товара сыпалось по
    // одной букве в столбик, а шапки налезали друг на друга. И размер, и ШК
    // видны в главной таблице слева; в панели ячейки важно только что стоит и
    // сколько.
    ...(hasSize && !compact ? [sizeColumn] : []),
    ...(compact ? [] : [barcodeColumn]),
    {
      key: 'qty',
      header: 'Штук',
      width: 56,
      align: 'right',
      render: (row) => <QtyCell value={row.qty} muted={row.qty === 0} />,
    },
    {
      key: 'actions',
      header: '',
      width: compact ? 92 : 88,
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
        const printable =
          row.kind === 'object'
            ? row.object.kind === 'pallet'
              ? ('ШК палеты' as const)
              : row.object.kind === 'box'
                ? ('ШК короба' as const)
                : ('ШК грузоместа' as const)
            : // Печать ШК товара из сортировки: раньше жила на прежнем экране
              // раскладки, а при переходе на раскладку объектами потерялась.
              ('ШК товара' as const)
        return (
          <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'flex-end' }}>
            {printable ? (
              <PrintAction
                what={printable}
                placement="row"
                onClick={() => onPrint(row)}
                testId={`${testId}-print-${row.key}`}
              />
            ) : null}
            {/* Снять с ячейки можно всё, что на ней стоит: и товар, и короб, и
                палету с грузоместом — целиком, вместе с содержимым. Снимают
                полку, а не по штуке: по штуке это уже пересчёт, а не снятие. */}
            {compact && holder && holder.startsWith('cell:') ? (
              <IconAction
                title="Снять с ячейки"
                onClick={() => onMinus(row)}
                testId={`${testId}-minus-${row.key}`}
              >
                <RemoveOutlined fontSize="small" />
              </IconAction>
            ) : null}
            {host ? (
              <IconAction
                title={`Вынуть из ${host.kind === 'pallet' ? 'палеты' : host.kind === 'box' ? 'короба' : 'грузоместа'}`}
                onClick={() => onTakeOut(row)}
                testId={`${testId}-out-${row.key}`}
              >
                <ArrowUpwardOutlined fontSize="small" />
              </IconAction>
            ) : null}
            {compact ? null : (
              <IconAction
                title="Положить в место"
                onClick={() => onPlace(row)}
                disabledReason={
                  insideClosed(row, objects) ? 'Сначала вытащите товар из тары' : undefined
                }
                testId={`${testId}-place-${row.key}`}
              >
                <AddOutlined fontSize="small" />
              </IconAction>
            )}
          </Stack>
        )
      },
    },
  ]

  return (
    // Отступы внутри ячеек поджаты именно здесь. По умолчанию их 16 слева и
    // справа, на шести колонках это почти двести пикселей — больше, чем занимает
    // само название товара. Для плотного дерева это непозволительная роскошь.
    <Box sx={{ '& .MuiTableCell-root': { pl: 1, pr: 1 } }}>
    <DataTable
      testId={testId}
      columns={columns}
      rows={rows}
      getRowKey={(row) => row.key}
      fixedLayout={compact}
      drag={{
        active: carried !== null,
        canDrag: (row) => !insideClosed(row, objects),
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
    </Box>
  )
}
