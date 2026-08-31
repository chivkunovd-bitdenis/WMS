import { describe, expect, it } from 'vitest'

import {
  containerTotalForProduct,
  looseQtyFromDisplayedTotal,
  scanErrorMessageRu,
} from './inboundReceivingHelpers'

describe('scanErrorMessageRu', () => {
  it('maps inbound receiving service codes to human messages', () => {
    expect(scanErrorMessageRu('product_seller_mismatch')).toContain('другому селлеру')
    expect(scanErrorMessageRu('mixed_seller_lines')).toContain('нельзя смешивать')
    expect(scanErrorMessageRu('not_verifying')).toContain('не открыта')
    // Формулировку сменили в 6cc1eed: ручное создание товара при приёмке больше не предлагается.
    expect(scanErrorMessageRu('product_not_in_seller_catalog')).toContain('каталоге селлера')
  })

  it('does not leak raw fallback codes', () => {
    expect(scanErrorMessageRu('unexpected_backend_code')).toBe(
      'Не удалось выполнить действие. Проверьте заявку и попробуйте ещё раз.',
    )
  })
})

describe('manual inbound actual quantity with containers', () => {
  const line = { product_id: 'product-1', actual_qty: 0 }
  const boxes = [{ lines: [{ product_id: 'product-1', quantity: 2 }] }]
  const cargoPlaces = [{ lines: [{ product_id: 'product-1', quantity: 3 }] }]

  it('subtracts both boxes and cargo places from the displayed total', () => {
    expect(containerTotalForProduct(boxes, cargoPlaces, line.product_id)).toBe(5)
    expect(looseQtyFromDisplayedTotal(8, line, boxes, cargoPlaces)).toBe(3)
  })

  it('rejects a displayed total below already containerized quantity', () => {
    expect(looseQtyFromDisplayedTotal(4, line, boxes, cargoPlaces)).toBeNull()
  })
})
