import { describe, expect, it } from 'vitest'

import { scanErrorMessageRu } from './inboundReceivingHelpers'

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
