import { apiUrl } from '../api'

/** Max page size for `/pending-marking` — keeps badge count aligned with loaded rows. */
export const PENDING_MARKING_FETCH_LIMIT = 200

export type PendingMarkingLine = {
  packaging_task_id: string
  packaging_task_line_id: string
  document_number: string | null
  product_id: string
  sku_code: string
  product_name: string
  storage_location_code: string
  qty_need: number
  qty_marking_printed: number
  qty_remaining: number
  marking_available_count: number
}

export type PendingMarkingResponse = {
  rows: PendingMarkingLine[]
  total: number
}

/** Line count for badges/chips — equals table row count when total ≤ fetch limit. */
export function pendingMarkingLineCount(body: PendingMarkingResponse): number {
  return body.total
}

export async function fetchPendingMarking(
  token: string,
  options?: { limit?: number; offset?: number },
): Promise<PendingMarkingResponse> {
  const limit = options?.limit ?? PENDING_MARKING_FETCH_LIMIT
  const offset = options?.offset ?? 0
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  const res = await fetch(apiUrl(`/operations/marking-codes/pending-marking?${params}`), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    throw new Error(`pending-marking ${res.status}`)
  }
  return (await res.json()) as PendingMarkingResponse
}
