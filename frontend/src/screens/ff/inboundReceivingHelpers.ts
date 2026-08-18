import { inboundOperationTypeReceptionLabel } from '../../utils/inboundOperationType'
import { plural } from '../../utils/plural'

export type InboundBoxLineRef = {
  product_id: string
  quantity: number
}

export type InboundBoxRef = {
  lines: InboundBoxLineRef[]
}

export type InboundLineRef = {
  sku_code?: string
  product_name?: string
  expected_qty?: number
  product_id: string
  actual_qty: number | null
  effective_actual_qty?: number | null
  volume_liters?: number | null
  weight_g?: number | null
}

export type InboundSummaryRef = {
  display_number?: string | null
  public_number?: string | null
  human_number?: string | null
  document_number?: string | null
  waybill_number?: string | null
  line_count?: number
  planned_box_count?: number | null
  actual_box_count?: number | null
  boxes_discrepancy?: boolean
  has_discrepancy?: boolean
  goods_qty_total?: number | null
  expected_qty_total?: number | null
  units_total?: number | null
  operation_type?: string | null
}

export type InboundReceivingTotals = {
  expectedQty: number
  acceptedQty: number
  plannedBoxes: number | null
  actualBoxes: number
  totalVolumeLiters: number
  totalWeightKg: number
  hasKnownWeight: boolean
  lineDiscrepancyCount: number
  hasBoxDiscrepancy: boolean
  hasAnyDiscrepancy: boolean
}

export type InboundDiscrepancyLine = {
  productId: string
  skuCode: string
  productName: string
  expectedQty: number
  acceptedQty: number
  shortage: number
  surplus: number
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

export function integerQtyError(raw: string): string | null {
  const value = raw.trim()
  if (value === '') return 'Укажите целое количество.'
  if (!/^\d+$/.test(value)) return 'Только целое количество без дробей.'
  return null
}

export function parseIntegerQty(raw: string): number | null {
  if (integerQtyError(raw) != null) return null
  return Number(raw.trim())
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
    return 'Товар не найден в документе. Нажмите «Добавить товар» и выберите его из каталога селлера.'
  }
  if (code === 'product_not_in_seller_catalog') {
    return 'Товар не найден в каталоге селлера. Добавление нового товара будет отдельной задачей.'
  }
  if (code === 'product_seller_mismatch' || code === 'mixed_seller_lines') {
    return 'Товар относится к другому селлеру. В одной приёмке нельзя смешивать селлеров.'
  }
  if (code === 'not_verifying') {
    return 'Приёмка сейчас не открыта для проверки.'
  }
  if (code === 'product_not_found') {
    return 'Товар не найден.'
  }
  if (code === 'invalid_qty') {
    return 'Количество должно быть больше нуля.'
  }
  if (code === 'nothing_to_receive') {
    return 'Нет товаров для приёмки.'
  }
  if (code === 'actual_below_posted') {
    return 'Нельзя уменьшить принятое количество ниже уже размещённого.'
  }
  if (code === 'barcode_empty') {
    return 'Введите штрихкод.'
  }
  if (code === 'open_box_exists') {
    return 'Сначала закройте открытый короб.'
  }
  if (code === 'box_not_empty') {
    return 'Нельзя удалить короб с товарами.'
  }
  return 'Не удалось выполнить действие. Проверьте заявку и попробуйте ещё раз.'
}

export function inboundQueueDocumentLabel(row: InboundSummaryRef): string {
  const operationLabel = inboundOperationTypeReceptionLabel(row.operation_type)
  const preferred = row.display_number ?? row.public_number ?? row.human_number
  if (preferred?.trim()) return `${operationLabel} № ${preferred.trim().replace(/^№\s*/, '')}`
  if (row.document_number?.trim()) return `${operationLabel} № ${row.document_number.trim()}`
  return `${operationLabel} № —`
}

