import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { resolveOzonAccountDisplay, SellerSettingsScreen } from './SellerSettingsScreen'

describe('seller employee email invitations', () => {
  it('offers email and permissions without a manager-supplied password', () => {
    const html = renderToStaticMarkup(createElement(SellerSettingsScreen, {
      token: 'test', authHeaders: () => ({}),
      permissions: { documents: true, products: false, honest_sign: false, settings: false, staff: true },
    }))
    expect(html).toContain('name="seller_staff_email"')
    expect(html).toContain('type="email"')
    expect(html).toContain('name="seller_staff_full_name"')
    expect(html).not.toContain('seller_staff_password')
    expect(html).not.toContain('type="password"')
    expect(html).toContain('seller-staff-create-perm-documents')
  })

  it('does not expose staff management without staff permission', () => {
    const html = renderToStaticMarkup(createElement(SellerSettingsScreen, {
      token: 'test', authHeaders: () => ({}),
      permissions: { documents: true, products: false, honest_sign: false, settings: false, staff: false },
    }))
    expect(html).not.toContain('seller-staff-panel')
    expect(html).not.toContain('seller_staff_email')
  })
})

describe('Ozon account exchange status', () => {
  it('shows enabled exchange only for a connected, validated account and an explicit true flag', () => {
    expect(resolveOzonAccountDisplay({ connected: true, validation_status: 'valid', live_exchange_enabled: true })).toEqual({
      label: 'Подключено, обмен включён', exchangeDisabled: false,
    })
  })

  it('preserves the disabled warning for an explicit false flag', () => {
    expect(resolveOzonAccountDisplay({ connected: true, validation_status: 'valid', live_exchange_enabled: false })).toEqual({
      label: 'Ключ принят, обмен не включён', exchangeDisabled: true,
    })
  })

  it('makes no exchange claim when an older API omits the flag', () => {
    expect(resolveOzonAccountDisplay({ connected: true, validation_status: 'valid' })).toEqual({
      label: 'Ключ принят', exchangeDisabled: false,
    })
  })

  it('does not let the global live flag override connection validation', () => {
    expect(resolveOzonAccountDisplay({ connected: true, validation_status: 'invalid', live_exchange_enabled: true })).toEqual({
      label: 'Подключение требует проверки', exchangeDisabled: false,
    })
    expect(resolveOzonAccountDisplay({ connected: true, validation_status: 'unavailable', live_exchange_enabled: true })).toEqual({
      label: 'Проверка подключения недоступна', exchangeDisabled: false,
    })
    expect(resolveOzonAccountDisplay({ connected: false, validation_status: 'not_configured', live_exchange_enabled: true })).toEqual({
      label: 'Не подключено', exchangeDisabled: false,
    })
    expect(resolveOzonAccountDisplay(null)).toEqual({ label: 'Не подключено', exchangeDisabled: false })
  })
})
