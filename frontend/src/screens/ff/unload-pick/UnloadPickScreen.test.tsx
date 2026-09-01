import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { UnloadPickScreen } from './UnloadPickScreen'
import { cellRef, type PickProduct } from './pickStub'


describe('UnloadPickScreen product identity columns', () => {
  it('shows photo, name, seller article, SKU, barcode, and size as separate values', () => {
    const product: PickProduct = {
      id: 'product-1',
      name: 'Куртка демо обычная',
      sellerArticle: 'KURTKA-VIDEO-01',
      sku: 'EMU-NORMAL-B2C',
      barcode: '2000000000011',
      photo: 'https://images.example.test/jacket.webp',
      size: '48',
    }

    const markup = renderToStaticMarkup(
      <UnloadPickScreen
        onNote={() => undefined}
        products={[product]}
        plan={[{ id: 'plan-1', productId: product.id, plan: 1 }]}
        stock={[{ id: 'stock-1', productId: product.id, qty: 1, holder: cellRef('cell-1') }]}
        cells={[{ id: 'cell-1', code: 'FBS-VIDEO-01', barcode: 'LOC-FBS-VIDEO-01' }]}
        objects={[]}
      />,
    )

    expect(markup).toContain('Товар')
    expect(markup).toContain('Артикул продавца')
    expect(markup).toContain('SKU')
    expect(markup).toContain('ШК')
    expect(markup).toContain('Размер')
    expect(markup).toContain('Куртка демо обычная')
    expect(markup).toContain('KURTKA-VIDEO-01')
    expect(markup).toContain('EMU-NORMAL-B2C')
    expect(markup).toContain('2000000000011')
    expect(markup).toContain('48')
    expect(markup).toContain('pick-product-photo-product-1')
  })
})
