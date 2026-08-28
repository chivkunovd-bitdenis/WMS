import type { WbProductCatalogRow } from '../../types/wbProductCatalog'
import { isDoneStatus, isReceivingStatus, isSortingStatus } from './inboundReceivingHelpers'

export type LocationRow = { id: string; code: string; warehouse_id: string; barcode: string }
export type WarehouseRow = { id: string; name: string; code: string }
export type SellerRow = { id: string; name: string }

export type InboundBoxLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  posted_qty?: number
  remaining_qty?: number
}

export type InboundBox = {
  id: string
  box_number: number
  internal_barcode: string
  label_printed_at: string | null
  intake_opened_at: string | null
  intake_closed_at: string | null
  is_open: boolean
  remaining_qty?: number
  lines: InboundBoxLine[]
}

export type InboundCargoPlace = {
  id: string
  place_number: number
  internal_barcode: string
  label_printed_at: string | null
  created_at: string
}

export type InboundLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  wb_barcode: string | null
  requires_honest_sign: boolean
  length_mm: number | null
  width_mm: number | null
  height_mm: number | null
  weight_g: number | null
  volume_liters: number | null
  added_by_fulfillment: boolean
  expected_qty: number
  actual_qty: number | null
  effective_actual_qty?: number | null
  defective_qty?: number
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

export type DiscrepancyActLine = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  inbound_intake_line_id: string | null
}

export type DiscrepancyActDetail = {
  id: string
  status: string
  inbound_intake_request_id: string | null
  created_at: string
  lines: DiscrepancyActLine[]
}

export type InboundDetail = {
  id: string
  document_number: string | null
  display_number?: string | null
  public_number?: string | null
  human_number?: string | null
  waybill_number?: string | null
  warehouse_id: string
  status: string
  operation_type: 'inbound' | 'return'
  marketplace?: 'wildberries' | 'ozon' | null
  marketplace_warning?: string | null
  planned_delivery_date: string | null
  planned_box_count: number | null
  actual_box_count: number | null
  boxes_discrepancy: boolean
  has_discrepancy: boolean
  seller_id?: string | null
  seller_name?: string | null
  created_by_seller_id?: string | null
  created_at?: string | null
  distribution_completed_at: string | null
  sorting_remaining_qty?: number
  boxes: InboundBox[]
  cargo_places: InboundCargoPlace[]
  lines: InboundLine[]
}

export type DistributionLineOut = {
  id: string
  product_id: string
  storage_location_id: string
  storage_location_code: string
  quantity: number
  created_at: string
}

export type DistributionLineDraft = {
  box_id: string
  product_id: string
  storage_location_id: string
  quantity: string
}

export type CellLocationHint = {
  storage_location_id: string
  storage_location_code: string
  quantity: number
  reserved: number
  available: number
}

export type WbCatalogRow = WbProductCatalogRow
export type InboundRequestWorkspace = 'reception' | 'sorting' | 'full'

export type FfInboundRequestViewProps = {
  token: string
  requestId: string
  isFulfillmentAdmin: boolean
  workspace?: InboundRequestWorkspace
  sellers?: SellerRow[]
  onClose: () => void
  onDirtyChange?: (dirty: boolean) => void
  addressStorageEnabled?: boolean
}

export function discrepancyActStatusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'confirmed') return 'Передан на FF'
  if (status === 'approved') return 'Утверждено'
  if (status === 'rejected') return 'Отклонено'
  return status
}

export function discrepancyActTitle(createdAt: string): string {
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return 'Акт расхождения'
  return `Акт от ${new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)}`
}

export function signedQty(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}

export function inboundWorkspaceTitle(workspace: InboundRequestWorkspace): string {
  return workspace === 'sorting' ? 'Сортировка' : 'Приёмка'
}

export function formatLineDiscrepancy(expectedQty: number, actualQty: number): string | null {
  const delta = actualQty - expectedQty
  if (delta > 0) return `Излишек ${delta}`
  if (delta < 0) return `Недостача ${Math.abs(delta)}`
  return null
}

export function inboundStatusChipColor(
  status: string,
): 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'info' {
  if (status === 'draft') return 'default'
  if (status === 'submitted') return 'info'
  if (isReceivingStatus(status)) return 'warning'
  if (isSortingStatus(status)) return 'secondary'
  if (isDoneStatus(status)) return 'success'
  return 'primary'
}
