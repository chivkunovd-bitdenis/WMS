import { describe, expect, it } from 'vitest'

import { visibleSellerNavItems } from './SellerLayout'
import { emptySellerPermissions } from '../../utils/sellerPermissions'

// WMS-549 R1/R4: «Расчёты» видно только с правом «Документы» (владелец кабинета —
// у него всегда все права) и стоит сразу после «Отчёты», как в макете.

describe('WMS-549 seller menu — «Расчёты»', () => {
  it('places the item right after «Отчёты» for a user with the documents permission', () => {
    const items = visibleSellerNavItems('', { ...emptySellerPermissions(), documents: true, products: true })
    const keys = items.map((item) => item.key)

    expect(keys).toContain('billing')
    expect(keys.indexOf('billing')).toBe(keys.indexOf('reports') + 1)
    expect(items.find((item) => item.key === 'billing')).toEqual({
      key: 'billing',
      label: 'Расчёты',
      to: '/billing',
      testId: 'nav-seller-billing',
    })
  })

  it('hides the item for a staff user without the documents permission', () => {
    const items = visibleSellerNavItems('', { ...emptySellerPermissions(), products: true, honest_sign: true })

    expect(items.map((item) => item.key)).not.toContain('billing')
  })

  it('shows the item for the cabinet owner, who has every permission', () => {
    const items = visibleSellerNavItems('', {
      documents: true,
      products: true,
      honest_sign: true,
      settings: true,
      staff: true,
    })

    expect(items.map((item) => item.key)).toContain('billing')
  })
})
