import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import {
  FfSettingsScreen,
  isTariffUnitAllowed,
  tariffRequestPayload,
  unitForTariffService,
} from './FfSettingsScreen'

function openingTag(markup: string, testId: string): string {
  return markup.match(new RegExp(`<button[^>]*data-testid="${testId}"[^>]*>`))?.[0] ?? ''
}

function renderSettings(initialEntry = '/app/ff/settings'): string {
  return renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: [initialEntry] },
      createElement(FfSettingsScreen, {
        token: '',
        authHeaders: () => ({}),
        isFulfillmentAdmin: true,
        canManageStaff: true,
      }),
    ),
  )
}

describe('FfSettingsScreen settings tabs', () => {
  it('renders the administrator sections as semantic tabs with staff selected initially', () => {
    const markup = renderSettings()

    expect(markup).toContain('role="tablist"')
    expect(markup).toContain('aria-label="Разделы настроек"')
    expect(openingTag(markup, 'ff-settings-staff-tab')).toContain('aria-selected="true"')
    expect(openingTag(markup, 'ff-settings-tariffs-tab')).toContain('aria-selected="false"')
  })

  it('opens the tariff tab when the route requests it', () => {
    const markup = renderSettings('/app/ff/settings?tab=tariffs')

    expect(openingTag(markup, 'ff-settings-staff-tab')).toContain('aria-selected="false"')
    expect(openingTag(markup, 'ff-settings-tariffs-tab')).toContain('aria-selected="true"')
  })
})

describe('FfSettingsScreen tariff unit', () => {
  it('sets liter-day only for storage and returns to a permitted operational unit', () => {
    const storageUnit = unitForTariffService('storage_liter_day', 'document')

    expect(storageUnit).toBe('liter_day')
    expect(unitForTariffService('inbound', storageUnit)).toBe('document')
    expect(unitForTariffService('outbound', storageUnit)).toBe('document')
    expect(unitForTariffService('inbound', 'item')).toBe('item')
  })

  it('builds only valid operational tariff requests and rejects liter-day for them', () => {
    const inbound = tariffRequestPayload({ service_code: 'inbound', seller_id: '', unit: 'document', amount: '45', valid_from: '2026-08-01' }, 45)
    const outbound = tariffRequestPayload({ service_code: 'outbound', seller_id: 'seller-1', unit: 'item', amount: '12', valid_from: '2026-08-01' }, 12)
    const invalidOperational = tariffRequestPayload({ service_code: 'inbound', seller_id: '', unit: 'liter_day', amount: '1', valid_from: '2026-08-01' }, 1)

    expect(inbound).toMatchObject({ service_code: 'inbound', unit: 'document', seller_id: null, amount: 45 })
    expect(outbound).toMatchObject({ service_code: 'marketplace_outbound', unit: 'item', seller_id: 'seller-1', amount: 12 })
    expect(invalidOperational).toBeNull()
    expect(isTariffUnitAllowed('outbound', 'liter_day')).toBe(false)
  })
})
