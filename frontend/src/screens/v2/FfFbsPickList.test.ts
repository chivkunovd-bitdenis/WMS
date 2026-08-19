import { describe, expect, it } from 'vitest'
import { markKey } from './FfFbsPickList'

describe('Лист подбора: отметки «Собрал» и «Упаковал»', () => {
  it('у одного артикула разные размеры — разные отметки', () => {
    // Артикул J308-6 приходит четырьмя строками: 38, 39, 40, 41. Раньше ключом был
    // только артикул, и галочка на 38-м вставала сразу на все четыре размера.
    const sizes = ['38', '39', '40', '41'].map((size) => markKey({ article: 'J308-6', size }))
    expect(new Set(sizes).size).toBe(4)
  })

  it('товар без размера опирается на артикул', () => {
    expect(markKey({ article: 'ART-1', size: null })).toBe('ART-1')
  })

  it('одинаковый размер у разных артикулов не смешивается', () => {
    expect(markKey({ article: 'J308-6', size: '39' }))
      .not.toBe(markKey({ article: 'J308-24', size: '39' }))
  })
})
