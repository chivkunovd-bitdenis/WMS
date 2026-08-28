import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import ExpandMore from '@mui/icons-material/ExpandMore'
import { Fragment, useState, type DragEvent, type ReactNode } from 'react'
import { IconAction } from './Actions'
import { EmptyState, TableSkeletonBody } from './States'

// Единственная таблица системы. Всё, что раньше собиралось руками на 33 экранах,
// живёт здесь одним экземпляром — поэтому «разъехалось на одном экране» больше
// не бывает: разъехаться может только у всех сразу, и это видно немедленно.
export type Column<Row> = {
  key: string
  header: ReactNode
  // Канон R-09: ширина фиксируется, чтобы таблица не прыгала между экранами и состояниями.
  width?: number
  // Канон R-08: числа вправо.
  align?: 'left' | 'right' | 'center'
  render: (row: Row) => ReactNode
}

/**
 * Перетаскивание строк — один механизм на всю систему.
 *
 * Складская правда переезжает между ячейками, коробами и палетами, и оператор
 * делает это рукой: тянет строку и отпускает на другой. Если бы каждый экран
 * писал свой drag, они бы выглядели по-разному и по-разному врали о том, куда
 * можно положить. Поэтому подсветка целей и запрет неверных целей живут здесь,
 * а экран отвечает только на два вопроса: что можно взять и куда это ляжет.
 *
 * Сам перенос таблица не выполняет — она сообщает о нём экрану. Количество,
 * подтверждение и запись в журнал решает экран: таблица не знает склада.
 */
export type RowDrag<Row> = {
  canDrag: (row: Row) => boolean
  canDrop: (row: Row) => boolean
  onDragStart: (row: Row) => void
  onDragEnd: () => void
  onDrop: (row: Row) => void
  /** Что-то несут прямо сейчас: цели подсвечиваются только во время переноса. */
  active: boolean
}

type Props<Row> = {
  columns: Column<Row>[]
  rows: Row[]
  getRowKey: (row: Row) => string | number
  loading?: boolean
  // Канон R-11: единственный разрешённый цвет строки — расхождение по количеству.
  // Другого способа покрасить строку в этом компоненте нет намеренно.
  hasDiscrepancy?: (row: Row) => boolean
  empty?: { title: string; hint?: string; action?: ReactNode }
  testId?: string
  /**
   * Скрыть шапку.
   *
   * Нужно списку из одной колонки, который служит группировкой: там шапка
   * повторяет очевидное, а рядом с шапкой раскрытой внутренней таблицы даёт
   * две одинаковые полосы подряд и читается как таблица в таблице.
   */
  hideHeader?: boolean
  /**
   * Раскрытие строки под собой.
   *
   * Второй таблице с собственной шапкой под основной таблицей взяться неоткуда:
   * оператор читает подробности там же, где выбрал строку, а не в оторванной
   * секции внизу экрана. Состояние держит экран — раскрытие обычно тянет данные.
   */
  expand?: {
    isExpanded: (row: Row) => boolean
    onToggle: (row: Row) => void
    render: (row: Row) => ReactNode
    /** Доступное имя стрелки: «флажок» без имени программе чтения бесполезен. */
    label: (row: Row) => string
  }
  /**
   * Жёсткая раскладка колонок.
   *
   * По умолчанию браузер меряет таблицу по содержимому, и колонка с длинным
   * названием растягивает её шире панели — панель приходится скроллить вбок.
   * Лечить это ограничением ширины текста нельзя: тогда буквы обрезаются даже
   * там, где место есть. С жёсткой раскладкой колонки получают заявленную
   * ширину, колонка без ширины забирает остаток, и текст обрезается ровно по
   * реальному краю, а не по выдуманному пределу.
   */
  fixedLayout?: boolean
  /** Перетаскивание строк (см. RowDrag). */
  drag?: RowDrag<Row>
  /**
   * Строка, которую только что нашли — сканером или поиском.
   *
   * Нужна именно подсветка, а не выделение чекбоксом: оператор пикает короб,
   * чтобы глазами найти его в длинном списке, а не чтобы что-то с ним выбрать.
   * Ключ строки уезжает в атрибут data-row-key, чтобы экран мог прокрутить к ней.
   */
  highlightedKey?: string | number | null
  /**
   * Строка доделана: работа по ней закрыта и возвращаться не нужно.
   *
   * Пара к `hasDiscrepancy`: тот красит красным то, что требует внимания, этот —
   * зелёным то, что внимания больше не требует. Оператор ведёт глазом по столбцу
   * и видит, где ещё работа, не читая чисел.
   */
  isComplete?: (row: Row) => boolean
}

