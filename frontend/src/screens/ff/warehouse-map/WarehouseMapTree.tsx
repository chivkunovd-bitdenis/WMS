import { Box, Stack, Tooltip, Typography } from '@mui/material'
import CallSplitOutlined from '@mui/icons-material/CallSplitOutlined'
import ExpandMore from '@mui/icons-material/ExpandMore'
import DragIndicator from '@mui/icons-material/DragIndicator'
import GridViewOutlined from '@mui/icons-material/GridViewOutlined'
import HistoryOutlined from '@mui/icons-material/HistoryOutlined'
import InboxOutlined from '@mui/icons-material/InboxOutlined'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import MoveDownOutlined from '@mui/icons-material/MoveDownOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import type { ReactNode } from 'react'
import { DataTable, IconAction, PrintAction, QtyCell, StatusChip, TextCell } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { canDragRow, canDropOn, type MapRow } from './WarehouseMapRows'
import { UNASSIGNED_ID } from './WarehouseMapTypes'

// Ширина одного уровня вложенности. Двадцать четыре пикселя — столько, чтобы
// уступ читался с расстояния вытянутой руки, и не столько, чтобы на третьем
// уровне название уехало на середину экрана.
const INDENT_STEP = 24
const ROW_HEIGHT = 28

const KIND_ICON: Record<MapRow['kind'], ReactNode> = {
  cell: <GridViewOutlined fontSize="small" color="primary" />,
  unassigned: <InboxOutlined fontSize="small" color="primary" />,
  pallet: <LayersOutlined fontSize="small" color="action" />,
  box: <Inventory2Outlined fontSize="small" color="action" />,
  cargo_place: <WidgetsOutlined fontSize="small" color="action" />,
  product: null,
}

const EMPTY_LABEL: Partial<Record<MapRow['kind'], string>> = {
  cell: 'Пусто',
  unassigned: 'Пусто',
  pallet: 'Пустая',
  box: 'Пустой',
  cargo_place: 'Пустое',
}

function titleWeight(kind: MapRow['kind']) {
  if (kind === 'cell' || kind === 'unassigned') return 700
  if (kind === 'product') return 400
  return 600
}

// Ячейка и «Без ячеек» — заголовки групп, и они на размер крупнее содержимого:
// иначе конец одной ячейки и начало следующей сливаются в одну простыню.
function titleVariant(kind: MapRow['kind']) {
  return kind === 'cell' || kind === 'unassigned' ? ('subtitle1' as const) : ('body2' as const)
}

function isInsideUnassigned(row: MapRow) {
  return row.ancestorKeys.includes(UNASSIGNED_ID)
}

type Props = {
  rows: MapRow[]
  loading: boolean
  carried: MapRow | null
  /** Строка, которую нашли сканером: подсвечена, пока не пикнут следующее. */
  highlightedKey: string | null
  empty?: { title: string; hint?: string; action?: ReactNode }
  onToggle: (row: MapRow) => void
  onTakeOff: (row: MapRow) => void
  onDisband: (row: MapRow) => void
  onHistory: (row: MapRow) => void
  onPrintCell: (row: MapRow) => void
  onDragStart: (row: MapRow) => void
  onDragEnd: () => void
  onDrop: (row: MapRow) => void
}

export function WarehouseMapTree({
  rows,
  loading,
  carried,
  highlightedKey,
  empty,
  onToggle,
  onTakeOff,
  onDisband,
  onHistory,
  onPrintCell,
  onDragStart,
  onDragEnd,
  onDrop,
}: Props) {
  const columns: Column<MapRow>[] = [
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
                testId={`map-toggle-${row.key}`}
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
          <Box sx={{ width: 20, display: 'flex', justifyContent: 'center' }}>
            {canDragRow(row) ? (
              // Ручка говорит, что строку можно взять. Без неё перетаскивание
              // существует, но о нём никто не догадывается — как со сканером,
              // который работал и молчал.
              <Tooltip title="Потяните строку на другую ячейку">
                <DragIndicator fontSize="small" sx={{ color: 'text.disabled' }} />
              </Tooltip>
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
          {row.empty && EMPTY_LABEL[row.kind] ? (
            <StatusChip
              label={EMPTY_LABEL[row.kind] as string}
              tone="neutral"
              hint="Внутри сейчас ничего нет"
              testId={`map-empty-${row.key}`}
            />
          ) : null}
        </Stack>
      ),
    },
    {
      key: 'seller',
      header: 'Селлер',
      width: 170,
      render: (row) =>
        row.seller ? <TextCell value={row.seller} width={158} /> : null,
    },
    {
      key: 'barcode',
      header: 'ШК',
      width: 160,
      render: (row) =>
        row.barcode ? (
          <Typography
            variant="body2"
            sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12.5 }}
          >
            {row.barcode}
          </Typography>
        ) : null,
    },
    {
      key: 'qty',
      header: 'Штук',
      width: 90,
      align: 'right',
      render: (row) => <QtyCell value={row.qty} muted={row.qty === 0} />,
    },
    {
      key: 'actions',
      header: '',
      width: 116,
      align: 'right',
      render: (row) => (
        <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'flex-end' }}>
          {row.kind === 'cell' ? (
            <PrintAction
              what="ШК ячейки"
              placement="row"
              onClick={() => onPrintCell(row)}
              testId={`map-print-${row.key}`}
            />
          ) : null}
          {row.kind === 'pallet' ? (
            <IconAction
              title="Расформировать палету"
              onClick={() => onDisband(row)}
              testId={`map-disband-${row.key}`}
            >
              <CallSplitOutlined fontSize="small" />
            </IconAction>
          ) : null}
          {row.kind !== 'cell' && row.kind !== 'unassigned' && !isInsideUnassigned(row) ? (
            <IconAction
              title="Снять с ячейки"
              onClick={() => onTakeOff(row)}
              testId={`map-takeoff-${row.key}`}
            >
              <MoveDownOutlined fontSize="small" />
            </IconAction>
          ) : null}
          {row.kind !== 'cell' && row.kind !== 'unassigned' ? (
            <IconAction
              title="История перемещений"
              onClick={() => onHistory(row)}
              testId={`map-history-${row.key}`}
            >
              <HistoryOutlined fontSize="small" />
            </IconAction>
          ) : null}
        </Stack>
      ),
    },
  ]

  return (
    <DataTable
      testId="warehouse-map-table"
      columns={columns}
      rows={rows}
      getRowKey={(row) => row.key}
      loading={loading}
      empty={empty}
      highlightedKey={highlightedKey}
      drag={{
        active: carried !== null,
        canDrag: canDragRow,
        canDrop: (row) => (carried ? canDropOn(carried, row) : false),
        onDragStart,
        onDragEnd,
        onDrop,
      }}
    />
  )
}
