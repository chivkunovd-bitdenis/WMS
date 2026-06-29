import { describe, expect, it } from 'vitest'

import { buildPackagingInstructionsPrintHtml } from './printPackagingInstructions'

describe('buildPackagingInstructionsPrintHtml', () => {
  it('includes product, seller and instructions on A4 layout', () => {
    const html = buildPackagingInstructionsPrintHtml({
      sku_code: 'SKU-1',
      product_name: 'Браслет',
      seller_name: 'Denmarcs',
      instructions: 'Упаковать в пакет\n+ бирка',
      requires_honest_sign: true,
    })
    expect(html).toContain('size: A4')
    expect(html).toContain('SKU-1')
    expect(html).toContain('Браслет')
    expect(html).toContain('Denmarcs')
    expect(html).toContain('Упаковать в пакет')
    expect(html).toContain('Нужен Честный знак при упаковке')
  })

  it('escapes html in instructions', () => {
    const html = buildPackagingInstructionsPrintHtml({
      sku_code: 'x',
      product_name: 'y',
      instructions: '<script>alert(1)</script>',
    })
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })
})
