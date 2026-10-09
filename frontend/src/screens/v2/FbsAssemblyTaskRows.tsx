import { Fragment } from 'react'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
  TableCell,
  TableRow,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { plural } from '../../utils/plural'
import { groupFbsAssemblyTaskSupplies } from './fbsSupplyAssembly'
import type { FbsAssemblyTask, FbsSupplyWorklistItem } from './fbsApi'

type Props = {
  tasks: FbsAssemblyTask[]
  supplies: FbsSupplyWorklistItem[]
  printingSupplyId: string | null
  onOpenAssembly: (supplyIds: string[]) => void
  onOpenSupply: (supplyId: string) => void
  onPrintSupply: (supply: FbsSupplyWorklistItem) => void
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function supplyStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: 'Черновик',
    assembling: 'В работе',
    packed: 'Готова к сдаче',
    shipped: 'Отгружена',
    acceptance_in_progress: 'Идёт приёмка',
    in_delivery: 'В доставке',
    done: 'Завершена',
  }
  return labels[status] ?? 'Статус уточняется'
}

function supplyStatusColor(status: string): 'default' | 'primary' | 'success' | 'warning' {
  if (status === 'done') return 'success'
  if (['shipped', 'acceptance_in_progress', 'in_delivery'].includes(status)) return 'primary'
  if (status === 'draft' || status === 'assembling' || status === 'packed') return 'warning'
  return 'default'
}

function PickedChip({ picked, total, testId }: { picked: number; total: number; testId: string }) {
  if (total <= 0 || picked !== total) return null
  return (
    <Chip
      size="small"
      variant="outlined"
      color="success"
      label="Подобрано"
      data-testid={testId}
    />
  )
}

function SupplyRow({
  supply,
  nested = false,
  lastNested = false,
  assemblyTaskId,
  printingSupplyId,
  onOpenSupply,
  onPrintSupply,
}: {
  supply: FbsSupplyWorklistItem
  nested?: boolean
  lastNested?: boolean
  assemblyTaskId?: string
  printingSupplyId: string | null
  onOpenSupply: (supplyId: string) => void
  onPrintSupply: (supply: FbsSupplyWorklistItem) => void
}) {
  return (
    <TableRow
      hover
      onClick={() => onOpenSupply(supply.id)}
      sx={(theme) => ({
        cursor: 'pointer',
        '& > td': {
          py: 1,
          ...(nested ? {
            bgcolor: alpha(theme.palette.primary.main, 0.035),
            '&:first-of-type': {
              borderLeft: `2px solid ${theme.palette.primary.main}`,
            },
            '&:last-of-type': {
              borderRight: `2px solid ${theme.palette.primary.main}`,
            },
            ...(lastNested ? {
              borderBottom: `2px solid ${theme.palette.primary.main}`,
            } : {}),
          } : {}),
        },
        ...(nested ? {
          '&:hover > td': {
            bgcolor: alpha(theme.palette.primary.main, 0.075),
          },
        } : {}),
      })}
      data-testid={`fbs-18-supply-${supply.id}`}
      data-assembly-task-id={assemblyTaskId}
    >
      <TableCell sx={nested ? { pl: 4 } : undefined}>
        <Typography variant="body2" sx={{ fontWeight: 750 }}>
          {supply.name}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {supply.marketplace === 'ozon' ? 'Ozon' : `WB №${supply.wb_supply_id}`}
        </Typography>
      </TableCell>
      <TableCell>{supply.seller.name}</TableCell>
      <TableCell>
        <Typography variant="body2" sx={{ fontWeight: 650 }}>
          {supply.wb_warehouse.name || (
            supply.marketplace === 'ozon'
              ? 'Склад Ozon'
              : `WB ${supply.wb_warehouse.id}`
          )}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          WMS: {supply.wms_warehouse.name}
        </Typography>
      </TableCell>
      <TableCell>{supply.orders_count} / {supply.units_count}</TableCell>
      <TableCell>{supply.boxes_count}</TableCell>
      <TableCell>
        <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
          <Chip
            size="small"
            variant="outlined"
            color={supplyStatusColor(supply.status)}
            label={supplyStatusLabel(supply.status)}
            data-testid="fbs-18-supply-status"
          />
          <PickedChip
            picked={supply.picked_units_count}
            total={supply.units_count}
            testId={`fbs-supply-picked-${supply.id}`}
          />
        </Stack>
      </TableCell>
      <TableCell>{supply.planned_shipment_date ? formatDateTime(supply.planned_shipment_date) : '—'}</TableCell>
      <TableCell align="right" onClick={(event) => event.stopPropagation()}>
        <Button
          size="small"
          variant="outlined"
          startIcon={printingSupplyId === supply.id
            ? <CircularProgress size={14} />
            : <PrintOutlinedIcon />}
          disabled={Boolean(printingSupplyId)}
          onClick={() => onPrintSupply(supply)}
          data-testid={`fbs-supply-qr-print-${supply.id}`}
        >
          {supply.marketplace === 'ozon' ? 'Этикетки коробов' : 'QR'}
        </Button>
      </TableCell>
    </TableRow>
  )
}

