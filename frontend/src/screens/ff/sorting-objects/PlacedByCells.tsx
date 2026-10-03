import { Box, Stack, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import ArrowUpwardOutlined from '@mui/icons-material/ArrowUpwardOutlined'
import ExpandMore from '@mui/icons-material/ExpandMore'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import RemoveOutlined from '@mui/icons-material/RemoveOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import { IconAction, QtyCell } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import {
  cellRef,
  type Cell,
  type GoodsLine,
  type Product,
  type WarehouseObject,
} from './objectsStub'
import {
  canPut,
  cellRows,
  objectTitle,
  type Carried,
  type ObjectRow,
} from './objectsRows'

// WMS-650. То, что уже стоит на ячейках, — рядом с ячейкой, а не в общем списке.
//
// Структура та же, что в разделе «Ячейки»: ячейка — заголовок группы, под ней
// то, что на ней стоит. Из этого списка нет «+» и перетаскивания: поставленное
// не ставится второй раз, а только снимается с ячейки или вынимается из тары
// (R10). Перенос на другую ячейку — только явный: скан другой ячейки и тары.
//
// Выделение (R11) отдаётся и цветом, и атрибутом data-highlight: «open» —
// открытая сканом ячейка или тара, «touched» — строка последнего действия.

const INDENT = 16

