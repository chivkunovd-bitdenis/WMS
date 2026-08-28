import { Box, Stack, Typography } from '@mui/material'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import GridViewOutlined from '@mui/icons-material/GridViewOutlined'
import { useState } from 'react'
import type { ReactNode } from 'react'
import ExpandMore from '@mui/icons-material/ExpandMore'
import { DataTable, EmptyState, IconAction, NumberInput, QtyCell } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import type { Column } from '../../../ui-kit'
import { placeNodesOf } from './pickRows'
import type { PickPlace, PickRow, PlaceKind, PlaceNode } from './pickRows'
import { OBJECTS, PICK_CELLS } from './pickStub'
import type { Cell, WarehouseObject } from './pickStub'

// Содержимое раскрывашки товара: раскрывающаяся структура склада, а не список.
//
// Ровно тот же вид, что на принятой раскладке: ячейка, на ней палета, на палете
// короб, в коробе товар. Владелец потребовал этого прямо: «ну ты же это делал в
// сортировке, у тебя в паллете может быть короб а в нём товары». Один и тот же
// склад обязан выглядеть одинаково на всех экранах — иначе оператор каждый раз
// заново разбирается, что во что вложено.
//
// Снимают всегда со строки товара, а не с тары: количество и поле есть только у
// листа. Поле на таре означало бы, что экран сам решает, из какого короба взяли.

const INDENT_STEP = 24
const GUIDE = 'rgba(15, 23, 42, 0.22)'

const KIND_ICON: Record<PlaceKind, ReactNode> = {
  loose: <GridViewOutlined fontSize="small" sx={{ color: 'text.secondary' }} />,
  pallet: <LayersOutlined fontSize="small" sx={{ color: 'text.secondary' }} />,
  box: <Inventory2Outlined fontSize="small" sx={{ color: 'text.secondary' }} />,
  cargo_place: <WidgetsOutlined fontSize="small" sx={{ color: 'text.secondary' }} />,
}

function Indent({ depth, children }: { depth: number; children: ReactNode }) {
  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{
        alignItems: 'center',
        minHeight: 34,
        pl: `${depth * INDENT_STEP}px`,
        // Направляющие вместо голого отступа: на третьей ступени глаз перестаёт
        // понимать, чьё это содержимое, и линия отвечает на это без слов.
        backgroundImage:
          depth === 0
            ? 'none'
            : Array.from({ length: depth })
                .map(() => `linear-gradient(to bottom, ${GUIDE} 0 100%)`)
                .join(', '),
        backgroundRepeat: 'no-repeat',
        backgroundSize: Array.from({ length: depth })
          .map(() => '1px 100%')
          .join(', '),
        backgroundPosition: Array.from({ length: depth })
          .map((_, level) => `${level * INDENT_STEP + 11}px 0`)
          .join(', '),
      }}
    >
      {children}
    </Stack>
  )
}

