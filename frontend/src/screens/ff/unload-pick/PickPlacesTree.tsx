import { Stack, Typography } from '@mui/material'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import type { ReactNode } from 'react'
import { DataTable, EmptyState, NumberInput, QtyCell, TextCell } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import type { PickPlace, PickRow, PlaceKind } from './pickRows'

// Содержимое раскрывашки товара: плоский список мест, а не дерево.
//
// Владелец посмотрел раскрывашку-дерево (ячейка → палета → короб со ступенькой
// отступа и структурными строками) и отменил её дословно (28.08): «у тебя
// раздел — россыпь, короба, паллета, каждый на своей ячейке, вот откуда я
// выбрал оттуда и взял». Раздел мест — это те места, откуда физически можно
// взять товар: одна строка — одно место, у каждой есть число «Лежит» и поле
// «Снять». Строк-заголовков без числа и без поля («ячейка целиком», «палета
// целиком, если в ней есть короб») здесь нет — считать в них нечего, а
// сортировка сама показывает, что стоит рядом (ячейка сначала, «Без ячейки»
// потом).

const KIND_ICON: Partial<Record<PlaceKind, ReactNode>> = {
  pallet: <LayersOutlined fontSize="small" color="action" />,
  box: <Inventory2Outlined fontSize="small" color="action" />,
  cargo_place: <WidgetsOutlined fontSize="small" color="action" />,
}

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

  const columns: Column<PickPlace>[] = [
    {
      key: 'source',
      header: 'Откуда снимаем',
      render: (place) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          {KIND_ICON[place.kind] ?? null}
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {place.sourceTitle}
          </Typography>
        </Stack>
      ),
    },
    {
      key: 'barcode',
      header: 'ШК',
      width: 134,
      render: (place) =>
        place.barcode ? (
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
            {place.barcode}
          </Typography>
        ) : null,
    },
    {
      key: 'standing',
      header: 'Где стоит',
      render: (place) =>
        place.cellCode ? (
          <TextCell value={place.standing} />
        ) : (
          // «Без ячейки» — нормальное состояние склада, а не ошибка данных, и
          // его надо выделить, а не спрятать в общий приглушённый текст (R-21).
          <Typography variant="body2" sx={{ fontWeight: 600, color: 'warning.main' }}>
            {place.standing}
          </Typography>
        ),
    },
    {
      key: 'lying',
      header: 'Лежит',
      align: 'right',
      width: 88,
      render: (place) => <QtyCell value={place.qty} />,
    },
    {
      key: 'take',
      header: 'Снять',
      align: 'right',
      width: 120,
      render: (place) => {
        // Потолок поля: не больше физического остатка и не больше того, что ещё
        // осталось по плану товара (контракт §4). Когда план закрыт, потолок
        // равен уже снятому — поле не растёт, а «Лежит» рядом объясняет почему.
        // Это временный обход отсутствия у NumberInput своей disabledReason.
        const ceiling = Math.min(place.qty, place.picked + row.left)
        return (
          <NumberInput
            label="Снять"
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
      rows={row.places}
      getRowKey={(place) => place.key}
      testId={`pick-places-${row.product.id}`}
      highlightedKey={highlightedKey}
      hideHeader
    />
  )
}
