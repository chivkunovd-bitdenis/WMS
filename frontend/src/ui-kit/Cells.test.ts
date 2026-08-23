import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ProductCell } from './Cells'

describe('ProductCell', () => {
  it('truncates a long SKU and exposes its full value in an accessible tooltip', () => {
    const sku = 'SKU-IDENTICAL-PREFIX-THIS-PART-DIFFERENT-0001'

    const markup = renderToStaticMarkup(createElement(ProductCell, { sku }))

    expect(markup).toContain('text-overflow:ellipsis')
    expect(markup).toContain(`aria-label="${sku}"`)
    expect(markup).toContain(sku)
  })
})
