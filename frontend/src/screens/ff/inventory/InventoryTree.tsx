import { Box, Stack, Tooltip, Typography } from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import GridViewOutlined from '@mui/icons-material/GridViewOutlined'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import type { ReactNode } from 'react'
import { DataTable, IconAction, NumberInput, QtyCell, StatusChip, TextCell } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import type { InvRow } from './InventoryRows'

const INDENT_STEP = 24
const ROW_HEIGHT = 28

const KIND_ICON: Record<InvRow['kind'], ReactNode> = {
  cell: <GridViewOutlined fontSize="small" color="primary" />,
  pallet: <LayersOutlined fontSize="small" color="action" />,
  box: <Inventory2Outlined fontSize="small" color="action" />,
  cargo_place: <WidgetsOutlined fontSize="small" color="action" />,
  product: null,
}

function titleWeight(kind: InvRow['kind']) {
  if (kind === 'cell') return 700
  if (kind === 'product') return 400
  return 600
}

function titleVariant(kind: InvRow['kind']) {
  return kind === 'cell' ? ('subtitle1' as const) : ('body2' as const)
}

/** Строка требует внимания: посчитали и не сошлось.
 *
 * У тары считаем по числу несошедшихся строк, а не по сумме: сумма схлопывает
 * излишек с недостачей и красит проблемный короб в спокойный цвет. */
export function hasDiscrepancy(row: InvRow): boolean {
  if (row.kind === 'product') return row.delta !== null && row.delta !== 0
  return row.mismatchLeaves > 0
}

/** Строка закрыта: посчитали и сошлось. У тары — когда закрыты все её листы. */
export function isComplete(row: InvRow): boolean {
  if (row.kind === 'product') return row.actual !== null && row.actual === row.expected
  // Тара закрыта, только когда посчитаны все её строки и все сошлись: наполовину
  // пройденный короб зелёным быть не может, к нему ещё возвращаться.
  return row.leaves > 0 && row.countedLeaves === row.leaves && !hasDiscrepancy(row)
}

function DeltaCell({ row }: { row: InvRow }) {
  if (row.kind !== 'product') {
    if (row.surplus === 0 && row.shortage === 0) {
      return (
        <Typography
          variant="body2"
          color={row.countedLeaves === 0 ? 'text.disabled' : 'text.secondary'}
        >
          {row.countedLeaves === 0 ? '—' : '0'}
        </Typography>
      )
    }
    // Излишек и недостача стоят рядом и никогда не складываются.
    return (
      <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
        {row.surplus > 0 ? (
          <Typography variant="body2" sx={{ color: 'success.main', fontWeight: 700 }}>
            +{row.surplus}
          </Typography>
        ) : null}
        {row.shortage > 0 ? (
          <Typography variant="body2" sx={{ color: 'error.main', fontWeight: 700 }}>
            −{row.shortage}
          </Typography>
        ) : null}
      </Stack>
    )
  }
  const d = row.delta
  if (d === null) return <Typography variant="body2" color="text.disabled">—</Typography>
  if (d === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        0
      </Typography>
    )
  }
  return (
    <Typography
      variant="body2"
      sx={{
        fontVariantNumeric: 'tabular-nums',
        fontWeight: 700,
        color: d > 0 ? 'success.main' : 'error.main',
      }}
    >
      {d > 0 ? `+${d}` : `−${Math.abs(d)}`}
    </Typography>
  )
}

type Props = {
  rows: InvRow[]
  loading: boolean
  readOnly: boolean
  empty?: { title: string; hint?: string; action?: ReactNode }
  onToggle: (row: InvRow) => void
  onActual: (row: InvRow, value: number | null) => void
}

export function InventoryTree({ rows, loading, readOnly, empty, onToggle, onActual }: Props) {
  const columns: Column<InvRow>[] = [
    {
      key: 'content',
      header: 'Содержимое',
      render: (row) => (
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', minHeight: ROW_HEIGHT, pl: `${row.depth * INDENT_STEP}px` }}
        >
          <Box sx={{ width: 30, display: 'flex', justifyContent: 'center' }}>
            {row.expandable ? (
              <IconAction
                title={row.expanded ? `Свернуть ${row.title}` : `Раскрыть ${row.title}`}
                onClick={() => onToggle(row)}
                testId={`inv-toggle-${row.key}`}
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
          <Box sx={{ width: 30, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            {row.kind === 'product' ? (
              <ProductPhotoThumb src={row.photoUrl} alt={row.title} size={28} />
            ) : (
              KIND_ICON[row.kind]
            )}
          </Box>
          <Typography
            variant={titleVariant(row.kind)}
            sx={{
              fontWeight: titleWeight(row.kind),
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
            title={row.title}
          >
            {row.title}
          </Typography>
          {row.stale ? (
            <StatusChip
              label="остаток изменился"
              tone="warn"
              hint="После наполнения документа по этой строке прошло движение. При проведении посчитаем от нового остатка."
              testId={`inv-stale-${row.key}`}
            />
          ) : null}
        </Stack>
      ),
    },
    {
      key: 'seller',
      header: 'Селлер',
      width: 170,
      render: (row) => (row.seller ? <TextCell value={row.seller} width={158} /> : null),
    },
    {
      key: 'progress',
      header: 'Посчитано',
      width: 110,
      align: 'right',
      render: (row) =>
        row.kind === 'product' ? null : (
          <Typography
            variant="body2"
            color={row.countedLeaves === row.leaves ? 'text.secondary' : 'text.primary'}
            sx={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {row.countedLeaves} из {row.leaves}
          </Typography>
        ),
    },
    {
      key: 'expected',
      header: 'Числится',
      width: 100,
      align: 'right',
      render: (row) => <QtyCell value={row.expected} muted={row.kind !== 'product'} />,
    },
    {
      key: 'actual',
      header: 'Факт',
      width: 120,
      align: 'right',
      // Поле ввода только у листа. У тары его нет намеренно: иначе экран сам
      // решит, из какого короба взяли, и вскроется это на следующем пересчёте.
      render: (row) =>
        row.kind === 'product' ? (
          <NumberInput
            label="Факт"
            hideLabel
            value={row.actual}
            min={0}
            onChange={(value) => onActual(row, value)}
            disabled={readOnly}
            testId={`inv-actual-${row.id}`}
          />
        ) : (
          <Tooltip title="Количество вводится у товара, а не у тары">
            <Typography variant="body2" color="text.disabled">
              {row.actual === null ? '—' : row.actual.toLocaleString('ru-RU')}
            </Typography>
          </Tooltip>
        ),
    },
    {
      key: 'delta',
      header: 'Расхождение',
      width: 120,
      align: 'right',
      render: (row) => <DeltaCell row={row} />,
    },
  ]

  return (
    <DataTable
      testId="inventory-tree"
      columns={columns}
      rows={rows}
      getRowKey={(row) => row.key}
      loading={loading}
      empty={empty}
      fixedLayout
      hasDiscrepancy={hasDiscrepancy}
      isComplete={isComplete}
    />
  )
}