/** WMS-588 R3: строка задания и прежние строки его поставок под ней. */
export function FbsAssemblyTaskRows({
  tasks,
  supplies,
  printingSupplyId,
  onOpenAssembly,
  onOpenSupply,
  onPrintSupply,
}: Props) {
  const grouped = groupFbsAssemblyTaskSupplies(tasks, supplies)
  return (
    <>
      {grouped.groups.map(({ task, supplies: taskSupplies }) => {
        const totalOrders = task.supplies.reduce((sum, supply) => sum + supply.orders_count, 0)
        const totalUnits = task.supplies.reduce((sum, supply) => sum + supply.units_count, 0)
        const pickedUnits = task.supplies.reduce((sum, supply) => sum + supply.picked_units_count, 0)
        const packed = task.supplies.reduce((sum, supply) => sum + supply.packed_count, 0)
        const sellers = [...new Set(task.supplies.map((supply) => supply.seller.name))]
        return (
          <Fragment key={task.id}>
            <TableRow
              hover
              onClick={() => onOpenAssembly(task.supplies.map((supply) => supply.id))}
              sx={(theme) => ({
                cursor: 'pointer',
                '& > td': {
                  py: 1.25,
                  bgcolor: alpha(theme.palette.primary.main, 0.12),
                  borderTop: `2px solid ${theme.palette.primary.main}`,
                  borderBottom: `1px solid ${alpha(theme.palette.primary.main, 0.35)}`,
                  '&:first-of-type': {
                    borderLeft: `2px solid ${theme.palette.primary.main}`,
                  },
                  '&:last-of-type': {
                    borderRight: `2px solid ${theme.palette.primary.main}`,
                  },
                },
                '&:hover > td': {
                  bgcolor: alpha(theme.palette.primary.main, 0.18),
                },
              })}
              data-testid={`fbs-assembly-task-${task.id}`}
            >
              <TableCell colSpan={8}>
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={{ xs: 0.5, md: 3 }}
                  sx={{ alignItems: { xs: 'flex-start', md: 'center' } }}
                >
                  <Box sx={{ minWidth: 210 }}>
                    <Stack direction="row" spacing={0.75} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                      <Typography variant="body2" sx={{ fontWeight: 800 }}>
                        Сборочное задание {task.number}
                      </Typography>
                      <PickedChip
                        picked={pickedUnits}
                        total={totalUnits}
                        testId={`fbs-assembly-task-picked-${task.id}`}
                      />
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      {formatDateTime(task.created_at)}
                    </Typography>
                  </Box>
                  <Typography variant="body2" sx={{ minWidth: 100 }}>
                    {task.supplies.length} {plural(task.supplies.length, ['поставка', 'поставки', 'поставок'])}
                  </Typography>
                  <Typography variant="body2" sx={{ minWidth: 150 }}>
                    {sellers.join(', ')}
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 650 }}>
                    Подбор {pickedUnits} / {totalUnits} · Упаковка {packed} / {totalOrders}
                  </Typography>
                </Stack>
              </TableCell>
            </TableRow>
            {taskSupplies.map((supply, index) => (
              <SupplyRow
                key={supply.id}
                supply={supply}
                nested
                lastNested={index === taskSupplies.length - 1}
                assemblyTaskId={task.id}
                printingSupplyId={printingSupplyId}
                onOpenSupply={onOpenSupply}
                onPrintSupply={onPrintSupply}
              />
            ))}
          </Fragment>
        )
      })}
      {grouped.standalone.map((supply) => (
        <SupplyRow
          key={supply.id}
          supply={supply}
          printingSupplyId={printingSupplyId}
          onOpenSupply={onOpenSupply}
          onPrintSupply={onPrintSupply}
        />
      ))}
    </>
  )
}