export function PlacedByCells({
  cells,
  objects,
  lines,
  products,
  collapsed,
  quantities,
  activeCellId,
  openObjectId,
  focusKey,
  carried,
  onPickCell,
  onDropOnCell,
  onToggle,
  onTakeOff,
  onTakeOut,
}: {
  cells: Cell[]
  objects: WarehouseObject[]
  lines: GoodsLine[]
  products: Product[]
  /** Какие объекты свёрнуты. Поставленное по умолчанию свёрнуто, чтобы список был коротким. */
  collapsed: Set<string>
  quantities: Map<string, number>
  activeCellId: string | null
  /** Открытая сканом тара. */
  openObjectId: string | null
  /** Строка, которой коснулось последнее действие. */
  focusKey: string | null
  carried: Carried | null
  onPickCell: (cellId: string) => void
  onDropOnCell: (cellId: string) => void
  onToggle: (objectId: string) => void
  onTakeOff: (row: ObjectRow) => void
  onTakeOut: (row: ObjectRow) => void
}) {
  const theme = useTheme()
  const primary = theme.palette.primary.main
  const success = theme.palette.success.main

  return (
    <Box data-testid="placed-list">
      {cells.map((cell, index) => {
        const active = activeCellId === cell.id
        const qty = quantities.get(cell.id) ?? 0
        const rows = cellRows(cell, objects, lines, products, collapsed)
        const target = Boolean(carried && canPut(carried, cellRef(cell.id), objects))
        return (
          <Box
            key={cell.id}
            data-testid={`placed-cell-${cell.id}`}
            sx={{ borderTop: index === 0 ? 'none' : '1px solid', borderColor: 'divider' }}
          >
            <Stack
              direction="row"
              role="button"
              tabIndex={0}
              data-highlight={active ? 'open' : undefined}
              onClick={() => onPickCell(cell.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') onPickCell(cell.id)
              }}
              onDragOver={(event) => {
                if (target) event.preventDefault()
              }}
              onDrop={() => {
                onPickCell(cell.id)
                onDropOnCell(cell.id)
              }}
              sx={{
                alignItems: 'center',
                justifyContent: 'space-between',
                px: 1.5,
                py: 0.75,
                cursor: 'pointer',
                // Открытая ячейка — полоса слева и лёгкая заливка: то же
                // выделение места, что у «selectedKey» в таблице продукта.
                boxShadow: active ? `inset 3px 0 0 ${primary}` : 'none',
                backgroundColor: active ? alpha(primary, 0.09) : 'transparent',
                outline: target && !active ? `1px dashed ${alpha(primary, 0.45)}` : 'none',
                outlineOffset: '-3px',
              }}
            >
              <Typography variant="subtitle2" sx={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                {cell.code}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', pl: 1 }}>
                {qty === 0 ? 'пусто' : `${qty} шт`}
              </Typography>
            </Stack>
            {rows.map((row) => {
              const open = row.kind === 'object' && row.object.id === openObjectId
              const touched = !open && row.key === focusKey
              const holder = row.kind === 'object' ? row.object.holder : row.line.holder
              const onCell = Boolean(holder && holder.startsWith('cell:'))
              const hostKind = !onCell
                ? objects.find((one) => `obj:${one.id}` === holder)?.kind
                : undefined
              const title = row.kind === 'object' ? objectTitle(row.object) : row.name
              return (
                <Stack
                  key={row.key}
                  direction="row"
                  spacing={0.5}
                  data-row-key={row.key}
                  data-highlight={open ? 'open' : touched ? 'touched' : undefined}
                  sx={{
                    alignItems: 'center',
                    minHeight: 34,
                    pl: `${12 + row.depth * INDENT}px`,
                    pr: 0.5,
                    ...(open
                      ? {
                          outline: `2px solid ${primary}`,
                          outlineOffset: '-2px',
                          backgroundColor: alpha(primary, 0.09),
                        }
                      : null),
                    // Только что положенное: зелёная заливка = «сделано» (канон R-11
                    // отводит зелёную строку закрытой работе), и она гаснет со
                    // следующим действием.
                    ...(touched
                      ? {
                          backgroundColor: alpha(success, 0.14),
                          boxShadow: `inset 3px 0 0 ${success}`,
                        }
                      : null),
                  }}
                >
                  <Box sx={{ width: 22, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                    {row.kind === 'object' && row.expandable ? (
                      <IconAction
                        title={row.expanded ? `Свернуть ${title}` : `Раскрыть ${title}`}
                        onClick={() => onToggle(row.object.id)}
                        testId={`placed-toggle-${row.object.id}`}
                      >
                        <ExpandMore
                          fontSize="small"
                          sx={{
                            transition: 'transform 120ms',
                            transform: row.expanded ? 'rotate(180deg)' : 'none',
                          }}
                        />
                      </IconAction>
                    ) : null}
                  </Box>
                  <Box sx={{ width: 22, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                    {row.kind === 'object' ? (
                      row.object.kind === 'pallet' ? (
                        <LayersOutlined fontSize="small" sx={{ color: 'text.secondary' }} />
                      ) : row.object.kind === 'box' ? (
                        <Inventory2Outlined fontSize="small" sx={{ color: 'text.secondary' }} />
                      ) : (
                        <WidgetsOutlined fontSize="small" sx={{ color: 'text.secondary' }} />
                      )
                    ) : (
                      <ProductPhotoThumb src={row.photo} alt={row.name} size={22} />
                    )}
                  </Box>
                  <Stack sx={{ minWidth: 0, flexGrow: 1, flexBasis: 0 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: row.kind === 'object' ? 600 : 400,
                        whiteSpace: 'normal',
                        overflowWrap: 'break-word',
                      }}
                    >
                      {title}
                    </Typography>
                    {row.kind === 'object' ? (
                      <Typography variant="caption" color="text.secondary">
                        {row.inside === 0 ? 'пусто' : `внутри ${row.inside}`}
                      </Typography>
                    ) : null}
                  </Stack>
                  <Box sx={{ minWidth: 34, textAlign: 'right', flexShrink: 0 }}>
                    <QtyCell value={row.qty} muted={row.qty === 0} />
                  </Box>
                  <Box sx={{ width: 34, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                    {onCell ? (
                      <IconAction
                        title="Снять с ячейки"
                        onClick={() => onTakeOff(row)}
                        testId={`placed-minus-${row.key}`}
                      >
                        <RemoveOutlined fontSize="small" />
                      </IconAction>
                    ) : hostKind ? (
                      <IconAction
                        title={`Вынуть из ${hostKind === 'pallet' ? 'палеты' : hostKind === 'box' ? 'короба' : 'грузоместа'}`}
                        onClick={() => onTakeOut(row)}
                        testId={`placed-out-${row.key}`}
                      >
                        <ArrowUpwardOutlined fontSize="small" />
                      </IconAction>
                    ) : null}
                  </Box>
                </Stack>
              )
            })}
          </Box>
        )
      })}
    </Box>
  )
}
