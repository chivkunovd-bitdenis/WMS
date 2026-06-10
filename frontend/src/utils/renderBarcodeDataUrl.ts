import JsBarcode from 'jsbarcode'

type BarcodeVariant = 'default' | 'thermal58'

const VARIANTS: Record<
  BarcodeVariant,
  { width: number; height: number; barHeight: number; margin: number }
> = {
  default: { width: 320, height: 80, barHeight: 64, margin: 8 },
  thermal58: { width: 248, height: 56, barHeight: 44, margin: 4 },
}

export function renderBarcodeDataUrl(
  barcode: string,
  options?: { variant?: BarcodeVariant },
): string {
  const variant = options?.variant ?? 'default'
  const size = VARIANTS[variant]
  const draw =
    (JsBarcode as unknown as { default?: typeof JsBarcode }).default ?? JsBarcode
  const c = document.createElement('canvas')
  c.width = size.width
  c.height = size.height
  const ctx = c.getContext('2d')
  if (!ctx) {
    throw new Error('Canvas context недоступен.')
  }
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, c.width, c.height)
  draw(c, barcode, {
    format: 'CODE128',
    displayValue: false,
    height: size.barHeight,
    margin: size.margin,
    lineColor: '#111',
    background: '#fff',
  })
  return c.toDataURL('image/png')
}
