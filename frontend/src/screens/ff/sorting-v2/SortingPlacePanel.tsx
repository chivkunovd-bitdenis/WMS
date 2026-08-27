import { Box, Paper, Stack, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import ChevronRight from '@mui/icons-material/ChevronRight'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import DragIndicator from '@mui/icons-material/DragIndicator'
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined'
import LayersOutlined from '@mui/icons-material/LayersOutlined'
import {
  DataTable,
  EmptyState,
  IconAction,
  PrimaryAction,
  PrintAction,
  QtyCell,
  SecondaryAction,
  StatusChip,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import {
  CONTAINER_TITLE,
  canDropInto,
  containerQty,
  creatableIn,
  type Carried,
  type Container,
  type ContainerKind,
  type PlaceRef,
  type Placement,
  type SortCell,
  type SortProduct,
} from './sortingStub'

// Панель активного места. Место — это не обязательно ячейка: это ячейка, палета
// на ней или короб внутри. Глубина показана хлебной крошкой, а не вложенными
// панелями: две панели друг в друге оператор читает как два разных экрана.

type PlaceRow =
  | { key: string; kind: 'container'; container: Container; qty: number }
  | { key: string; kind: 'goods'; placement: Placement; product: SortProduct }

export function SortingPlacePanel({
  cell,
  path,
  place,
  containers,
  placements,
  products,
  carried,
  onEnter,
  onLeaveTo,
  onCreate,
  onChangeQty,
  onRemove,
  onDropHere,
  onDragContainer,
  onDragEnd,
  onCommit,
  onPrint,
}: {
  /** Ячейка, в которой всё происходит: её содержимое до раскладки. */
  cell: SortCell | null
  /** Путь от ячейки до активного места, включая его самого. */
  path: PlaceRef[]
  place: PlaceRef | null
  containers: Container[]
  placements: Placement[]
  products: SortProduct[]
  carried: Carried | null
  onEnter: (place: PlaceRef) => void
  onLeaveTo: (index: number) => void
  onCreate: (kind: ContainerKind) => void
  onChangeQty: (productId: string, qty: number) => void
  onRemove: (productId: string) => void
  onDropHere: (place: PlaceRef) => void
  onDragContainer: (container: Container) => void
  onDragEnd: () => void
  onCommit: () => void
  onPrint: () => void
}) {
  const theme = useTheme()
  const productById = new Map(products.map((product) => [product.id, product]))

  if (!place) {
    return (
      <Paper variant="outlined" data-testid="sorting-no-cell">
        <EmptyState
          title="Ячейка не выбрана"
          hint="Пикните штрихкод с полки или выберите ячейку выше. Пока места нет, класть некуда."
        />
      </Paper>
    )
  }

  const rows: PlaceRow[] = [
    ...containers
      .filter((one) => one.parentId === place.id)
      .map((container) => ({
        key: `c-${container.id}`,
        kind: 'container' as const,
        container,
        qty: containerQty(container.id, placements, containers),
      })),
    ...placements
      .filter((one) => one.cellId === place.id)
      .map((placement) => ({
        key: `g-${placement.productId}`,
        kind: 'goods' as const,
        placement,
        product: productById.get(placement.productId)!,
      }))
      .filter((row) => Boolean(row.product)),
  ]
  const here = containerQty(place.id, placements, containers)
  const canCreate = creatableIn(place)

  const columns: Column<PlaceRow>[] = [
    {
      key: 'what',
      header: 'В этом месте',
      render: (row) =>
        row.kind === 'container' ? (
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minHeight: 34 }}>
            <DragIndicator fontSize="small" sx={{ color: 'text.disabled' }} />
            {row.container.kind === 'pallet' ? (
              <LayersOutlined fontSize="small" color="action" />
            ) : (
              <Inventory2Outlined fontSize="small" color="action" />
            )}
            <Typography variant="body2" sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
              {CONTAINER_TITLE[row.container.kind]} {row.container.code}
            </Typography>
            {row.qty === 0 ? <StatusChip label="пустой" tone="neutral" /> : null}
          </Stack>
        ) : (
          <Typography variant="body2" sx={{ minHeight: 34, display: 'flex', alignItems: 'center' }}>
            {row.product.name}
          </Typography>
        ),
    },
    {
      key: 'qty',
      header: 'Штук',
      width: 88,
      align: 'right',
      render: (row) => <QtyCell value={row.kind === 'container' ? row.qty : row.placement.qty} />,
    },
    {
      key: 'actions',
      header: '',
      width: 92,
      align: 'right',
      render: (row) =>
        row.kind === 'container' ? (
          <IconAction
            title={`Открыть ${CONTAINER_TITLE[row.container.kind].toLowerCase()} ${row.container.code}`}
            onClick={() =>
              onEnter({ id: row.container.id, code: row.container.code, kind: row.container.kind })
            }
            testId={`sorting-enter-${row.container.id}`}
          >
            <ChevronRight fontSize="small" />
          </IconAction>
        ) : (
          <Stack direction="row" spacing={0.25} sx={{ justifyContent: 'flex-end' }}>
            <IconAction
              title="Убрать одну штуку"
              onClick={() => onChangeQty(row.product.id, row.placement.qty - 1)}
              testId={`sorting-minus-${row.product.id}`}
            >
              <Typography sx={{ fontWeight: 700, lineHeight: 1 }}>−</Typography>
            </IconAction>
            <IconAction
              title="Снять — вернётся в «Осталось разложить»"
              onClick={() => onRemove(row.product.id)}
              testId={`sorting-remove-${row.product.id}`}
            >
              <CloseOutlined fontSize="small" />
            </IconAction>
          </Stack>
        ),
    },
  ]

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        // Вся панель — цель для того, что несут: попасть в неё проще, чем в строку.
        outline:
          carried && canDropInto(carried, place, containers)
            ? `2px dashed ${alpha(theme.palette.primary.main, 0.5)}`
            : 'none',
        outlineOffset: '-4px',
      }}
      onDragOver={(event) => {
        if (carried && canDropInto(carried, place, containers)) event.preventDefault()
      }}
      onDrop={() => onDropHere(place)}
      data-testid="sorting-active-cell"
    >
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          {path.map((step, index) => (
            <Stack key={step.id} direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
              {index > 0 ? <ChevronRight fontSize="small" sx={{ color: 'text.disabled' }} /> : null}
              <Box
                role="button"
                tabIndex={0}
                onClick={() => onLeaveTo(index)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') onLeaveTo(index)
                }}
                sx={{ cursor: index === path.length - 1 ? 'default' : 'pointer' }}
                data-testid={`sorting-crumb-${step.id}`}
              >
                <Typography
                  variant={index === path.length - 1 ? 'h6' : 'body2'}
                  sx={{ color: index === path.length - 1 ? 'text.primary' : 'text.secondary' }}
                >
                  {index === 0 ? step.code : `${CONTAINER_TITLE[step.kind as ContainerKind]} ${step.code}`}
                </Typography>
              </Box>
            </Stack>
          ))}
          <StatusChip
            label={here > 0 ? `положено ${here} шт` : 'пока пусто'}
            tone={here > 0 ? 'ok' : 'neutral'}
            testId="sorting-put-here"
          />
          <Box sx={{ flexGrow: 1 }} />
          <PrintAction what="ШК ячейки" placement="row" onClick={onPrint} testId="sorting-print" />
        </Stack>

        {cell && path.length === 1 ? (
          <Typography variant="body2" color="text.secondary">
            {cell.occupied.length > 0
              ? `Уже лежит: ${cell.occupied.map((one) => `${one.name} — ${one.qty} шт`).join(', ')}`
              : 'Ячейка была пустой.'}
          </Typography>
        ) : null}

        <DataTable
          testId="sorting-cell-rows"
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.key}
          drag={{
            active: carried !== null,
            canDrag: (row) => row.kind === 'container',
            canDrop: (row) =>
              row.kind === 'container' &&
              carried !== null &&
              canDropInto(
                carried,
                { id: row.container.id, code: row.container.code, kind: row.container.kind },
                containers,
              ),
            onDragStart: (row) => {
              if (row.kind === 'container') onDragContainer(row.container)
            },
            onDragEnd,
            onDrop: (row) => {
              if (row.kind === 'container') {
                onDropHere({ id: row.container.id, code: row.container.code, kind: row.container.kind })
              }
            },
          }}
          empty={{
            title: 'Здесь пока ничего нет',
            hint: 'Пикните товар, перетащите строку слева или создайте палету и короб.',
          }}
        />

        <Stack direction="row" spacing={1} sx={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          <Stack direction="row" spacing={1}>
            {canCreate.map((kind) => (
              <SecondaryAction
                key={kind}
                onClick={() => onCreate(kind)}
                data-testid={`sorting-create-${kind}`}
              >
                {kind === 'pallet' ? 'Новая палета' : 'Новый короб'}
              </SecondaryAction>
            ))}
          </Stack>
          <PrimaryAction
            onClick={onCommit}
            disabledReason={here === 0 ? 'В это место ничего не положено' : undefined}
            data-testid="sorting-commit"
          >
            Записать ячейку
          </PrimaryAction>
        </Stack>
      </Stack>
    </Paper>
  )
}
