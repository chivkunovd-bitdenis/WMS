import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { formatStockQty } from '../utils/formatStockQty'
import { ProductStockLines } from './ProductStockLines'

// WMS-532: ячейка «Остаток» в каталоге ФФ и в кабинете селлера — три строки
// с теми же числами, что отдаёт сервер (WMS-530 R1–R3).

const NBSP = '\u00a0'
const MINUS = '\u2212'

describe('WMS-532 ячейка «Остаток»', () => {
  it('разряды — неразрывным пробелом, как в «В Wildberries»; минус — настоящий', () => {
    expect(formatStockQty(1234567)).toBe(`1${NBSP}234${NBSP}567`)
    expect(formatStockQty(0)).toBe('0')
    expect(formatStockQty(-3)).toBe(`${MINUS}3`)
    expect(formatStockQty(-1234567)).toBe(`${MINUS}1${NBSP}234${NBSP}567`)
  })

  it('R1–R3: три строки по порядку, отрицательное Доступно как есть, подсказка повторяет строку', () => {
    const markup = renderToStaticMarkup(
      <ProductStockLines
        totals={{ onHand: -3, reserved: 2, available: -5 }}
        productId="p1"
        testIdPrefix="ff-catalog-stock"
      />,
    )
    const onHand = markup.indexOf('Остаток')
    const reserved = markup.indexOf('Резерв')
    const available = markup.indexOf('Доступно')
    expect(onHand).toBeGreaterThanOrEqual(0)
    expect(reserved).toBeGreaterThan(onHand)
    expect(available).toBeGreaterThan(reserved)
    expect(markup).toContain(`data-testid="ff-catalog-stock-on-hand-p1" title="Остаток ${MINUS}3"`)
    expect(markup).toContain(`data-testid="ff-catalog-stock-reserved-p1" title="Резерв 2"`)
    expect(markup).toContain(`data-testid="ff-catalog-stock-available-p1" title="Доступно ${MINUS}5"`)
    expect(markup).not.toContain('FBO')
    expect(markup).not.toContain('В ячейках')
  })
})
