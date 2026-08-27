import { Box, Paper, Stack, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import {
  DataTable,
  EmptyState,
  IconAction,
  PrimaryAction,
  PrintAction,
  QtyCell,
  StatusChip,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import type { Placement, SortCell, SortProduct } from './sortingStub'

// Правая половина: одна ячейка, к которой оператор сейчас стоит. Раньше активная
// ячейка была строчкой подписи под полем ввода — её не видно с полутора метров,
// а именно с такого расстояния на неё и смотрят, держа товар в руках.

type CellRow = { placement: Placement; product: SortProduct }

export function SortingCellPanel({
  cells,
  activeCell,
  placements,
  products,
  carried,
  onPickCell,
  onChangeQty,
  onRemove,
  onCommit,
  onPrint,
  onCreateCell,
}: {
  cells: SortCell[]
  activeCell: SortCell | null
  placements: Placement[]
  products: SortProduct[]
  /** Товар, который сейчас тянут мышью, — плитки ячеек становятся целями. */
  carried: SortProduct | null
  onPickCell: (cellId: string) => void
  onChangeQty: (productId: string, qty: number) => void
  onRemove: (productId: string) => void
  onCommit: () => void
  onPrint: () => void
  onCreateCell: () => void
}) {
  const theme = useTheme()
  const productById = new Map(products.map((product) => [product.id, product]))
  const rows: CellRow[] = activeCell
    ? placements
        .filter((one) => one.cellId === activeCell.id)
        .map((placement) => ({ placement, product: productById.get(placement.productId)! }))
        .filter((row) => Boolean(row.product))
    : []
  const putHere = rows.reduce((sum, row) => sum + row.placement.qty, 0)

  const columns: Column<CellRow>[] = [
    {
      key: 'name',
      header: 'Положили сюда',
      render: ({ product }) => (
        <Typography variant="body2" sx={{ minHeight: 32, display: 'flex', alignItems: 'center' }}>
          {product.name}
        </Typography>
      ),
    },
    {
      key: 'qty',
      header: 'Штук',
      width: 96,
      align: 'right',
      render: ({ placement }) => <QtyCell value={placement.qty} />,
    },
    {
      key: 'actions',
      header: '',
      width: 88,
      align: 'right',
      render: ({ placement, product }) => (
        <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'flex-end' }}>
          <IconAction
            title="Убрать одну штуку"
            onClick={() => onChangeQty(product.id, placement.qty - 1)}
            testId={`sorting-minus-${product.id}`}
          >
            <Typography sx={{ fontWeight: 700, lineHeight: 1 }}>−</Typography>
          </IconAction>
          <IconAction
            title="Снять с ячейки — вернётся в «Осталось разложить»"
            onClick={() => onRemove(product.id)}
            testId={`sorting-remove-${product.id}`}
          >
            <CloseOutlined fontSize="small" />
          </IconAction>
        </Stack>
      ),
    },
  ]

  return (
    <Stack spacing={1.5}>
      {/* Плитки ячеек: и выбор без сканера, и цель для перетаскивания. */}
      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
        {cells.map((cell) => {
          const active = activeCell?.id === cell.id
          const target = carried !== null
          return (
            <Box
              key={cell.id}
              role="button"
              tabIndex={0}
              onClick={() => onPickCell(cell.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') onPickCell(cell.id)
              }}
              onDragOver={(event) => {
                if (target) event.preventDefault()
              }}
              onDrop={() => onPickCell(cell.id)}
              data-testid={`sorting-cell-${cell.id}`}
              sx={{
                px: 1.5,
                py: 0.75,
                borderRadius: 2,
                cursor: 'pointer',
                border: '1px solid',
                borderColor: active ? 'primary.main' : 'divider',
                backgroundColor: active
                  ? alpha(theme.palette.primary.main, 0.12)
                  : 'background.paper',
                outline: target && !active ? `1px dashed ${alpha(theme.palette.primary.main, 0.45)}` : 'none',
                outlineOffset: '-3px',
              }}
            >
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {cell.code}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {cell.occupied.length === 0 ? 'пусто' : `занято ${cell.occupied.length}`}
              </Typography>
            </Box>
          )
        })}
        <PrimaryAction onClick={onCreateCell} data-testid="sorting-create-cell">
          Создать ячейку
        </PrimaryAction>
      </Stack>

      {activeCell === null ? (
        <Paper variant="outlined" data-testid="sorting-no-cell">
          <EmptyState
            title="Ячейка не выбрана"
            hint="Пикните штрихкод с полки или нажмите на плитку выше. Пока ячейки нет, класть некуда."
          />
        </Paper>
      ) : (
        <Paper variant="outlined" sx={{ p: 2 }} data-testid="sorting-active-cell">
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
              <Typography variant="h5">{activeCell.code}</Typography>
              <StatusChip
                label={putHere > 0 ? `положено ${putHere} шт` : 'пока пусто'}
                tone={putHere > 0 ? 'ok' : 'neutral'}
                testId="sorting-put-here"
              />
              <Box sx={{ flexGrow: 1 }} />
              <PrintAction what="ШК ячейки" placement="row" onClick={onPrint} testId="sorting-print" />
            </Stack>

            {activeCell.occupied.length > 0 ? (
              <Typography variant="body2" color="text.secondary">
                Уже лежит: {activeCell.occupied.map((one) => `${one.name} — ${one.qty} шт`).join(', ')}
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Ячейка была пустой.
              </Typography>
            )}

            <DataTable
              testId="sorting-cell-rows"
              columns={columns}
              rows={rows}
              getRowKey={(row) => row.placement.productId}
              empty={{
                title: 'В эту ячейку пока ничего не положили',
                hint: 'Пикните товар или нажмите плюс в списке слева.',
              }}
            />

            <Stack direction="row" sx={{ justifyContent: 'flex-end' }}>
              <PrimaryAction
                onClick={onCommit}
                disabledReason={putHere === 0 ? 'В ячейку ничего не положено' : undefined}
                data-testid="sorting-commit"
              >
                Записать ячейку
              </PrimaryAction>
            </Stack>
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}