export function inboundQueueUnitsLabel(row: InboundSummaryRef): string {
  const exact = row.goods_qty_total ?? row.expected_qty_total ?? row.units_total
  if (typeof exact === 'number' && Number.isFinite(exact)) {
    return `${exact} ед.`
  }
  const lines = row.line_count ?? 0
  if (lines <= 0) return '0 ед.'
  return `от ${lines} ед.`
}

export function inboundQueueBoxesLabel(row: InboundSummaryRef): string {
  const actual = row.actual_box_count
  const planned = row.planned_box_count
  if (planned == null) {
    if (actual == null) return 'нет данных'
    return `${actual} ${plural(actual, ['короб', 'короба', 'коробов'])}`
  }
  if (actual == null) {
    // Фактическое число коробов неизвестно — показываем только план понятной формулировкой
    // ("3 короба"), а не "? из 3 коробов": знак вопроса читается как поломка экрана.
    return `${planned} ${plural(planned, ['короб', 'короба', 'коробов'])}`
  }
  return `${actual} из ${planned} ${plural(planned, ['короба', 'коробов', 'коробов'])}`
}

export function buildInboundReceivingTotals(
  lines: InboundLineRef[],
  boxes: InboundBoxRef[],
  status?: string,
  plannedBoxCount?: number | null,
): InboundReceivingTotals {
  let expectedQty = 0
  let acceptedQty = 0
  let totalVolumeLiters = 0
  let totalWeightKg = 0
  let hasKnownWeight = false
  let lineDiscrepancyCount = 0
  for (const line of lines) {
    const expected = line.expected_qty ?? 0
    const accepted = effectiveActualQty(line, boxes, status)
    expectedQty += expected
    acceptedQty += accepted
    if (line.volume_liters != null && Number.isFinite(line.volume_liters)) {
      totalVolumeLiters += accepted * line.volume_liters
    }
    if (line.weight_g != null && Number.isFinite(line.weight_g)) {
      hasKnownWeight = true
      totalWeightKg += (accepted * line.weight_g) / 1000
    }
    if (accepted !== expected) lineDiscrepancyCount += 1
  }
  const actualBoxes = boxes.length
  const hasBoxDiscrepancy = plannedBoxCount != null && actualBoxes !== plannedBoxCount
  return {
    expectedQty,
    acceptedQty,
    plannedBoxes: plannedBoxCount ?? null,
    actualBoxes,
    totalVolumeLiters,
    totalWeightKg,
    hasKnownWeight,
    lineDiscrepancyCount,
    hasBoxDiscrepancy,
    hasAnyDiscrepancy: lineDiscrepancyCount > 0 || hasBoxDiscrepancy,
  }
}

/**
 * Formats the "Короба: X из Y" summary. When actual boxes exceed the planned
 * count, "X из Y" reads as nonsense ("2 out of 1"), so switch to an explicit
 * "created more than planned" phrasing instead of keeping the "из" wording.
 */
export function formatBoxesCountLabel(actualBoxes: number, plannedBoxes: number | null): string {
  if (plannedBoxes == null) return `${actualBoxes}`
  if (actualBoxes <= plannedBoxes) return `${actualBoxes} из ${plannedBoxes}`
  const over = actualBoxes - plannedBoxes
  return `${actualBoxes} (план ${plannedBoxes}, создано больше на ${over})`
}

export function buildInboundDiscrepancyLines(
  lines: InboundLineRef[],
  boxes: InboundBoxRef[],
  status?: string,
): InboundDiscrepancyLine[] {
  return lines
    .map((line) => {
      const expectedQty = line.expected_qty ?? 0
      const acceptedQty = effectiveActualQty(line, boxes, status)
      return {
        productId: line.product_id,
        skuCode: line.sku_code ?? 'SKU',
        productName: line.product_name ?? '',
        expectedQty,
        acceptedQty,
        shortage: Math.max(0, expectedQty - acceptedQty),
        surplus: Math.max(0, acceptedQty - expectedQty),
      }
    })
    .filter((line) => line.shortage > 0 || line.surplus > 0)
}
