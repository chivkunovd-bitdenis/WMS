import { describe, expect, it } from 'vitest'
import { marketplaceFillButtonsVisible, mergeMarketplaceRequisitesIntoForm } from './FfBillingProfilesDialog'

const FILLED_FORM = {
  legal_name: 'ООО Ручное',
  inn: '7700000000',
  kpp: '770001001',
  bank_name: 'Ручной банк',
  bik: '044525225',
  settlement_account: '40702810000000000001',
  correspondent_account: '30101810400000000225',
}

describe('mergeMarketplaceRequisitesIntoForm (WMS-547 R10)', () => {
  it('substitutes inn, legal_name and kpp when the platform returned them', () => {
    const result = mergeMarketplaceRequisitesIntoForm(FILLED_FORM, {
      inn: '500100732259',
      legal_name: 'ИП Тестов Т. Т.',
      kpp: '997700001',
    })
    expect(result.inn).toBe('500100732259')
    expect(result.legal_name).toBe('ИП Тестов Т. Т.')
    expect(result.kpp).toBe('997700001')
  })

  it('never touches the bank fields', () => {
    const result = mergeMarketplaceRequisitesIntoForm(FILLED_FORM, {
      inn: '500100732259',
      legal_name: 'ИП Тестов Т. Т.',
      kpp: null,
    })
    expect(result.bank_name).toBe(FILLED_FORM.bank_name)
    expect(result.bik).toBe(FILLED_FORM.bik)
    expect(result.settlement_account).toBe(FILLED_FORM.settlement_account)
    expect(result.correspondent_account).toBe(FILLED_FORM.correspondent_account)
  })

  it('keeps the already-typed KPP when the response has no usable KPP (null)', () => {
    const result = mergeMarketplaceRequisitesIntoForm(FILLED_FORM, {
      inn: '500100732259',
      legal_name: 'ИП Тестов Т. Т.',
      kpp: null,
    })
    expect(result.kpp).toBe(FILLED_FORM.kpp)
  })

  it('keeps the already-typed KPP when the field is simply absent from the response', () => {
    const result = mergeMarketplaceRequisitesIntoForm(FILLED_FORM, {
      inn: '500100732259',
      legal_name: 'ИП Тестов Т. Т.',
    })
    expect(result.kpp).toBe(FILLED_FORM.kpp)
  })
})

describe('marketplaceFillButtonsVisible (WMS-547 R9)', () => {
  it('shows nothing without a seller id — the shared "Расчёты" dialog', () => {
    expect(marketplaceFillButtonsVisible({ wbConnected: true, ozonConnected: true })).toEqual({
      wb: false,
      ozon: false,
    })
  })

  it('shows only the connected marketplace button for a seller', () => {
    expect(
      marketplaceFillButtonsVisible({ sellerId: 's1', wbConnected: true, ozonConnected: false }),
    ).toEqual({ wb: true, ozon: false })
    expect(
      marketplaceFillButtonsVisible({ sellerId: 's1', wbConnected: false, ozonConnected: true }),
    ).toEqual({ wb: false, ozon: true })
  })

  it('shows both buttons when both are connected', () => {
    expect(
      marketplaceFillButtonsVisible({ sellerId: 's1', wbConnected: true, ozonConnected: true }),
    ).toEqual({ wb: true, ozon: true })
  })

  it('shows neither button when the seller has no keys', () => {
    expect(marketplaceFillButtonsVisible({ sellerId: 's1' })).toEqual({ wb: false, ozon: false })
  })
})
