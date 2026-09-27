import type { GoodsLine, Holder } from './objectsStub'

export type ScanResult = {
  reload: boolean
  remaining_qty?: number | null
  source_id: string | null
  target_id: string | null
  product_id: string | null
  target_holder: Holder
}

/** Only a newly committed unit is applied; a replay gets a canonical read. */
export function applyScanResult(lines: GoodsLine[], result: ScanResult): GoodsLine[] | null {
  const source = lines.find((line) => line.id === result.source_id)
  if (result.reload || !source || source.qty < 1 || !result.target_id || !result.product_id || !result.target_holder) return null
  const target = lines.find((line) => line.id === result.target_id)
  const next = lines.flatMap((line) => {
    if (line === source) return line.qty === 1 ? [] : [{ ...line, qty: line.qty - 1 }]
    return [{ ...line, qty: line.qty + (line === target ? 1 : 0) }]
  })
  if (!target) next.push({ id: result.target_id, productId: result.product_id, holder: result.target_holder, qty: 1 })
  return next
}
