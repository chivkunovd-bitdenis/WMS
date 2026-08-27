import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import { Fragment, type ReactNode } from 'react'
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
}: Props<Row>) {
  const showEmpty = !loading && rows.length === 0
  const spanWidth = columns.length + (expand ? 1 : 0)

  return (
    <TableContainer component={Paper} variant="outlined" data-testid={testId}>
      {/* stickyHeader по умолчанию: на двухстах строках без липкой шапки
          оператор читает число не из того столбца (канон R-05). */}
      <Table stickyHeader size="small">
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
        {loading ? (
          <TableSkeletonBody columns={spanWidth} />
        ) : (
          <TableBody>
            {rows.map((row) => {
              const expanded = Boolean(expand?.isExpanded(row))
              return (
                <Fragment key={getRowKey(row)}>
                  <TableRow
                    hover
                    sx={
                      hasDiscrepancy?.(row)
                        ? { backgroundColor: 'rgba(163, 42, 32, 0.10)' }
                        : undefined
                    }
                  >
                    {expand ? (
                      <TableCell padding="checkbox">
                        <IconAction
                          title={expand.label(row)}
                          onClick={() => expand.onToggle(row)}
                          testId={`${testId ?? 'table'}-expand-${getRowKey(row)}`}
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
                        sx={{ p: 0, backgroundColor: 'action.hover' }}
                        data-testid={`${testId ?? 'table'}-expanded-${getRowKey(row)}`}
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