export function DataTable<Row>({
  columns,
  rows,
  getRowKey,
  loading = false,
  hasDiscrepancy,
  empty,
  testId,
  expand,
  drag,
  fixedLayout = false,
  highlightedKey = null,
  hideHeader = false,
  isComplete,
}: Props<Row>) {
  const theme = useTheme()
  const showEmpty = !loading && rows.length === 0
  const spanWidth = columns.length + (expand ? 1 : 0)
  const [carriedKey, setCarriedKey] = useState<string | number | null>(null)
  const [overKey, setOverKey] = useState<string | number | null>(null)

  function dragSx(row: Row, key: string | number) {
    if (!drag) return null
    const carried = carriedKey === key
    const target = drag.active && !carried && drag.canDrop(row)
    const over = target && overKey === key
    return {
      ...(drag.canDrag(row) ? { cursor: 'grab' } : null),
      // Взятую строку видно, что она в руке, но она не исчезает: оператор должен
      // помнить, откуда тянет, пока ищет глазами цель.
      ...(carried ? { opacity: 0.45 } : null),
      // Цели обведены, а не залиты: заливка строки в системе означает ровно одно —
      // расхождение по количеству (канон R-11), и занимать её под подсказку нельзя.
      ...(target
        ? {
            outline: `1px dashed ${alpha(theme.palette.primary.main, 0.45)}`,
            outlineOffset: '-2px',
          }
        : null),
      ...(over
        ? {
            outline: `2px solid ${theme.palette.primary.main}`,
            backgroundColor: alpha(theme.palette.primary.main, 0.07),
          }
        : null),
    }
  }

  return (
    <TableContainer component={Paper} variant="outlined" data-testid={testId}>
      {/* stickyHeader по умолчанию: на двухстах строках без липкой шапки
          оператор читает число не из того столбца (канон R-05). */}
      <Table stickyHeader size="small" sx={fixedLayout ? { tableLayout: 'fixed' } : undefined}>
        {hideHeader ? null : (
        <TableHead>
          <TableRow>
            {expand ? <TableCell width={56} sx={{ whiteSpace: 'nowrap' }} /> : null}
            {columns.map((column) => (
              <TableCell
                key={column.key}
                align={column.align ?? 'left'}
                width={column.width}
                sx={{ whiteSpace: 'nowrap' }}
              >
                {column.header}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        )}
        {loading ? (
          <TableSkeletonBody columns={spanWidth} />
        ) : (
          <TableBody>
            {rows.map((row) => {
              const rowKey = getRowKey(row)
              const expanded = Boolean(expand?.isExpanded(row))
              const draggable = Boolean(drag?.canDrag(row))
              const droppable = Boolean(drag?.active && carriedKey !== rowKey && drag.canDrop(row))
              return (
                <Fragment key={rowKey}>
                  <TableRow
                    hover
                    data-row-key={rowKey}
                    draggable={draggable || undefined}
                    data-drop-target={droppable ? 'true' : undefined}
                    onDragStart={
                      draggable && drag
                        ? (event: DragEvent<HTMLTableRowElement>) => {
                            event.dataTransfer.effectAllowed = 'move'
                            // Пустой dataTransfer в Firefox отменяет перетаскивание молча,
                            // поэтому кладём ключ строки — он же полезен при отладке.
                            event.dataTransfer.setData('text/plain', String(rowKey))
                            setCarriedKey(rowKey)
                            drag.onDragStart(row)
                          }
                        : undefined
                    }
                    onDragEnd={
                      draggable && drag
                        ? () => {
                            setCarriedKey(null)
                            setOverKey(null)
                            drag.onDragEnd()
                          }
                        : undefined
                    }
                    onDragOver={
                      droppable
                        ? (event: DragEvent<HTMLTableRowElement>) => {
                            event.preventDefault()
                            event.dataTransfer.dropEffect = 'move'
                            setOverKey(rowKey)
                          }
                        : undefined
                    }
                    onDragLeave={
                      droppable
                        ? (event: DragEvent<HTMLTableRowElement>) => {
                            // Переход на вложенный элемент внутри той же строки тоже
                            // считается уходом — без этой проверки подсветка мигает.
                            const next = event.relatedTarget as Node | null
                            if (next && event.currentTarget.contains(next)) return
                            setOverKey((current) => (current === rowKey ? null : current))
                          }
                        : undefined
                    }
                    onDrop={
                      droppable && drag
                        ? (event: DragEvent<HTMLTableRowElement>) => {
                            event.preventDefault()
                            setOverKey(null)
                            drag.onDrop(row)
                          }
                        : undefined
                    }
                    sx={{
                      ...(hasDiscrepancy?.(row)
                        ? { backgroundColor: 'rgba(163, 42, 32, 0.10)' }
                        : null),
                      ...(isComplete?.(row)
                        ? { backgroundColor: alpha(theme.palette.success.main, 0.12) }
                        : null),
                      ...(highlightedKey === rowKey
                        ? {
                            outline: `2px solid ${theme.palette.primary.main}`,
                            outlineOffset: '-2px',
                            backgroundColor: alpha(theme.palette.primary.main, 0.09),
                          }
                        : null),
                      ...dragSx(row, rowKey),
                    }}
                  >
                    {expand ? (
                      <TableCell padding="checkbox">
                        <IconAction
                          title={expand.label(row)}
                          onClick={() => expand.onToggle(row)}
                          testId={`${testId ?? 'table'}-expand-${rowKey}`}
                        >
                          <ExpandMore
                            fontSize="small"
                            sx={{
                              transition: 'transform 120ms',
                              transform: expanded ? 'rotate(180deg)' : 'none',
                            }}
                          />
                        </IconAction>
                      </TableCell>
                    ) : null}
                    {columns.map((column) => (
                      <TableCell key={column.key} align={column.align ?? 'left'}>
                        {column.render(row)}
                      </TableCell>
                    ))}
                  </TableRow>
                  {expanded && expand ? (
                    <TableRow>
                      <TableCell
                        colSpan={spanWidth}
                        sx={{ p: 0, borderLeft: 3, borderLeftColor: 'primary.main' }}
                        data-testid={`${testId ?? 'table'}-expanded-${rowKey}`}
                      >
                        {expand.render(row)}
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              )
            })}
            {showEmpty && empty ? (
              <TableRow>
                <TableCell colSpan={spanWidth} sx={{ borderBottom: 'none' }}>
                  <EmptyState title={empty.title} hint={empty.hint} action={empty.action} />
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        )}
      </Table>
    </TableContainer>
  )
}
