import { describe, expect, it } from 'vitest'
import { resolveOzonAccountDisplay } from './SellerSettingsScreen'

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
