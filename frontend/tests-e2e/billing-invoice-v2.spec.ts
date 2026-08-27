import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { openFulfillmentRegistration } from './auth-flow'
import { waitForGetOk, waitForPostOk } from './api-waits'

// Вкладка «Выставленные счета» проверяется на НАСТОЯЩЕМ сервере: Playwright
// поднимает uvicorn с реальной базой. Подменять здесь API нельзя — именно
// зелёный прогон на выдуманных данных в прошлый раз скрыл, что экран и сервер
// вообще не состыкованы.

const API = process.env.E2E_API_ORIGIN ?? `http://127.0.0.1:${process.env.E2E_API_PORT ?? '18000'}`

async function registerAdmin(page: Page, suffix: string) {
  await page.goto('/')
  await openFulfillmentRegistration(page)
  const form = page.getByTestId('register-form')
  await form.getByLabel('Организация').fill(`Счета ${suffix}`)
  await form.getByLabel('Email администратора').fill(`invoice-v2-${suffix}@example.com`)
  await form.getByLabel('Пароль').fill('password123')
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    form.getByRole('button', { name: 'Создать аккаунт' }).click(),
  ])
  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'))
  expect(token, 'после регистрации должен быть токен ФФ').toBeTruthy()
  return token as string
}

async function createSeller(request: APIRequestContext, token: string, name: string) {
  const response = await request.post(`${API}/sellers`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  return (await response.json()).id as string
}

async function createManualInvoice(
  request: APIRequestContext,
  token: string,
  sellerId: string,
  description: string,
  amount: string,
  key: string,
) {
  const response = await request.post(`${API}/billing/invoices-v2`, {
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': key },
    data: {
      creation_mode: 'manual',
      seller_id: sellerId,
      lines: [{ description, amount }],
    },
  })
  expect(response.status(), await response.text()).toBe(201)
  return await response.json()
}

// TC-NEW-205 — Дано выставленный счёт, Когда администратор открывает вкладку
// «Выставленные счета», Тогда он видит его в истории и может открыть карточку.
test('TC-NEW-205 история счетов показывает документ и открывает его карточку', async ({
  page,
  request,
}) => {
  const suffix = String(Date.now())
  const token = await registerAdmin(page, suffix)
  const sellerId = await createSeller(request, token, `Селлер ${suffix}`)
  const invoice = await createManualInvoice(
    request,
    token,
    sellerId,
    'Упаковка партии',
    '1250.40',
    `e2e-${suffix}`,
  )

  await page.goto('/app/ff/billing')
  await Promise.all([
    waitForGetOk(page, '/api/billing/invoices-v2'),
    page.getByTestId('billing-tab-invoices').click(),
  ])

  const table = page.getByTestId('billing-invoices-table')
  await expect(table).toContainText(invoice.number)
  await expect(table).toContainText(`Селлер ${suffix}`)
  // Ручной счёт периода не имеет — врать про период нельзя.
  await expect(table).toContainText('Без периода')
  await expect(table).toContainText('1 250,40')
  await expect(table).toContainText('Выставлен')

  await page.getByTestId(`billing-invoice-open-${invoice.id}`).click()
  const dialog = page.getByTestId('billing-invoice-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('Упаковка партии')
  await expect(dialog).toContainText('Итого: 1 250,40')

  // Печать и отмена доступны прямо из карточки.
  await expect(page.getByTestId('billing-invoice-print')).toBeVisible()
  await expect(page.getByTestId('billing-invoice-cancel')).toBeVisible()
})

// TC-NEW-206 — Дано открытый счёт, Когда администратор подтверждает отмену,
// Тогда счёт остаётся в истории со статусом «Отменён».
// Негатив: отменённый счёт не исчезает из списка и не предлагает отмену снова.
test('TC-NEW-206 отменённый счёт остаётся в истории и больше не отменяется', async ({
  page,
  request,
}) => {
  const suffix = String(Date.now())
  const token = await registerAdmin(page, suffix)
  const sellerId = await createSeller(request, token, `Селлер ${suffix}`)
  const invoice = await createManualInvoice(
    request,
    token,
    sellerId,
    'Разовая услуга',
    '99.00',
    `e2e-cancel-${suffix}`,
  )

  await page.goto('/app/ff/billing')
  await Promise.all([
    waitForGetOk(page, '/api/billing/invoices-v2'),
    page.getByTestId('billing-tab-invoices').click(),
  ])
  await page.getByTestId(`billing-invoice-open-${invoice.id}`).click()
  await page.getByTestId('billing-invoice-cancel').click()
  await Promise.all([
    waitForPostOk(page, `/api/billing/invoices-v2/${invoice.id}/cancel`),
    page.getByTestId('billing-invoice-cancel-confirm').click(),
  ])

  const dialog = page.getByTestId('billing-invoice-dialog')
  await expect(dialog).toContainText('Отменён')
  await expect(page.getByTestId('billing-invoice-cancel')).toBeHidden()

  await page.getByRole('button', { name: 'Закрыть' }).click()
  const table = page.getByTestId('billing-invoices-table')
  await expect(table).toContainText(invoice.number)
  await expect(table).toContainText('Отменён')
})

// TC-NEW-207 — Дано пустую историю, Когда счетов ещё нет,
// Тогда экран объясняет, где счёт выставляется, а не показывает голую таблицу.
test('TC-NEW-207 пустая история ведёт оператора на вкладку «Селлеры»', async ({ page }) => {
  const suffix = String(Date.now())
  await registerAdmin(page, suffix)

  await page.goto('/app/ff/billing')
  await Promise.all([
    waitForGetOk(page, '/api/billing/invoices-v2'),
    page.getByTestId('billing-tab-invoices').click(),
  ])
  const table = page.getByTestId('billing-invoices-table')
  await expect(table).toContainText('Счета ещё не выставлены')
  await expect(table).toContainText('Выставьте счёт на вкладке «Селлеры»')
})

// TC-NEW-208 — Дано счета двух селлеров, Когда выбран один селлер и статус,
// Тогда фильтры сужают историю на сервере, а не в браузере.
test('TC-NEW-208 фильтры истории отсекают чужие счета', async ({ page, request }) => {
  const suffix = String(Date.now())
  const token = await registerAdmin(page, suffix)
  const firstSeller = await createSeller(request, token, `Первый ${suffix}`)
  const secondSeller = await createSeller(request, token, `Второй ${suffix}`)
  const first = await createManualInvoice(request, token, firstSeller, 'Первая', '10.00', `f-${suffix}`)
  const second = await createManualInvoice(request, token, secondSeller, 'Вторая', '20.00', `s-${suffix}`)

  await page.goto('/app/ff/billing')
  await Promise.all([
    waitForGetOk(page, '/api/billing/invoices-v2'),
    page.getByTestId('billing-tab-invoices').click(),
  ])
  const table = page.getByTestId('billing-invoices-table')
  await expect(table).toContainText(first.number)
  await expect(table).toContainText(second.number)

  await Promise.all([
    waitForGetOk(page, '/api/billing/invoices-v2'),
    page.getByTestId('billing-seller').selectOption({ label: `Первый ${suffix}` }),
  ])
  await expect(table).toContainText(first.number)
  await expect(table).not.toContainText(second.number)

  await Promise.all([
    waitForGetOk(page, '/api/billing/invoices-v2'),
    page.getByTestId('billing-status').selectOption({ label: 'Отменён' }),
  ])
  await expect(table).toContainText('Счета ещё не выставлены')
})

// TC-NEW-209 — Дано вкладку «Селлеры» с включёнными финансами, Когда ничего не
// выбрано и нажата «Выставить счёт», Тогда открывается ручная форма, счёт
// сохраняется и появляется в истории.
// Ограничение: кнопка доступна всегда при включённых финансах — иначе, пока у
// селлеров нет ни одной операции, ручной счёт выставить было бы нечем.
test('TC-NEW-209 ручной счёт выставляется с вкладки «Селлеры» и попадает в историю', async ({
  page,
  request,
}) => {
  const suffix = String(Date.now())
  const token = await registerAdmin(page, suffix)
  await createSeller(request, token, `Ручной ${suffix}`)

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-seller-finance').click()
  const issue = page.getByTestId('billing-issue-invoice')
  await expect(issue).toBeVisible()
  await issue.click()

  const manual = page.getByTestId('billing-invoice-manual')
  await expect(manual).toBeVisible()
  await manual.getByTestId('billing-manual-seller').selectOption({ label: `Ручной ${suffix}` })
  await manual.getByTestId('billing-manual-description-0').fill('Погрузка паллет')
  await manual.getByTestId('billing-manual-amount-0').fill('740.50')

  await Promise.all([
    waitForPostOk(page, '/api/billing/invoices-v2/preview'),
    manual.getByTestId('billing-manual-preview').click(),
  ])
  const preview = page.getByTestId('billing-invoice-preview')
  await expect(preview).toContainText('Погрузка паллет')
  await expect(preview).toContainText('Итого: 740,50')

  await Promise.all([
    waitForPostOk(page, '/api/billing/invoices-v2'),
    preview.getByTestId('billing-invoice-save').click(),
  ])
  await expect(preview).toContainText('выставлен')
  await preview.getByRole('button', { name: 'Закрыть' }).click()

  await Promise.all([
    waitForGetOk(page, '/api/billing/invoices-v2'),
    page.getByTestId('billing-tab-invoices').click(),
  ])
  const table = page.getByTestId('billing-invoices-table')
  await expect(table).toContainText('740,50')
  await expect(table).toContainText(`Ручной ${suffix}`)
})

// TC-NEW-210 — Дано выключённые «Финансы», Когда открыта вкладка «Селлеры»,
// Тогда кнопки выставления счёта нет.
// Негатив: денежное действие не должно быть доступно в режиме без денег.
test('TC-NEW-210 без «Финансов» кнопка выставления счёта скрыта', async ({ page }) => {
  const suffix = String(Date.now())
  await registerAdmin(page, suffix)

  await page.goto('/app/ff/billing')
  await expect(page.getByTestId('billing-issue-invoice')).toBeHidden()

  await page.getByTestId('billing-seller-finance').click()
  await expect(page.getByTestId('billing-issue-invoice')).toBeVisible()

  await page.getByTestId('billing-seller-finance').click()
  await expect(page.getByTestId('billing-issue-invoice')).toBeHidden()
})

// TC-NEW-211 — Дано ручную форму, Когда сумма указана мельче копейки,
// Тогда поле помечено недопустимым и счёт не собирается.
// Негатив: сумма с третьим знаком не должна доезжать до сохранения.
test('TC-NEW-211 ручная форма не пропускает сумму мельче копейки', async ({ page, request }) => {
  const suffix = String(Date.now())
  const token = await registerAdmin(page, suffix)
  await createSeller(request, token, `Копейки ${suffix}`)

  await page.goto('/app/ff/billing')
  await page.getByTestId('billing-seller-finance').click()
  await page.getByTestId('billing-issue-invoice').click()

  const manual = page.getByTestId('billing-invoice-manual')
  await manual.getByTestId('billing-manual-seller').selectOption({ label: `Копейки ${suffix}` })
  await manual.getByTestId('billing-manual-description-0').fill('Услуга')
  await manual.getByTestId('billing-manual-amount-0').fill('10.005')
  await expect(manual.getByTestId('billing-manual-amount-0')).toHaveAttribute('aria-invalid', 'true')

  await manual.getByTestId('billing-manual-preview').click()
  await expect(manual.getByTestId('billing-manual-error')).toContainText(
    'Сумма указывается с точностью до копеек',
  )
  await expect(page.getByTestId('billing-invoice-preview')).toBeHidden()
})
