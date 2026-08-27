import { Box, Stack, Tooltip, Typography } from '@mui/material'
import ExpandMore from '@mui/icons-material/ExpandMore'
import DragIndicator from '@mui/icons-material/DragIndicator'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import WidgetsOutlined from '@mui/icons-material/WidgetsOutlined'
import MoveDownOutlined from '@mui/icons-material/MoveDownOutlined'
import ArrowUpwardOutlined from '@mui/icons-material/ArrowUpwardOutlined'
import type { ReactNode } from 'react'
import { DataTable, IconAction, QtyCell, StatusChip, TextCell } from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { ProductPhotoThumb } from '../../../components/ProductPhotoThumb'
import { objRef, type Holder, type ObjKind } from './objectsStub'
import { canPut, objectTitle, type Carried, type ObjectRow } from './objectsRows'

const INDENT_STEP = 20
const ROW_HEIGHT = 30

const KIND_ICON: Record<ObjKind, ReactNode> = {
  pallet: <LayersOutlined fontSize="small" color="primary" />,
  box: <Inventory2Outlined fontSize="small" color="action" />,
  cargo_place: <WidgetsOutlined fontSize="small" color="action" />,
}

export function ObjectsTree({
  rows,
  carried,
  objects,
  placeLabel,
  testId,
  empty,
  onToggle,
  onDragStart,
  onDragEnd,
  onDropOn,
  onPlace,
  onTakeOut,
}: {
  rows: ObjectRow[]
  carried: Carried | null
  objects: Parameters<typeof canPut>[2]
  /** Куда положит кнопка «поставить»: подпись активной ячейки или null. */
  placeLabel: string | null
  testId: string
  empty: { title: string; hint?: string }
  onToggle: (objectId: string) => void
  onDragStart: (row: ObjectRow) => void
  onDragEnd: () => void
  onDropOn: (target: Holder) => void
  onPlace: (row: ObjectRow) => void
  onTakeOut: (row: ObjectRow) => void
}) {
  const columns: Column<ObjectRow>[] = [
    {
      key: 'what',
      header: 'Содержимое',
      render: (row) => (
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', minHeight: ROW_HEIGHT, pl: `${row.depth * INDENT_STEP}px` }}
        >
          <Box sx={{ width: 30, display: 'flex', justifyContent: 'center' }}>
            {row.kind === 'object' && row.expandable ? (
              <IconAction
                title={row.expanded ? `Свернуть ${objectTitle(row.object)}` : `Раскрыть ${objectTitle(row.object)}`}
                onClick={() => onToggle(row.object.id)}
                testId={`${testId}-toggle-${row.object.id}`}
              >
                <ExpandMore
                  fontSize="small"
                  sx={{ transition: 'transform 120ms', transform: row.expanded ? 'rotate(180deg)' : 'none' }}
                />
              </IconAction>
            ) : null}
          </Box>
          <Tooltip title="Потяните строку в другой объект или на ячейку">
            <DragIndicator fontSize="small" sx={{ color: 'text.disabled' }} />
          </Tooltip>
          <Box sx={{ width: 30, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            {row.kind === 'object' ? (
              KIND_ICON[row.object.kind]
            ) : (
              <ProductPhotoThumb src={row.photo} alt={row.name} size={26} />
            )}
          </Box>
          {/* Длинное название не растягивает таблицу за край панели: под
              многоточием всегда лежит подсказка с полным значением (канон R-02). */}
          <Tooltip title={row.kind === 'object' ? objectTitle(row.object) : row.name}>
            <Typography
              variant="body2"
              sx={{
                fontWeight: row.kind === 'object' ? 700 : 400,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: 240,
              }}
            >
              {row.kind === 'object' ? objectTitle(row.object) : row.name}
            </Typography>
          </Tooltip>
          {row.kind === 'object' && row.empty ? (
            <StatusChip label="пустой" tone="neutral" hint="Внутри пока ничего нет" />
          ) : null}
        </Stack>
      ),
    },
    {
      key: 'seller',
      header: 'Селлер',
      width: 128,
      render: (row) => (row.kind === 'goods' ? <TextCell value={row.seller} width={116} /> : null),
    },
    {
      key: 'barcode',
      header: 'ШК',
      width: 122,
      render: (row) => (
        <Typography
          variant="body2"
          sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12.5 }}
        >
          {row.kind === 'object' ? row.object.barcode : row.barcode}
        </Typography>
      ),
    },
    {
      key: 'qty',
      header: 'Штук',
      width: 80,
      align: 'right',
      render: (row) => <QtyCell value={row.qty} muted={row.qty === 0} />,
    },
    {
      key: 'actions',
      header: '',
      width: 76,
      align: 'right',
      render: (row) => (
        <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'flex-end' }}>
          {row.depth > 0 ? (
            <IconAction
              title="Вынуть наружу"
              onClick={() => onTakeOut(row)}
              testId={`${testId}-out-${row.key}`}
            >
              <ArrowUpwardOutlined fontSize="small" />
            </IconAction>
          ) : null}
          <IconAction
            title={placeLabel ? `Поставить в ${placeLabel}` : 'Сначала выберите ячейку'}
            onClick={() => onPlace(row)}
            disabledReason={placeLabel ? undefined : 'Сначала выберите ячейку справа'}
            testId={`${testId}-place-${row.key}`}
          >
            <MoveDownOutlined fontSize="small" />
          </IconAction>
        </Stack>
      ),
    },
  ]

  return (
    <DataTable
      testId={testId}
      columns={columns}
      rows={rows}
      getRowKey={(row) => row.key}
      empty={empty}
      drag={{
        active: carried !== null,
        canDrag: () => true,
        canDrop: (row) =>
          row.kind === 'object' && carried !== null && canPut(carried, objRef(row.object.id), objects),
        onDragStart,
        onDragEnd,
        onDrop: (row) => {
          if (row.kind === 'object') onDropOn(objRef(row.object.id))
        },
      }}
    />
  )
}
