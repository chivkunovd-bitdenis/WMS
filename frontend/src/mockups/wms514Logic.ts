export type Wms514MockupModes = {
  printQr: boolean
  printChz: boolean
  reprintChz: boolean
}

export type Wms514MockupOutput = 'order_qr' | 'new_chz' | 'exact_chz_reprint'

export const WMS514_PRODUCT_BARCODE = '4680123456789'
export const WMS514_ORDER_QR = 'WB-3941200046'
export const WMS514_DIRECT_KIZ =
  '010460000000051421DIRECT51491ABCD92ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789012345678'
export const WMS514_BOUND_KIZ =
  '010460000000051421BOUND51491EFGH92ZYXWVUTSRQPONMLKJIHGFEDCBA876543210987654321'

// The configured product barcode belongs to TSHIRT_M. These are exactly the
// four existing TSHIRT_M/M rows in the scene fixture, in workspace order.
const PRODUCT_ORDER_NUMBERS = [3941200018, 3941200025, 3941200032, 3941200039]

export type Wms514ProductSimulation = {
  handled: boolean
  orderNumber?: number
  outputs: Wms514MockupOutput[]
  waitsForFullKiz: boolean
  notice?: string
  error?: string
}

export function classifyWms514MockScan(raw: string): 'order_qr' | 'full_kiz' | 'product' | 'unknown' {
  if (raw === WMS514_ORDER_QR) return 'order_qr'
  if (raw === WMS514_DIRECT_KIZ || raw === WMS514_BOUND_KIZ) return 'full_kiz'
  if (raw === WMS514_PRODUCT_BARCODE) return 'product'
  return 'unknown'
}

export function simulateWms514ProductScan(
  modes: Wms514MockupModes,
  orderIndex: number,
): Wms514ProductSimulation {
  if (!modes.printQr && !modes.printChz && !modes.reprintChz) {
    return { handled: false, outputs: [], waitsForFullKiz: false }
  }
  const orderNumber = PRODUCT_ORDER_NUMBERS[orderIndex]
  if (orderNumber == null) {
    return {
      handled: true,
      outputs: [],
      waitsForFullKiz: false,
      error: 'Подходящие единицы товара размера M в этой поставке закончились.',
    }
  }
  const outputs: Wms514MockupOutput[] = []
  if (modes.printQr) outputs.push('order_qr')
  if (modes.printChz && !modes.reprintChz) outputs.push('new_chz')
  const waitsForFullKiz = modes.reprintChz

  const result = outputs.length === 0
    ? 'автоматической печати нет'
    : outputs.map((output) => output === 'order_qr' ? 'QR' : 'новый ЧЗ').join(' → ')
  const wait = waitsForFullKiz ? ' · ожидается отдельный скан полного ЧЗ' : ''
  return {
    handled: true,
    orderNumber,
    outputs,
    waitsForFullKiz,
    notice: `Заказ WB № ${orderNumber} выбран · ${result}${wait}. Товарный ШК не печатается.`,
  }
}

export function createWms514MockupScanPrinting() {
  let productScanIndex = 0
  return {
    async handleIdleScan(raw: string, modes: Wms514MockupModes) {
      const kind = classifyWms514MockScan(raw)
      if (kind === 'full_kiz' && modes.reprintChz) {
        return {
          handled: true,
          notice: 'Точная копия отсканированного ЧЗ отправлена в печать. Новый код не выделялся.',
          outputs: ['exact_chz_reprint'] satisfies Wms514MockupOutput[],
        }
      }
      if (kind === 'product') {
        const result = simulateWms514ProductScan(modes, productScanIndex)
        if (result.orderNumber != null) productScanIndex += 1
        return result
      }
      return {
        handled: true,
        error: kind === 'order_qr'
          ? 'Известный QR должен обрабатываться существующим lookup раньше макетной печати.'
          : 'Код не распознан: используйте точный QR заказа, товарный ШК или полный тестовый ЧЗ.',
      }
    },
    async reprintBoundKiz(rawKiz: string) {
      return rawKiz === WMS514_BOUND_KIZ || rawKiz === WMS514_DIRECT_KIZ
    },
  }
}
