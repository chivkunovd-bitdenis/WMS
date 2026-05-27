export const SORTING_LOCATION_CODE = '__SORTING__'

export function storageLocationLabel(code: string): string {
  return code === SORTING_LOCATION_CODE ? 'Сортировка' : code
}

export type InboundQueueRow = {
  id: string
  status: string
  line_count: number
  planned_delivery_date: string | null
  seller_name?: string | null
  created_at?: string
  sorting_remaining_qty?: number
}

const RECEPTION_STATUSES = new Set(['submitted', 'primary_accepted', 'verifying'])

export function filterReceptionQueue(rows: InboundQueueRow[]): InboundQueueRow[] {
  return rows.filter((r) => RECEPTION_STATUSES.has(r.status))
}

export function filterSortingQueue(rows: InboundQueueRow[]): InboundQueueRow[] {
  return rows.filter(
    (r) => r.status === 'verified' && (r.sorting_remaining_qty ?? 0) > 0,
  )
}
