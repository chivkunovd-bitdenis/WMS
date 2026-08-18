import { useMemo, useSyncExternalStore } from 'react'
import { Chip, Tooltip } from '@mui/material'
import type { ChipProps } from '@mui/material'

// Настенные часы как внешний источник: React подписывается на них штатно, без setState
// внутри эффекта и без вызова Date.now() в теле рендера. Снимок округляем до шага тика,
// иначе useSyncExternalStore будет считать значение изменившимся на каждом рендере.
const CLOCK_TICK_MS = 30_000
const readClock = () => Math.floor(Date.now() / CLOCK_TICK_MS) * CLOCK_TICK_MS

// eslint-disable-next-line react-refresh/only-export-components -- pure clock arithmetic is covered by FbsChips.test.ts.
export function resolveDeadlineNow(
  serverNow: string | null | undefined,
  clientNow: number,
  clientAnchor: number,
) {
  const serverMs = serverNow ? Date.parse(serverNow) : Number.NaN
  return Number.isFinite(serverMs) ? serverMs + (clientNow - clientAnchor) : clientNow
}

function createDeadlineClock(serverNow: string | null | undefined) {
  let clientAnchor: number | null = null
  const serverMs = serverNow ? Date.parse(serverNow) : Number.NaN

  const getSnapshot = () => {
    const clientNow = readClock()
    if (clientAnchor === null) return clientNow
    return Number.isFinite(serverMs) ? serverMs + (clientNow - clientAnchor) : clientNow
  }

  return {
    subscribe(onStoreChange: () => void) {
      clientAnchor = readClock()
      onStoreChange()
      const timer = window.setInterval(onStoreChange, CLOCK_TICK_MS)
      return () => window.clearInterval(timer)
    },
    getSnapshot,
    getServerSnapshot: () => (Number.isFinite(serverMs) ? serverMs : 0),
  }
}

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

// WMS рассчитывает срок отгрузки как 120 часов с createdAt заказа WB.
export function DeadlinePill({
  deadlineAt,
  cancelled,
  serverNow,
}: {
  deadlineAt: string | null
  cancelled?: boolean
  serverNow?: string | null
}) {
  // Серверное время — базовая отметка, а клиентские часы измеряют только прошедшее после
  // получения этой отметки время. Поэтому clock-skew оператора не меняет старт дедлайна,
  // но плашка продолжает обновляться между ответами worklist.
  const clock = useMemo(() => createDeadlineClock(serverNow), [serverNow])
  const now = useSyncExternalStore(clock.subscribe, clock.getSnapshot, clock.getServerSnapshot)

  if (cancelled || !deadlineAt) {
    return (
      <Chip size="small" variant="outlined" color="default" label="—" data-testid="fbs-deadline-pill" />
    )
  }
  const msLeft = new Date(deadlineAt).getTime() - now
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
    <Tooltip title={`Отгрузить до ${new Date(deadlineAt).toLocaleString('ru-RU')}. Рассчитано WMS: 120 часов с момента создания заказа в WB.`}>
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

const STICKER_STATUS_META: Record<string, { label: string; color: ChipProps['color'] }> = {
  not_requested: { label: 'Не напечатан', color: 'default' },
  requesting: { label: 'Готовим к печати', color: 'info' },
  ready: { label: 'Не напечатан', color: 'default' },
  print_opened: { label: 'Напечатан', color: 'primary' },
  applied: { label: 'Нанесён', color: 'success' },
  error: { label: 'Ошибка', color: 'error' },
}

export function FbsStickerStatusChip({ status }: { status: string }) {
  const meta = STICKER_STATUS_META[status] ?? {
    label: 'Статус уточняется',
    color: 'default' as ChipProps['color'],
  }
  return (
    <Chip
      size="small"
      variant="outlined"
      color={meta.color}
      label={meta.label}
      data-testid="fbs-sticker-status-chip"
      data-status={status}
    />
  )
}

type MarkingState = { status: string }

export function FbsMarkingStatusChip({ required, states }: { required: string[]; states: MarkingState[] }) {
  if (required.length === 0) {
    return <Chip size="small" variant="outlined" label="Не требуется" data-testid="fbs-marking-status-chip" />
  }
  const statuses = states.map((state) => state.status)
  const hasError = statuses.some((status) => ['rejected', 'replacement_required', 'error'].includes(status))
  const acceptedCount = statuses.filter((status) => ['accepted', 'assigned', 'allowed_without_check', 'ok'].includes(status)).length
  const ready = acceptedCount >= required.length
  const meta = hasError
    ? { label: 'Требует исправления', color: 'error' as ChipProps['color'] }
    : ready
      ? { label: 'Проверена', color: 'success' as ChipProps['color'] }
      : { label: 'Не проверена', color: 'warning' as ChipProps['color'] }
  return (
    <Chip
      size="small"
      variant="outlined"
      color={meta.color}
      label={meta.label}
      data-testid="fbs-marking-status-chip"
    />
  )
}

// Статус проверки идентификатора (КИЗ/УИН/IMEI/GTIN) заказа — поле check_status в API.
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
