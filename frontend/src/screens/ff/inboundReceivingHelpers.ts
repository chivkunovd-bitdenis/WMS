export type InboundBoxLineRef = {
  product_id: string
  quantity: number
}

export type InboundBoxRef = {
  lines: InboundBoxLineRef[]
}

export type InboundLineRef = {
  product_id: string
  actual_qty: number | null
  effective_actual_qty?: number | null
}

export function isReceivingStatus(status: string): boolean {
  return status === 'receiving' || status === 'primary_accepted' || status === 'verifying'
}

export function isSortingStatus(status: string): boolean {
  return status === 'sorting' || status === 'verified'
}

export function isDoneStatus(status: string): boolean {
  return status === 'done' || status === 'posted'
}

export function inboundStatusRu(status: string): string {
  if (status === 'draft') return 'Черновик'
  if (status === 'submitted') return 'Передано на склад'
  if (isReceivingStatus(status)) return 'Приёмка'
  if (isSortingStatus(status)) return 'В сортировке'
  if (isDoneStatus(status)) return 'Оприходовано'
  return status
}

export function boxTotalForProduct(boxes: InboundBoxRef[], productId: string): number {
  let sum = 0
  for (const box of boxes) {
    const ln = box.lines.find((l) => l.product_id === productId)
    if (ln) {
      sum += ln.quantity
    }
  }
  return sum
}

/** Mirrors backend effective_actual_qty: API field during receiving, else loose + boxes. */
export function effectiveActualQty(
  line: InboundLineRef,
  boxes: InboundBoxRef[],
  requestStatus?: string,
): number {
  if (line.effective_actual_qty != null) {
    return line.effective_actual_qty
  }
  const loose = line.actual_qty ?? 0
  if (requestStatus != null && (isSortingStatus(requestStatus) || isDoneStatus(requestStatus))) {
    return loose
  }
  return loose + boxTotalForProduct(boxes, line.product_id)
}

/** Convert displayed total (what user edits) to loose qty for PATCH while boxes exist. */
export function looseQtyFromDisplayedTotal(
  displayedTotal: number,
  line: InboundLineRef,
  boxes: InboundBoxRef[],
): number {
  const boxTotal = boxTotalForProduct(boxes, line.product_id)
  if (boxTotal <= 0) {
    return displayedTotal
  }
  return Math.max(0, displayedTotal - boxTotal)
}

export function scanErrorMessageRu(code: string): string {
  if (code === 'product_not_on_request' || code === 'barcode_unknown') {
    return 'Товар не найден в этой поставке.'
  }
  if (code === 'barcode_empty') {
    return 'Введите штрихкод.'
  }
  if (code === 'open_box_exists') {
    return 'Сначала закройте открытый короб.'
  }
  return code
}
