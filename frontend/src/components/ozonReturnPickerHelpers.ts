import type { StatusTone } from '../ui-kit'
import type { OzonReturnPreviewGroup } from './OzonReturnPickerDialog'

const GIVEOUT_STATUS: Record<string, { label: string; tone: StatusTone }> = {
  GIVEOUT_STATUS_CREATED: { label: 'Создана', tone: 'neutral' },
  GIVEOUT_STATUS_APPROVED: { label: 'Одобрена', tone: 'ok' },
  GIVEOUT_STATUS_COMPLETED: { label: 'Завершена', tone: 'ok' },
  GIVEOUT_STATUS_CANCELLED: { label: 'Отменена', tone: 'stop' },
  created: { label: 'Создана', tone: 'neutral' },
  approved: { label: 'Одобрена', tone: 'ok' },
  completed: { label: 'Завершена', tone: 'ok' },
  cancelled: { label: 'Отменена', tone: 'stop' },
}

export function ozonGiveoutStatus(status: string): {
  label: string
  tone: StatusTone
} {
  return GIVEOUT_STATUS[status] ?? { label: status || 'Неизвестно', tone: 'neutral' }
}

export function formatOzonUtilizationDate(value: string | null): string | null {
  if (!value) return null
  const date = new Date(`${value.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
  }).format(date)
}

export function isOzonReturnUrgent(value: string | null, now = new Date()): boolean {
  if (!value) return false
  const deadline = new Date(`${value.slice(0, 10)}T23:59:59`)
  if (Number.isNaN(deadline.getTime())) return false
  const msUntilDeadline = deadline.getTime() - now.getTime()
  return msUntilDeadline >= 0 && msUntilDeadline < 7 * 24 * 60 * 60 * 1000
}

export function filterOzonReturnGroups(
  groups: OzonReturnPreviewGroup[],
  search: string,
): OzonReturnPreviewGroup[] {
  const normalized = search.trim().toLocaleLowerCase('ru-RU')
  if (!normalized) return groups
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) =>
        [item.product_name, item.offer_id, item.ozon_sku, item.return_barcode]
          .filter((value): value is string | number => value != null)
          .join(' ')
          .toLocaleLowerCase('ru-RU')
          .includes(normalized),
      ),
    }))
    .filter((group) => group.items.length > 0)
}

export function ozonReturnGroupAt(
  groups: OzonReturnPreviewGroup[],
  lines: { id: string }[],
  index: number,
): { group?: OzonReturnPreviewGroup; showHeader: boolean } {
  const findGroup = (lineId?: string) =>
    lineId
      ? groups.find((group) =>
          group.items.some((item) => item.inbound_line_id === lineId),
        )
      : undefined
  const group = findGroup(lines[index]?.id)
  const previousGroup = findGroup(lines[index - 1]?.id)
  return { group, showHeader: group != null && group.giveout_id !== previousGroup?.giveout_id }
}

export function ozonReturnUnrepresentedGroups(
  groups: OzonReturnPreviewGroup[],
  lines: { id: string }[],
): OzonReturnPreviewGroup[] {
  const represented = new Set(
    lines
      .map((line) =>
        groups.find((group) =>
          group.items.some((item) => item.inbound_line_id === line.id),
        )?.giveout_id,
      )
      .filter((giveoutId): giveoutId is number => giveoutId != null),
  )
  return groups.filter((group) => !represented.has(group.giveout_id))
}
