import { Box, Stack, Typography } from '@mui/material'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import type { ReactNode } from 'react'
import { DataTable, EmptyState, NumberInput, QtyCell } from '../../../ui-kit'
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

// Ступенька и направляющая — те же, что в принятой раскладке: на втором
// уровне глаз перестаёт понимать, на чём стоит короб, и линия отвечает на это
// без единого лишнего слова.
const INDENT_STEP = 32
const GUIDE = 'rgba(15, 23, 42, 0.26)'

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
      width: 320,
      render: (place) => (
        <Stack
          direction="row"
          spacing={1}
          sx={{
            alignItems: 'center',
            minHeight: 36,
            pl: `${place.depth * INDENT_STEP}px`,
            backgroundImage:
              place.depth === 0
                ? 'none'
                : Array.from({ length: place.depth })
                    .map(() => `linear-gradient(to bottom, ${GUIDE} 0 100%)`)
                    .join(', '),
            backgroundRepeat: 'no-repeat',
            backgroundSize: Array.from({ length: place.depth })
              .map(() => '1px 100%')
              .join(', '),
            backgroundPosition: Array.from({ length: place.depth })
              .map((_, level) => `${level * INDENT_STEP + 10}px 0`)
              .join(', '),
          }}
        >
          <Box sx={{ width: 22, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
            {KIND_ICON[place.kind] ?? null}
          </Box>
          <Stack sx={{ minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {place.sourceTitle}
            </Typography>
            {/* Вложенному месту адрес не повторяем: на чём оно стоит, видно по
                ступеньке и по строке родителя прямо над ним. */}
            {place.depth > 0 ? null : place.cellCode ? (
              <Typography variant="caption" color="text.secondary">
                {place.standing}
              </Typography>
            ) : (
              // «Без ячейки» — нормальное состояние склада, а не ошибка данных,
              // и его надо выделить, а не спрятать в приглушённый текст (R-21).
              <Typography variant="caption" sx={{ fontWeight: 600, color: 'warning.main' }}>
                {place.standing}
              </Typography>
            )}
          </Stack>
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
    { key: 'tail', header: '', render: () => null },
  ]

  return (
    <DataTable
      columns={columns}
      rows={row.places}
      getRowKey={(place) => place.key}
      testId={`pick-places-${row.product.id}`}
      highlightedKey={highlightedKey}
    />
  )
}
