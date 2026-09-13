import { describe, expect, it } from 'vitest'
import { workingDocumentTarget } from './documentTarget'

// Ссылка карточки документа полезна ровно настолько, насколько её читает экран
// выпуска. Поэтому здесь закреплены сами адреса, а рядом назван фактический
// получатель каждого параметра в выпускаемом коде — сверять надо с ним:
//
//   order_id + seller_id -> FfFbsOrdersScreen (точный заказ из сообщения)
//   supply_id            -> FfFbsOrdersScreen (открытие рабочего пространства)
//   open_inbound         -> App.tsx, обработчик WMS-177 на /app/ff/reception
//   open_mp              -> FfSuppliesShipmentsPage (документ отгрузки на МП)
//   open_outbound        -> FfSuppliesShipmentsPage (отгрузка со склада)
//
// Менять параметр в этом файле можно только вместе с его получателем.

const doc = (kind: string) => ({ kind, id: 'doc-1', seller_id: 'seller-1' })

describe('WMS-397 рабочие ссылки карточки документа', () => {
  it('фулфилмент получает существующие рабочие маршруты', () => {
    expect(workingDocumentTarget(doc('fbs_order'), '/app/ff')).toBe(
      '/app/ff/fbs?order_id=doc-1&seller_id=seller-1',
    )
    expect(workingDocumentTarget(doc('fbs_supply'), '/app/ff')).toBe('/app/ff/fbs?supply_id=doc-1')
    expect(workingDocumentTarget(doc('inbound_intake'), '/app/ff')).toBe(
      '/app/ff/reception?open_inbound=doc-1',
    )
    expect(workingDocumentTarget(doc('marketplace_unload'), '/app/ff')).toBe(
      '/app/ff/mp-shipments?open_mp=doc-1',
    )
    expect(workingDocumentTarget(doc('outbound_shipment'), '/app/ff')).toBe(
      '/app/ff/mp-shipments?open_outbound=doc-1',
    )
  })

  it('идентификаторы уходят в адрес экранированными', () => {
    const target = workingDocumentTarget({ kind: 'fbs_order', id: 'a b&c', seller_id: 'x y' }, '/app/ff')
    expect(target).toBe('/app/ff/fbs?order_id=a%20b%26c&seller_id=x%20y')
  })

  it('у продавца рабочая только приёмка, остальное уходит на карточку чата', () => {
    expect(workingDocumentTarget(doc('inbound_intake'), '')).toBe('/inbound/doc-1')
    for (const kind of ['fbs_order', 'fbs_supply', 'marketplace_unload', 'outbound_shipment']) {
      expect(workingDocumentTarget(doc(kind), '')).toBeNull()
    }
  })
})
