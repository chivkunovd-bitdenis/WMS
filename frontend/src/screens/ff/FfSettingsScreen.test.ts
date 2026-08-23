import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { FfSettingsScreen } from './FfSettingsScreen'

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
