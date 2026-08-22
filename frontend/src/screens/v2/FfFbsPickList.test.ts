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

// TC-06-001: отображение диапазона «№» в листе подбора
describe('Лист подбора: колонка «№» — диапазон и одиночное число', () => {
  // Логика вычисления orderNo вынесена inline в FfFbsPickList.tsx:
  //   const orderNo = i.first_no === i.last_no ? String(i.first_no) : `${i.first_no}–${i.last_no}`
  // Тестируем ту же логику здесь, чтобы зафиксировать контракт.
  function computeOrderNo(first_no: number, last_no: number): string {
    return first_no === last_no ? String(first_no) : `${first_no}–${last_no}`
  }

  it('одна наклейка — одиночное число', () => {
    expect(computeOrderNo(7, 7)).toBe('7')
  })

  it('несколько наклеек — диапазон через тире', () => {
    expect(computeOrderNo(12, 17)).toBe('12–17')
  })

  it('два заказа подряд', () => {
    expect(computeOrderNo(3, 4)).toBe('3–4')
  })

  it('первый элемент всегда 1', () => {
    expect(computeOrderNo(1, 1)).toBe('1')
  })
})
