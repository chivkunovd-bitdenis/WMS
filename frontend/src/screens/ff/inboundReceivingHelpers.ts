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

/** Mirrors backend effective_actual_qty during receiving. */
export function effectiveActualQty(line: InboundLineRef, boxes: InboundBoxRef[]): number {
  const loose = line.actual_qty ?? 0
  const boxTotal = boxTotalForProduct(boxes, line.product_id)
  if (boxTotal <= 0) {
    return loose
  }
  if (loose > boxTotal) {
    return loose + boxTotal
  }
  if (loose < boxTotal) {
    return boxTotal + loose
  }
  return boxTotal
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
