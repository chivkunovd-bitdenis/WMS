import { describe, expect, it } from 'vitest'
import { buildNumberedItems, markKey } from './FfFbsPickList'

describe('Лист подбора: отметки «Собрал» и «Упаковал»', () => {
  it('сохраняет сквозные диапазоны при скрытии строк представления', () => {
    const rows = buildNumberedItems([
      { article: 'A', sku_code: null, size: 'M', product_name: 'A', quantity: 3, number_start: 1, number_end: 3, order_ids: ['1', '2', '3'] },
      { article: 'B', sku_code: null, size: null, product_name: 'B', quantity: 1, number_start: 4, number_end: 4, order_ids: ['4'] },
      { article: 'C', sku_code: null, size: 'L', product_name: 'C', quantity: 2, number_start: 5, number_end: 6, order_ids: ['5', '6'] },
    ])
    expect(rows.map(({ numberFrom, numberTo }) => [numberFrom, numberTo])).toEqual([[1, 3], [4, 4], [5, 6]])
  })
  it('у одного артикула разные размеры — разные отметки', () => {
    // Артикул J308-6 приходит четырьмя строками: 38, 39, 40, 41. Раньше ключом был
    // только артикул, и галочка на 38-м вставала сразу на все четыре размера.
    const sizes = ['38', '39', '40', '41'].map((size) => markKey({ article: 'J308-6', sku_code: 'SKU-1', product_name: 'Куртка', size }))
    expect(new Set(sizes).size).toBe(4)
  })

  it('товар без размера опирается на артикул', () => {
    expect(markKey({ article: 'ART-1', sku_code: null, product_name: 'Товар', size: null })).toBe('ART-1::::::Товар')
  })

  it('одинаковый размер у разных артикулов не смешивается', () => {
    expect(markKey({ article: 'J308-6', sku_code: 'SKU-1', product_name: 'Товар', size: '39' }))
      .not.toBe(markKey({ article: 'J308-24', sku_code: 'SKU-1', product_name: 'Товар', size: '39' }))
  })

  it('различает одинаковые артикул и размер при разном SKU или названии', () => {
    expect(markKey({ article: 'A', sku_code: 'SKU-1', product_name: 'Один', size: 'M' }))
      .not.toBe(markKey({ article: 'A', sku_code: 'SKU-2', product_name: 'Два', size: 'M' }))
  })
})
