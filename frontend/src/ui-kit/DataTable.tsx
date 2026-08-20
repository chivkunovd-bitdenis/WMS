import {
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material'
import type { ReactNode } from 'react'
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
}

export function DataTable<Row>({
  columns,
  rows,
  getRowKey,
  loading = false,
  hasDiscrepancy,
  empty,
  testId,
}: Props<Row>) {
  const showEmpty = !loading && rows.length === 0

  return (
    <TableContainer component={Paper} variant="outlined" data-testid={testId}>
      {/* stickyHeader по умолчанию: на двухстах строках без липкой шапки
          оператор читает число не из того столбца (канон R-05). */}
      <Table stickyHeader size="small">
        <TableHead>
          <TableRow>
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
          <TableSkeletonBody columns={columns.length} />
        ) : (
          <TableBody>
            {rows.map((row) => (
              <TableRow
                key={getRowKey(row)}
                hover
                sx={
                  hasDiscrepancy?.(row)
                    ? { backgroundColor: 'rgba(163, 42, 32, 0.10)' }
                    : undefined
                }
              >
                {columns.map((column) => (
                  <TableCell key={column.key} align={column.align ?? 'left'}>
                    {column.render(row)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {showEmpty && empty ? (
              <TableRow>
                <TableCell colSpan={columns.length} sx={{ borderBottom: 'none' }}>
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
