import { describe, expect, it } from 'vitest'
import { ordersWord } from './fbsUx'

describe('FBS supply creation copy', () => {
  it('TC-FBS-UX-001 uses correct Russian order forms', () => {
    expect([1, 2, 4, 5, 11, 21, 22, 25].map((count) => `${count} ${ordersWord(count)}`)).toEqual([
      '1 заказ',
      '2 заказа',
      '4 заказа',
      '5 заказов',
      '11 заказов',
      '21 заказ',
      '22 заказа',
      '25 заказов',
    ])
  })
})
