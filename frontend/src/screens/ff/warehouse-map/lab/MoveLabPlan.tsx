import { Box, Stack, Tooltip, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import {
  cellQty,
  metricCaption,
  metricValue,
  type LabCell,
  type LabMetric,
  type LabMove,
} from './labData'

// План склада плиткой. Плитки стоят по своим координатам в сетке, а не по потоку
// разметки, — из-за этого стрелку переезда можно нарисовать поверх, зная только
// ряд и номер ячейки, без измерения разметки в браузере.
const TILE_W = 148
const TILE_H = 84
const GAP = 14
const RACK_LABEL_W = 34

function tileLeft(column: number) {
  return RACK_LABEL_W + column * (TILE_W + GAP)
}

function tileTop(row: number) {
  return row * (TILE_H + GAP)
}

function centerOf(cell: LabCell) {
  return { x: tileLeft(cell.column) + TILE_W / 2, y: tileTop(cell.row) + TILE_H / 2 }
}

export function MoveLabPlan({
  cells,
  metric,
  highlighted,
  flying,
  onSelect,
}: {
  cells: LabCell[]
  metric: LabMetric
  highlighted: Set<string>
  /** Переезды, которые прямо сейчас летят по плану стрелками. */
  flying: LabMove[]
  onSelect: (cell: LabCell) => void
}) {
  const theme = useTheme()
  const rows = Math.max(...cells.map((cell) => cell.row)) + 1
  const columns = Math.max(...cells.map((cell) => cell.column)) + 1
  const width = RACK_LABEL_W + columns * TILE_W + (columns - 1) * GAP
  const height = rows * TILE_H + (rows - 1) * GAP
  const byId = new Map(cells.map((cell) => [cell.id, cell]))

  return (
    <Box sx={{ overflowX: 'auto' }}>
      <Box sx={{ position: 'relative', width, height, minWidth: width }}>
        {cells.map((cell) => {
          const value = metricValue(cell, metric, cells)
          const qty = cellQty(cell)
          const lit = highlighted.has(cell.id)
          return (
            <Tooltip
              key={cell.id}
              title={
                qty === 0
                  ? `${cell.code} — пусто, ${cell.distance} шагов от упаковки`
                  : cell.items.map((entry) => `${entry.name} — ${entry.qty} шт`).join(' · ')
              }
            >
              <Box
                role="button"
                tabIndex={0}
                onClick={() => onSelect(cell)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') onSelect(cell)
                }}
                data-testid={`lab-cell-${cell.id}`}
                sx={{
                  position: 'absolute',
                  left: tileLeft(cell.column),
                  top: tileTop(cell.row),
                  width: TILE_W,
                  height: TILE_H,
                  p: 1.25,
                  cursor: 'pointer',
                  borderRadius: 2,
                  border: '1px solid',
                  borderColor: lit ? 'primary.main' : 'divider',
                  boxShadow: lit ? `0 0 0 3px ${alpha(theme.palette.primary.main, 0.25)}` : 'none',
                  backgroundColor:
                    qty === 0
                      ? 'background.paper'
                      : alpha(theme.palette.primary.main, 0.08 + value * 0.42),
                  color: value > 0.6 && qty > 0 ? 'common.white' : 'text.primary',
                  transition: 'background-color 240ms, box-shadow 160ms, border-color 160ms',
                }}
              >
                <Stack sx={{ height: '100%', justifyContent: 'space-between' }}>
                  <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <Typography variant="subtitle2" sx={{ color: 'inherit', fontWeight: 700 }}>
                      {cell.code}
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'inherit', opacity: 0.85 }}>
                      {metricCaption(cell, metric)}
                    </Typography>
                  </Stack>
                  <Typography variant="caption" sx={{ color: 'inherit', opacity: 0.9 }}>
                    {qty === 0
                      ? 'пусто'
                      : `${qty} шт · ${cell.items.length} ${cell.items.length === 1 ? 'позиция' : 'позиции'}`}
                  </Typography>
                </Stack>
              </Box>
            </Tooltip>
          )
        })}

        {/* Стрелки переезда живут поверх плана и ничего не ловят мышью. */}
        <Box
          component="svg"
          viewBox={`0 0 ${width} ${height}`}
          sx={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'visible' }}
        >
          <defs>
            <marker id="lab-arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
              <path d="M0,0 L9,4.5 L0,9 Z" fill={theme.palette.primary.dark} />
            </marker>
          </defs>
          {flying.map((move, index) => {
            const from = byId.get(move.fromId)
            const to = byId.get(move.toId)
            if (!from || !to) return null
            const start = centerOf(from)
            const end = centerOf(to)
            const lift = 26 + index * 10
            const path = `M ${start.x} ${start.y} Q ${(start.x + end.x) / 2} ${
              Math.min(start.y, end.y) - lift
            } ${end.x} ${end.y}`
            return (
              <g key={`${move.fromId}-${move.toId}-${move.sku}`}>
                <path
                  d={path}
                  fill="none"
                  stroke={theme.palette.primary.dark}
                  strokeWidth={2.5}
                  markerEnd="url(#lab-arrow)"
                  strokeDasharray="180"
                  strokeDashoffset="180"
                >
                  <animate
                    attributeName="stroke-dashoffset"
                    from="180"
                    to="0"
                    dur="0.7s"
                    fill="freeze"
                  />
                </path>
                <circle r={5} fill={theme.palette.primary.dark}>
                  <animateMotion dur="0.7s" fill="freeze" path={path} />
                </circle>
              </g>
            )
          })}
        </Box>

        {Array.from({ length: rows }).map((_, row) => (
          <Typography
            key={row}
            variant="caption"
            sx={{
              position: 'absolute',
              left: 0,
              top: tileTop(row) + TILE_H / 2 - 9,
              width: RACK_LABEL_W - 8,
              textAlign: 'center',
              fontWeight: 700,
              color: 'text.secondary',
            }}
          >
            {cells.find((cell) => cell.row === row)?.code.split(' ')[0]}
          </Typography>
        ))}
      </Box>
    </Box>
  )
}
