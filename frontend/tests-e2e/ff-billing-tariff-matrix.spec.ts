import { expect, test } from '@playwright/test'

// TC-NEW-2B-001 — Given an FF admin opens the existing settings tariff link,
// When the matrix loads, Then the stable S-19 section is visible without a new route.
test('S-19 tariff matrix accepts existing deep link', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('wms_token_ff', 'e2e-tariff-admin'))
  await page.route('**/api/auth/me', async (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ email: 'tariff@example.test', organization_name: 'Тарифы', role: 'fulfillment_admin' }),
  }))
  await page.route('**/api/auth/staff-accounts**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/api/billing/tariff-matrix', async (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ revision: 0, services: [
      { service_code: 'inbound', enabled: false }, { service_code: 'marketplace_outbound', enabled: false },
      { service_code: 'packing', enabled: false }, { service_code: 'return', enabled: false },
    ] }),
  }))
  await page.goto('/app/ff/settings?tab=tariffs')
  const panel = page.getByTestId('ff-settings-tariffs-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toBeFocused()
  await expect(panel.getByText('Приёмка', { exact: true })).toBeVisible()
  const inboundAction = panel.getByTestId('ff-settings-tariff-inbound')
  await expect(inboundAction).toHaveText('Включить')
  await expect(inboundAction).toHaveAttribute('aria-pressed', 'false')
  await inboundAction.click()
  await expect(inboundAction).toHaveText('Выключить')
  await expect(inboundAction).toHaveAttribute('aria-pressed', 'true')
})
