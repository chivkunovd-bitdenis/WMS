import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { humanTariffMatrixError } from './FfBillingTariffMatrixPanel'
import { FfSettingsScreen } from './FfSettingsScreen'

const props = {
  token: 'test-token',
  authHeaders: () => ({ Authorization: 'Bearer test-token' }),
  canManageStaff: true,
}

describe('FfSettingsScreen tariff deep link owner', () => {
  it('translates a stale tariff revision into an actionable operator message', () => {
    expect(humanTariffMatrixError('billing_tariff_matrix_stale_revision')).toBe(
      'Конфигурация тарифов уже изменилась. Обновите данные и повторите сохранение.',
    )
    expect(humanTariffMatrixError('network_failed')).toBe('network_failed')
  })

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

  it('keeps the complete tariff-matrix structure inside S-19 using ui-kit fields', () => {
    const markup = renderToStaticMarkup(
      <FfSettingsScreen {...props} isFulfillmentAdmin />,
    )
    expect(markup).toContain('Ставка, ₽')
    expect(markup).toContain('Товарные цены')
    expect(markup).toContain('Ставки сотрудников')
    expect(markup).toContain('Хранение')
    expect(markup).toContain('ff-settings-tariff-product-id')
    expect(markup).toContain('ff-settings-tariff-employee-rates')
  })
})
