import JsBarcode from 'jsbarcode'

export function renderBarcodeDataUrl(barcode: string): string {
  const draw =
    (JsBarcode as unknown as { default?: typeof JsBarcode }).default ?? JsBarcode
  const c = document.createElement('canvas')
  c.width = 320
  c.height = 80
  const ctx = c.getContext('2d')
  if (!ctx) {
    throw new Error('Canvas context недоступен.')
  }
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, c.width, c.height)
  draw(c, barcode, {
    format: 'CODE128',
    displayValue: false,
    height: 64,
    margin: 8,
    lineColor: '#111',
    background: '#fff',
  })
  return c.toDataURL('image/png')
}
