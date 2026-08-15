export const SORTING_LOCATION_CODE = '__SORTING__'

export function storageLocationLabel(code: string): string {
  return code === SORTING_LOCATION_CODE ? 'Сортировка' : code
}

export type InboundQueueRow = {
  id: string
  status: string
  operation_type?: string | null
  line_count: number
  planned_delivery_date: string | null
  created_by_seller_id?: string | null
  seller_name?: string | null
  seller_id?: string | null
  document_number?: string | null
  display_number?: string | null
  waybill_number?: string | null
  product_names?: string[]
  goods_qty_total?: number | null
  planned_box_count?: number | null
  actual_box_count?: number | null
  boxes_discrepancy?: boolean
  has_discrepancy?: boolean
  created_at?: string
  sorting_remaining_qty?: number
}

export function filterReceptionQueue(rows: InboundQueueRow[]): InboundQueueRow[] {
  return rows
}

export function filterSortingQueue(rows: InboundQueueRow[]): InboundQueueRow[] {
  return rows.filter(
    (r) =>
      (r.status === 'sorting' || r.status === 'verified') &&
      (r.sorting_remaining_qty ?? 0) > 0,
  )
}