export function PickPlacesTree({
  row,
  highlightedKey,
  onQtyChange,
  objects = OBJECTS,
  cells = PICK_CELLS,
  busy = false,
}: {
  row: PickRow
  highlightedKey: string | null
  onQtyChange: (place: PickPlace, next: number | null) => void
  objects?: WarehouseObject[]
  cells?: Cell[]
  busy?: boolean
}) {
  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(() => new Set())
  if (row.places.length === 0) {
    return (
      <EmptyState
        title="Этого товара нет на складе"
        hint="Снимать нечего — строка останется несобранной."
        testId={`pick-places-${row.product.id}`}
      />
    )
  }

  const all = placeNodesOf(row.places, objects, cells)
  // Свёрнутое хранится списком, а не «раскрытым»: по умолчанию структура открыта
  // целиком, иначе оператор при каждом заходе кликал бы, чтобы увидеть работу.
  const collapsed = collapsedKeys
  const hidden = new Set<string>()
  for (const node of all) {
    if (node.parentKey && (collapsed.has(node.parentKey) || hidden.has(node.parentKey))) {
      hidden.add(node.key)
    }
  }
  const hasChildren = new Set(all.map((node) => node.parentKey).filter(Boolean) as string[])
  const nodes = all.filter((node) => !hidden.has(node.key))

  const columns: Column<PlaceNode>[] = [
    {
      key: 'what',
      header: 'Где лежит и что снимаем',
      render: (node) =>
        node.kind === 'container' ? (
          <Indent depth={node.depth}>
            <Box sx={{ width: 24, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
              {hasChildren.has(node.key) ? (
                <IconAction
                  title={
                    collapsed.has(node.key) ? `Раскрыть ${node.title}` : `Свернуть ${node.title}`
                  }
                  onClick={() =>
                    setCollapsedKeys((prev) => {
                      const next = new Set(prev)
                      if (next.has(node.key)) next.delete(node.key)
                      else next.add(node.key)
                      return next
                    })
                  }
                  testId={`pick-level-${row.product.id}-${node.key}`}
                >
                  <ExpandMore
                    fontSize="small"
                    sx={{
                      transition: 'transform 120ms',
                      transform: collapsed.has(node.key) ? 'rotate(-90deg)' : 'none',
                    }}
                  />
                </IconAction>
              ) : null}
            </Box>
            <Box sx={{ width: 22, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
              {KIND_ICON[node.icon]}
            </Box>
            <Stack sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {node.title}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  color: node.title === 'Без ячейки' ? 'warning.main' : 'text.secondary',
                  fontWeight: node.title === 'Без ячейки' ? 600 : 400,
                }}
              >
                {node.inside > 0 ? `внутри ${node.inside} шт` : 'стоит не на ячейке'}
              </Typography>
            </Stack>
          </Indent>
        ) : (
          <Indent depth={node.depth}>
            <Box sx={{ width: 24, flexShrink: 0 }} />
            <Box sx={{ width: 22, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
              <ProductPhotoThumb src={row.product.photo} alt={row.product.name} size={24} />
            </Box>
            <Stack sx={{ minWidth: 0 }}>
              <Typography variant="body2">{row.product.name}</Typography>
              <Typography variant="caption" color="text.secondary">
                {row.product.sku}
                {row.product.size ? ` · ${row.product.size}` : ''}
              </Typography>
            </Stack>
          </Indent>
        ),
    },
    {
      key: 'barcode',
      header: 'ШК',
      width: 134,
      render: (node) => {
        const code = node.kind === 'container' ? node.barcode : row.product.barcode
        return code ? (
          <Typography
            variant="body2"
            sx={{
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              fontSize: 12.5,
              color: 'text.secondary',
              whiteSpace: 'nowrap',
            }}
          >
            {code}
          </Typography>
        ) : null
      },
    },
    {
      key: 'lying',
      header: 'Лежит',
      align: 'right',
      width: 76,
      render: (node) => (node.kind === 'goods' ? <QtyCell value={node.place.qty} /> : null),
    },
    {
      key: 'take',
      header: 'Снять',
      align: 'right',
      width: 116,
      render: (node) => {
        if (node.kind !== 'goods') return null
        // Потолок: не больше того, что лежит здесь, и не больше того, что ещё
        // осталось по плану товара. Когда план закрыт, потолок равен уже снятому.
        const ceiling = Math.min(node.place.qty, node.place.picked + row.left)
        return (
          <NumberInput
            label="Снять"
            hideLabel
            value={node.place.picked}
            onChange={(next) => onQtyChange(node.place, next)}
            min={0}
            max={ceiling}
            disabled={busy}
            testId={`pick-place-qty-${row.product.id}-${node.place.key}`}
          />
        )
      },
    },
    { key: 'tail', header: '', render: () => null },
  ]

  return (
    <DataTable
      columns={columns}
      rows={nodes}
      getRowKey={(node) => node.key}
      testId={`pick-places-${row.product.id}`}
      highlightedKey={highlightedKey}
    />
  )
}
