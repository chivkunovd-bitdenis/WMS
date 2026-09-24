// Standalone local browser acceptance against tests.seller_staff_browser_app.
// WMS_BROWSER_URL=http://127.0.0.1:15463 node tests-e2e/seller-staff-invites.mjs
// WMS_PLAYWRIGHT_MODULE can point to an installed Playwright index.mjs.
import assert from 'node:assert/strict'

const { chromium } = await import(process.env.WMS_PLAYWRIGHT_MODULE || 'playwright')
const root = process.env.WMS_BROWSER_URL || 'http://127.0.0.1:15463'
const browser = await chromium.launch({ headless: true, channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const suffix = Date.now().toString()
const employeeEmail = `employee-with-long-address-${suffix}@example.com`
const employeeName = 'Александра Константинопольская-Рождественская'
const password = 'Self-password-463'
const errors = []
page.on('pageerror', error => errors.push(error.message))
try {
  const api = async (path, body, token) => {
    const response = await page.request.post(`${root}/api${path}`, {
      data: body, headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    assert(response.ok(), `${path}: ${response.status()}`)
    return response.json()
  }
  const admin = await api('/auth/register', {
    organization_name: 'Browser invitation test', slug: `browser-${suffix}`,
    admin_email: `admin-${suffix}@example.com`, password,
  })
  const seller = await api('/sellers', { name: 'Browser Seller' }, admin.access_token)
  const ownerEmail = `owner-${suffix}@example.com`
  await api('/auth/seller-accounts', { seller_id: seller.id, email: ownerEmail, password }, admin.access_token)
  await page.goto(`${root}/seller/`)
  await page.locator('input[type=email]').fill(ownerEmail)
  await page.locator('input[type=password]').fill(password)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await page.getByRole('button', { name: 'Выйти', exact: true }).waitFor()
  await page.goto(`${root}/seller/settings`)
  await page.getByTestId('seller-staff-panel').waitFor()
  assert.equal(await page.locator('[name=seller_staff_password]').count(), 0)
  await page.getByTestId('seller-staff-name').fill(employeeName)
  await page.getByTestId('seller-staff-email').fill('not-an-email')
  await page.getByTestId('seller-staff-submit').click()
  await page.getByTestId('seller-staff-error').waitFor()
  assert.equal(await page.getByTestId('seller-staff-name').inputValue(), employeeName)
  await page.getByTestId('seller-staff-email').fill(employeeEmail)
  await page.getByTestId('seller-staff-create-perm-products').locator('input').uncheck()
  await page.getByTestId('seller-staff-create-perm-honest_sign').locator('input').uncheck()
  for (const failure of ['network', 500, 422]) {
    await page.route('**/api/auth/seller-staff-accounts', route => failure === 'network'
      ? route.abort('failed')
      : route.fulfill({ status: failure, contentType: 'application/json', body: JSON.stringify({ detail: 'private backend detail' }) }), { times: 1 })
    await page.getByTestId('seller-staff-submit').click()
    await page.getByTestId('seller-staff-error').filter({ hasText: 'Не удалось добавить сотрудника.' }).waitFor()
    assert.equal(await page.getByTestId('seller-staff-name').inputValue(), employeeName)
    assert.equal(await page.getByTestId('seller-staff-email').inputValue(), employeeEmail)
    assert.equal(await page.getByTestId('seller-staff-create-perm-products').locator('input').isChecked(), false)
    assert(await page.getByTestId('seller-staff-submit').isEnabled())
  }
  const createdResponse = page.waitForResponse(r => r.url().endsWith('/seller-staff-accounts') && r.request().method() === 'POST')
  await page.getByTestId('seller-staff-submit').click()
  const created = await createdResponse
  assert.equal(created.status(), 201)
  const staff = await created.json()
  await page.getByTestId('seller-staff-ok').waitFor()
  assert.match(await page.getByTestId('seller-staff-ok').innerText(), /передано на отправку/)
  const row = page.locator(`[data-staff-id="${staff.id}"]`)
  await row.waitFor()
  assert.match(await row.innerText(), /ожидает активации/)
  for (const failure of ['network', 500, 422]) {
    await page.route(`**/api/auth/seller-staff-accounts/${staff.id}/invite`, route => failure === 'network'
      ? route.abort('failed')
      : route.fulfill({ status: failure, contentType: 'application/json', body: JSON.stringify({ detail: 'private backend detail' }) }), { times: 1 })
    await page.getByTestId(`seller-staff-invite-${staff.id}`).click()
    await page.getByTestId('seller-staff-error').filter({ hasText: 'Не удалось отправить приглашение.' }).waitFor()
    assert(await page.getByTestId(`seller-staff-invite-${staff.id}`).isEnabled())
  }
  const resend = page.waitForResponse(r => r.url().endsWith(`/${staff.id}/invite`))
  await page.getByTestId(`seller-staff-invite-${staff.id}`).click()
  assert.equal((await resend).status(), 204)
  await row.getByRole('button', { name: 'Изменить', exact: true }).click()
  const profileDialog = page.getByRole('dialog')
  for (const failure of ['network', 500, 422]) {
    await page.route(`**/api/auth/seller-staff-accounts/${staff.id}/profile`, route => failure === 'network'
      ? route.abort('failed')
      : route.fulfill({ status: failure, contentType: 'application/json', body: JSON.stringify({ detail: 'private backend detail' }) }), { times: 1 })
    await profileDialog.getByRole('button', { name: 'Сохранить', exact: true }).click()
    await profileDialog.getByRole('alert').filter({ hasText: 'Не удалось сохранить данные сотрудника.' }).waitFor()
    assert.equal(await profileDialog.getByLabel('ФИО', { exact: false }).inputValue(), employeeName)
  }
  await profileDialog.getByRole('button', { name: 'Сохранить', exact: true }).click()
  await profileDialog.waitFor({ state: 'hidden' })
  await page.getByTestId('seller-staff-name').fill(employeeName)
  await page.getByTestId('seller-staff-email').fill(employeeEmail)
  await page.getByTestId('seller-staff-submit').click()
  await page.getByTestId('seller-staff-error').filter({ hasText: 'Этот email уже используется' }).waitFor()
  assert.equal(await page.getByTestId('seller-staff-email').inputValue(), employeeEmail)
  if (process.env.WMS_BROWSER_SCREENSHOT) await page.screenshot({ path: process.env.WMS_BROWSER_SCREENSHOT.replace('.png', '-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  const menu = page.getByRole('button', { name: 'Открыть меню', exact: true })
  await menu.waitFor()
  await menu.click()
  await page.getByTestId('nav-seller-settings').click()
  await page.getByTestId('app-sidebar').waitFor({ state: 'hidden' })
  const inviteButton = page.getByTestId(`seller-staff-invite-${staff.id}`)
  await inviteButton.scrollIntoViewIfNeeded()
  const buttonBox = await inviteButton.boundingBox()
  assert(buttonBox.x >= 0 && buttonBox.x + buttonBox.width <= 390, JSON.stringify(buttonBox))
  assert(await inviteButton.isVisible() && await inviteButton.isEnabled())
  assert(await row.getByText('ожидает активации', { exact: true }).isVisible())
  const width = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }))
  assert(width.document <= width.viewport, JSON.stringify(width))
  const mobileResend = page.waitForResponse(r => r.url().endsWith(`/${staff.id}/invite`))
  await inviteButton.click()
  assert.equal((await mobileResend).status(), 204)
  if (process.env.WMS_BROWSER_SCREENSHOT) await page.screenshot({ path: process.env.WMS_BROWSER_SCREENSHOT, fullPage: true })
  const messages = await (await page.request.get(`${root}/api/_test/mail`)).json()
  const invitation = messages.find(message => message.to === employeeEmail)
  assert(invitation)
  const link = invitation.body.match(/https?:\/\/\S+/)[0]
  assert.equal(new URL(link).pathname, '/seller/set-password')
  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  await page.goto(link)
  await page.locator('[name=new_password]').fill(password)
  await page.locator('[name=new_password_confirm]').fill(password)
  await page.getByTestId('set-password-submit').click()
  await page.getByRole('button', { name: 'Выйти', exact: true }).waitFor()
  assert(!page.url().includes('set-password'))
  await page.setViewportSize({ width: 1440, height: 1000 })
  assert.equal(await page.getByRole('link', { name: 'Настройки', exact: true }).count(), 0)
  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  await page.locator('input[type=email]').fill(employeeEmail)
  await page.locator('input[type=password]').fill(password)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await page.getByRole('button', { name: 'Выйти', exact: true }).waitFor()
  assert.equal(errors.length, 0, errors.join('\n'))
  console.log('PASS: network/500/422 failures and retry for create/resend/profile, form preservation, 390px containment and clickable resend, desktop, captured mail activation and repeat login')
} finally {
  await browser.close()
}
