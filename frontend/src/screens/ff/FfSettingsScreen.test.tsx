import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { FfSettingsScreen } from './FfSettingsScreen'

const props = {
  token: 'test-token',
  authHeaders: () => ({ Authorization: 'Bearer test-token' }),
  canManageStaff: true,
}

describe('FfSettingsScreen tariff deep link owner', () => {
  it('renders a stable tariff anchor for fulfillment admin without a new route', () => {
    const markup = renderToStaticMarkup(
      <FfSettingsScreen {...props} isFulfillmentAdmin />,
    )
    expect(markup).toContain('id="ff-settings-tariffs-panel"')
    expect(markup).toContain('data-testid="ff-settings-tariffs-panel"')
    expect(markup).toContain('Тарифы')
  })

  it('does not reveal tariff settings to non-admin staff', () => {
    const markup = renderToStaticMarkup(
      <FfSettingsScreen {...props} isFulfillmentAdmin={false} />,
    )
    expect(markup).not.toContain('ff-settings-tariffs-panel')
  })
})
