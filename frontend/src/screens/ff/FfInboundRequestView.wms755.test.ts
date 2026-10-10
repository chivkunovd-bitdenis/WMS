import { describe, expect, it } from 'vitest'
import { findInboundContainerByScan } from './FfInboundRequestView'

const boxes = [
  { id: 'box-1', internal_barcode: 'INB-V2KA7397PAX2M9' },
  { id: 'box-2', internal_barcode: 'INB-4JDZN6VTGZBH5Z' },
]
const places = [{ id: 'place-1', internal_barcode: 'GM-0001' }]

describe('WMS-755: скан наклейки короба в приёмке', () => {
  it('код короба открывает именно этот короб, регистр не важен', () => {
    expect(findInboundContainerByScan(' inb-4jdzn6vtgzbh5z ', boxes, places)).toEqual({ kind: 'box', id: 'box-2' })
  })

  it('код грузоместа открывает грузоместо', () => {
    expect(findInboundContainerByScan('GM-0001', boxes, places)).toEqual({ kind: 'cargo_place', id: 'place-1' })
  })

  it('штрихкод товара и чужой код — не контейнер, скан идёт как раньше', () => {
    expect(findInboundContainerByScan('4650263673075', boxes, places)).toBeNull()
    expect(findInboundContainerByScan('INB-4JDZN6VTGZBH5', boxes, places)).toBeNull()
    expect(findInboundContainerByScan('', boxes, places)).toBeNull()
  })
})
