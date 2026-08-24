import JsBarcode from 'jsbarcode'

type BarcodeVariant = 'default' | 'thermal58' | 'storageCell' | 'internalBox'

const VARIANTS: Record<
  BarcodeVariant,
  { width: number; height: number; barHeight: number; margin: number; moduleWidth?: number }
> = {
  default: { width: 320, height: 80, barHeight: 64, margin: 8 },
  thermal58: { width: 248, height: 56, barHeight: 44, margin: 4 },
  storageCell: { width: 1200, height: 300, barHeight: 240, margin: 24, moduleWidth: 5 },
  // Внутренние короба и грузоместа сканируют издалека на складе. У длинного
  // Code 128 достаточно крупный модуль только на полном полотне этикетки.
  internalBox: { width: 1200, height: 380, barHeight: 300, margin: 28, moduleWidth: 5 },
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
    width: size.moduleWidth,
    lineColor: '#111',
    background: '#fff',
  })
  return c.toDataURL('image/png')
}
