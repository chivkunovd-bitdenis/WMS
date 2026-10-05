import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ProductBarcodeCell, normalizeProductBarcodes } from './ProductBarcodeCell'

describe('WMS-660 product barcode cell', () => {
  it('keeps the primary barcode first and removes blank and duplicate values', () => {
    expect(
      normalizeProductBarcodes(' 04640556102658 ', [
        '2055629421109',
        '04640556102658',
        ' ',
        '4610264735875',
        '2055629421109',
      ]),
    ).toEqual(['04640556102658', '2055629421109', '4610264735875'])
  })

  it('renders every saved barcode as a separate plain line', () => {
    const markup = renderToStaticMarkup(
      <ProductBarcodeCell
        barcode="04640556102658"
        barcodes={['2055629421109', '4610264735875']}
        testId="barcode-cell"
      />,
    )

    expect(markup).toContain('04640556102658')
    expect(markup).toContain('2055629421109')
    expect(markup).toContain('4610264735875')
    expect(markup.match(/data-barcode-line=/g)).toHaveLength(3)
  })

  it('preserves the old one-line display for records with one barcode', () => {
    const markup = renderToStaticMarkup(
      <ProductBarcodeCell barcode="2055629421109" barcodes={[]} />,
    )

    expect(markup.match(/data-barcode-line=/g)).toHaveLength(1)
    expect(markup).toContain('2055629421109')
  })
})
