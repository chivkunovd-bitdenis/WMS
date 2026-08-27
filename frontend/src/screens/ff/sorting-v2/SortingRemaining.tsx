import { Box, LinearProgress, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import { DataTable, IconAction, QtyCell, StatusChip } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import AddOutlined from '@mui/icons-material/AddOutlined'
import type { Placement, SortCell, SortProduct } from './sortingStub'
import { placedFor, remainingFor } from './sortingStub'

// Левая половина: что осталось разложить. Список тает по мере работы — это
// единственный ответ на вопрос «мне ещё долго», который оператор задаёт себе
// каждые пять минут. Сегодня такого ответа на экране нет вовсе.

export type RemainingRow = {
  product: SortProduct
  remaining: number
  placed: number
}

export function SortingRemaining({
  products,
  placements,
  activeCell,
  summary,
  footer,
  activeWarehouseId,
  onPlaceAll,
  onPickCell,
  onDragProduct,
  onDragEnd,
}: {
  products: SortProduct[]
  placements: Placement[]
  activeCell: SortCell | null
  /** Итоги по всей приёмке, когда в таблице показана одна страница из многих. */
  summary?: { left: number; total: number }
  footer?: ReactNode
  /** Чтобы отличить подсказку «лежит здесь» от «лежит на другом складе». */
  activeWarehouseId?: string
  onPlaceAll: (product: SortProduct) => void
  onPickCell: (cellId: string) => void
  onDragProduct: (product: SortProduct) => void
  onDragEnd: () => void
}) {
  const rows: RemainingRow[] = products.map((product) => ({
    product,
    remaining: remainingFor(product, placements),
    placed: placedFor(placements, product.id),
  }))
  const left = summary ? summary.left : rows.reduce((sum, row) => sum + row.remaining, 0)
  const total = summary ? summary.total : products.reduce((sum, product) => sum + product.accepted, 0)
  const done = total - left

  const columns: Column<RemainingRow>[] = [
    {
      key: 'product',
      header: 'Товар',
      render: ({ product, remaining }) => (
        <Stack
          direction="row"
          spacing={1.25}
          sx={{ alignItems: 'center', minHeight: 44, opacity: remaining === 0 ? 0.45 : 1 }}
          draggable={remaining > 0}
          onDragStart={(event) => {
            event.dataTransfer.effectAllowed = 'move'
            event.dataTransfer.setData('text/plain', product.id)
            onDragProduct(product)
          }}
          onDragEnd={onDragEnd}
        >
          <ProductPhotoThumb src={product.photo} alt={product.name} size={34} />
          <Stack sx={{ minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
              {product.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {product.seller} · {product.source.label}
            </Typography>
          </Stack>
        </Stack>
      ),
    },
    {
      key: 'already',
      header: 'Уже лежит',
      width: 168,
      render: ({ product }) =>
        product.alreadyAt.length === 0 ? (
          // Значком, а не фразой: фраза переносилась на три строки и делала эти
          // строки таблицы выше соседних — таблица переставала читаться столбцом.
          <StatusChip
            label="новый"
            tone="neutral"
            hint="Этого товара на складе ещё нет — кладите куда удобно"
          />
        ) : (
          <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
            {product.alreadyAt.map((place) => {
              // Чужой склад — не подсказка, а предупреждение: положить туда
              // отсюда нельзя, и молча красить это в «зелёное, жми сюда» нельзя.
              const elsewhere =
                Boolean(activeWarehouseId) &&
                Boolean(place.warehouseId) &&
                place.warehouseId !== activeWarehouseId
              return (
                <Box
                  key={place.cellId}
                  onClick={() => onPickCell(place.cellId)}
                  sx={{ cursor: 'pointer' }}
                  data-testid={`sorting-already-${place.cellId}`}
                >
                  <StatusChip
                    label={
                      elsewhere ? `${place.warehouseName} · ${place.code}` : `${place.code} · ${place.qty}`
                    }
                    tone={elsewhere ? 'warn' : 'ok'}
                    hint={
                      elsewhere
                        ? `Лежит на складе «${place.warehouseName}» — ${place.qty} шт. Здесь положить туда нельзя.`
                        : `Положить туда же, где уже лежит ${place.qty} шт`
                    }
                  />
                </Box>
              )
            })}
          </Stack>
        ),
    },
    {
      key: 'barcode',
      header: 'ШК',
      width: 148,
      render: ({ product }) => (
        <Typography
          variant="body2"
          sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12.5 }}
        >
          {product.barcode}
        </Typography>
      ),
    },
    {
      // Две цифры в одной колонке, а не в двух: «осталось» — то, ради чего сюда
      // смотрят, а «из скольких» отвечает на следующий вопрос, не занимая
      // собственный столбец. Строки тут и так в две строки, высота не прыгает.
      key: 'remaining',
      header: 'Осталось',
      width: 112,
      align: 'right',
      render: ({ remaining, product }) => (
        <Stack sx={{ alignItems: 'flex-end' }}>
          <QtyCell value={remaining} muted={remaining === 0} />
          <Typography variant="caption" color="text.secondary">
            из {product.accepted}
          </Typography>
        </Stack>
      ),
    },
    {
      key: 'actions',
      header: '',
      width: 56,
      align: 'right',
      render: ({ product, remaining }) => (
        <IconAction
          title={
            activeCell
              ? `Положить всё в ${activeCell.code}`
              : 'Сначала выберите ячейку'
          }
          onClick={() => onPlaceAll(product)}
          disabledReason={
            remaining === 0
              ? 'Всё уже разложено'
              : !activeCell
                ? 'Сначала пикните или выберите ячейку'
                : undefined
          }
          testId={`sorting-place-${product.id}`}
        >
          <AddOutlined fontSize="small" />
        </IconAction>
      ),
    },
  ]

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'baseline' }}>
        <Typography variant="h5" data-testid="sorting-left">
          {left.toLocaleString('ru-RU')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          штук осталось разложить из {total.toLocaleString('ru-RU')} принятых
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={total === 0 ? 0 : (done / total) * 100}
        sx={{ height: 8, borderRadius: 4 }}
      />
      <DataTable
        testId="sorting-remaining"
        columns={columns}
        rows={rows}
        getRowKey={(row) => row.product.id}
        empty={{ title: 'Раскладывать нечего', hint: 'Под фильтры ничего не подошло.' }}
      />
      {footer}
    </Stack>
  )
}
