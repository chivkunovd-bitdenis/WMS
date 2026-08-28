import { Box, Typography } from '@mui/material'
import { DataTable, EmptyState, NumberInput, QtyCell, TextCell } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { placeTreeOf } from './pickRows'
import type { PickPlace, PickRow } from './pickRows'
import { PICK_CELLS, OBJECTS } from './pickStub'

// Содержимое раскрывашки товара: не список ячеек, а дерево «ячейка → палета →
// короб», и показаны только те ветки, что ведут к этому товару (владелец
// отменил показ постороннего состава места — вариант Б остался вариантом Б).
//
// Ступенька отступа — временный обход отсутствия в ui-kit ячейки-дерева
// (`TreeCell`): своя таблица здесь не заводится, `TextCell` просто завёрнут в
// `Box` с отступом по глубине. Как только `TreeCell` появится в ui-kit, этот
// файл — первый кандидат на переезд (контракт, §11).

export function PickPlacesTree({
  row,
  highlightedKey,
  onQtyChange,
}: {
  row: PickRow
  highlightedKey: string | null
  onQtyChange: (place: PickPlace, next: number | null) => void
}) {
  if (row.places.length === 0) {
    return (
      <EmptyState
        title="Этого товара нет на складе"
        hint="Снимать нечего — строка останется несобранной."
        testId={`pick-places-${row.product.id}`}
      />
    )
  }

  const tree = placeTreeOf(row.places, OBJECTS, PICK_CELLS)

  const columns: Column<(typeof tree)[number]>[] = [
    {
      key: 'place',
      header: 'Место',
      render: (node) => (
        <Box sx={{ pl: node.depth * 2 }}>
          <TextCell value={node.label} />
        </Box>
      ),
    },
    {
      key: 'lying',
      header: 'Лежит',
      align: 'right',
      width: 88,
      render: (node) =>
        node.place ? (
          <QtyCell value={node.place.qty} />
        ) : (
          <Typography variant="body2" color="text.secondary">
            —
          </Typography>
        ),
    },
    {
      key: 'taken',
      header: 'Снято отсюда',
      align: 'right',
      width: 120,
      render: (node) => {
        if (!node.place) return null
        const place = node.place
        // Потолок поля: не больше физического остатка и не больше того, что ещё
        // осталось по плану товара (контракт §4). Когда план закрыт, потолок
        // равен уже снятому — поле не растёт, а «Лежит» рядом объясняет почему.
        // Это временный обход отсутствия у NumberInput своей disabledReason.
        const ceiling = Math.min(place.qty, place.picked + row.left)
        return (
          <NumberInput
            label="Снято отсюда"
            hideLabel
            value={place.picked}
            onChange={(next) => onQtyChange(place, next)}
            min={0}
            max={ceiling}
            testId={`pick-place-qty-${row.product.id}-${place.key}`}
          />
        )
      },
    },
  ]

  return (
    <DataTable
      columns={columns}
      rows={tree}
      getRowKey={(node) => node.key}
      testId={`pick-places-${row.product.id}`}
      highlightedKey={highlightedKey}
    />
  )
}
