import { describe, expect, it } from 'vitest'

import { sellerDocumentStatusRu } from './SellerDocumentsScreen'
import {
  sellerInboundStatusRu,
  sellerInboundPendingText,
  shouldShowSellerInboundLoadError,
  shouldShowSellerInboundNoWarehouse,
  shouldShowSellerWarehouseSelector,
  sellerVisibleWarehouses,
} from './SellerInboundDraftScreen'

describe('seller inbound document UI helpers', () => {
  it('maps seller documents inbound workflow statuses to Russian labels', () => {
    expect(sellerDocumentStatusRu('receiving', 'inbound')).toBe('Принимается на складе')
    expect(sellerDocumentStatusRu('sorting', 'inbound')).toBe('В сортировке')
    expect(sellerDocumentStatusRu('done', 'inbound')).toBe('Проведено')
  })

  it('maps seller marketplace unload statuses without leaking raw backend text', () => {
    expect(sellerDocumentStatusRu('collecting', 'mp_unload')).toBe('На сборке')
    expect(sellerDocumentStatusRu('cancelled', 'mp_unload')).toBe('Отменено')
    expect(sellerDocumentStatusRu('collecting', 'mp_unload')).not.toBe('collecting')
    expect(sellerDocumentStatusRu('cancelled', 'mp_unload')).not.toBe('cancelled')
  })

  it('hides unknown raw backend statuses from document and inbound fact-card UI', () => {
    expect(sellerDocumentStatusRu('backend_inbound_raw', 'inbound')).toBe('Статус уточняется')
    expect(sellerDocumentStatusRu('backend_mp_raw', 'mp_unload')).toBe('Статус уточняется')
    expect(sellerInboundStatusRu('backend_fact_card_raw')).toBe('Статус уточняется')
    expect(sellerDocumentStatusRu('backend_inbound_raw', 'inbound')).not.toBe('backend_inbound_raw')
    expect(sellerDocumentStatusRu('backend_mp_raw', 'mp_unload')).not.toBe('backend_mp_raw')
    expect(sellerInboundStatusRu('backend_fact_card_raw')).not.toBe('backend_fact_card_raw')
  })

  it('keeps existing inbound card load failures out of draft and no-warehouse states', () => {
    expect(shouldShowSellerInboundNoWarehouse(null, 'request-1', null)).toBe(false)
    expect(shouldShowSellerInboundLoadError(false, 'Заявка не найдена')).toBe(true)
    expect(sellerInboundPendingText('request-1')).toBe('Загружаем карточку приёмки…')
    expect(sellerInboundPendingText(null)).toBe('Создаём черновик…')
  })

  it('shows warehouse choice only for a draft with multiple available warehouses', () => {
    expect(shouldShowSellerWarehouseSelector(1, 'draft')).toBe(false)
    expect(shouldShowSellerWarehouseSelector(2, 'draft')).toBe(true)
    expect(shouldShowSellerWarehouseSelector(2, 'submitted')).toBe(false)
  })

  it('does not expose service FBS warehouses to the seller', () => {
    expect(
      sellerVisibleWarehouses([
        { id: 'north', name: 'Север', code: 'north' },
        { id: 'wb', name: 'FBS WB Москва', code: 'fbs-wb-moscow' },
      ]),
    ).toEqual([{ id: 'north', name: 'Север', code: 'north' }])
  })
})
