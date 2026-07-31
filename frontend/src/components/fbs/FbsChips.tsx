import { Chip, Tooltip } from '@mui/material'
import type { ChipProps } from '@mui/material'

// Переиспользуемые визуальные примитивы модуля FBS (DESIGN.md §6).
// Спокойная палитра статусов: цвет несёт смысл, а не украшает.

type FbsOrderStatus =
  | 'new'
  | 'in_supply'
  | 'assembling'
  | 'packed'
  | 'in_delivery'
  | 'sorted'
  | 'done'
  | 'cancelled'
  | 'defect'

const ORDER_STATUS_META: Record<
  FbsOrderStatus,
  { label: string; color: ChipProps['color'] }
> = {
  new: { label: 'Новый', color: 'info' },
  in_supply: { label: 'В отгрузке', color: 'default' },
  assembling: { label: 'Сборка', color: 'warning' },
  packed: { label: 'Упакован', color: 'warning' },
  in_delivery: { label: 'В доставке', color: 'primary' },
  sorted: { label: 'Отсортирован', color: 'primary' },
  done: { label: 'Завершён', color: 'success' },
  cancelled: { label: 'Отменён', color: 'default' },
  defect: { label: 'Дефект', color: 'error' },
}

export function FbsStatusChip({ status }: { status: string }) {
  const meta = ORDER_STATUS_META[status as FbsOrderStatus] ?? {
    label: status,
    color: 'default' as ChipProps['color'],
  }
  return (
    <Chip
      size="small"
      variant="outlined"
      color={meta.color}
      label={meta.label}
      data-testid="fbs-status-chip"
      data-status={status}
    />
  )
}

// До дедлайна 120ч: зелёный → жёлтый → красный (просрочен) → серый (отменён/нет).
export function DeadlinePill({
  deadlineAt,
  cancelled,
}: {
  deadlineAt: string | null
  cancelled?: boolean
}) {
  if (cancelled || !deadlineAt) {
    return (
      <Chip size="small" variant="outlined" color="default" label="—" data-testid="fbs-deadline-pill" />
    )
  }
  const msLeft = new Date(deadlineAt).getTime() - Date.now()
  const hoursLeft = Math.floor(msLeft / 3_600_000)
  let color: ChipProps['color'] = 'success'
  let label = `${hoursLeft} ч`
  if (msLeft <= 0) {
    color = 'error'
    label = 'Просрочен'
  } else if (hoursLeft <= 12) {
    color = 'warning'
  } else if (hoursLeft <= 48) {
    color = 'info'
  }
  return (
    <Tooltip title={`Дедлайн: ${new Date(deadlineAt).toLocaleString('ru-RU')}`}>
      <Chip
        size="small"
        variant="outlined"
        color={color}
        label={label}
        data-testid="fbs-deadline-pill"
        data-overdue={msLeft <= 0 ? 'true' : 'false'}
      />
    </Tooltip>
  )
}

// Компактный маркер селлера — мультиселлер первого класса (DESIGN.md §1).
export function SellerBadge({ name }: { name: string | null }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      label={name ?? '—'}
      data-testid="fbs-seller-badge"
    />
  )
}

// Статус проверки идентификатора (КИЗ/УИН/IMEI/GTIN) заказа — FbsOrderMarking.check_status.
const CHECK_STATUS_META: Record<string, { label: string; color: ChipProps['color'] }> = {
  new: { label: 'Новый', color: 'default' },
  checking: { label: 'Проверяется', color: 'warning' },
  ok: { label: 'Проверен', color: 'success' },
  error: { label: 'Ошибка', color: 'error' },
  no_check: { label: 'Без проверки', color: 'default' },
}

export function MarkingCheckStatusChip({ status }: { status: string }) {
  const meta = CHECK_STATUS_META[status] ?? {
    label: status,
    color: 'default' as ChipProps['color'],
  }
  return (
    <Chip
      size="small"
      variant="outlined"
      color={meta.color}
      label={meta.label}
      data-testid="fbs-marking-check-status-chip"
      data-status={status}
    />
  )
}

const CARGO_LABEL: Record<string, string> = { mgt: 'МГТ', kgt: 'КГТ+', sgt: 'СГТ' }

export function CargoTypeChip({ cargoType }: { cargoType: string }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      label={CARGO_LABEL[cargoType] ?? cargoType}
      data-testid="fbs-cargo-chip"
    />
  )
}
