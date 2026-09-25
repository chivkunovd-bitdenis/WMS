import { describe, expect, it } from 'vitest'
import { PRODUCT_SCAN_AMBIGUOUS_MESSAGE } from './productScanResolver'
import { productScanAmbiguousApiMessage, readApiErrorMessage } from './readApiErrorMessage'

const reply = (detail: unknown, status = 409) =>
  new Response(JSON.stringify({ detail }), { status })

// WMS-536 R2: товарная неоднозначность показывается одним текстом во всех процессах.
describe('WMS-536 · общий текст товарной неоднозначности', () => {
  it('все серверные коды товарной неоднозначности дают один текст', async () => {
    for (const code of ['barcode_ambiguous', 'barcode_is_ambiguous', 'scan_product_ambiguous']) {
      expect(productScanAmbiguousApiMessage(code)).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
      expect(await readApiErrorMessage(reply(code))).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
      // Серверный текст конкретного процесса не подменяет общий.
      expect(
        await readApiErrorMessage(reply({ code, message: 'Штрихкод соответствует разным товарам.' })),
      ).toBe(PRODUCT_SCAN_AMBIGUOUS_MESSAGE)
    }
  })

  it('межтиповая неоднозначность общего поиска остаётся своей', async () => {
    expect(productScanAmbiguousApiMessage('scan_ambiguous')).toBeNull()
    expect(await readApiErrorMessage(reply('scan_ambiguous'))).toBe('scan_ambiguous')
    expect(
      await readApiErrorMessage(reply({ code: 'scan_ambiguous', message: 'Код совпал с товаром и ячейкой.' })),
    ).toBe('Код совпал с товаром и ячейкой.')
  })

  it('другие ответы переводятся как раньше', async () => {
    expect(productScanAmbiguousApiMessage(undefined)).toBeNull()
    expect(await readApiErrorMessage(reply('barcode_unknown', 404))).toBe(
      'Штрихкод не найден. Проверьте товар или ячейку.',
    )
    expect(await readApiErrorMessage(reply('some_new_code'))).toBe('some_new_code')
    expect(
      await readApiErrorMessage(reply({ code: 'unknown_barcode', message: 'Текст сервера.' })),
    ).toBe('Текст сервера.')
  })
})
