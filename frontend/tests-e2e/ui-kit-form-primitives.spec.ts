import { expect, test, type Page } from '@playwright/test'

// Поведение общих примитивов доказывается в настоящем браузере на витрине канона.
// Юнит-слой проекта работает в `environment: 'node'` без DOM, поэтому проверить
// клик, фокус и Escape там физически нечем: там остаются только чистые функции.

const SHOWCASE = '/ui-kit.html'

async function openShowcase(page: Page) {
  await page.goto(SHOWCASE)
  await expect(page.getByTestId('showcase-checkbox-input')).toBeVisible()
}

// TC-NEW-101 — Дано витрину канона, Когда оператор кликает подписанный checkbox,
// Тогда состояние действительно переключается в обе стороны.
test('TC-NEW-101 CheckboxInput действительно переключается по клику на подпись', async ({ page }) => {
  await openShowcase(page)
  const checkbox = page.getByTestId('showcase-checkbox-input')
  await expect(checkbox).not.toBeChecked()

  // Клик именно по видимой подписи: оператор попадает в неё, а не в квадрат 18×18.
  await page.getByText('Выбрать операцию', { exact: true }).click()
  await expect(checkbox).toBeChecked()

  await page.getByText('Выбрать операцию', { exact: true }).click()
  await expect(checkbox).not.toBeChecked()
})

// TC-NEW-102 — Дано недоступный выбор, Когда оператор пытается его нажать,
// Тогда состояние не меняется, а причина недоступности читается программой чтения.
// Негатив: недоступный checkbox не должен молча игнорировать клик без объяснения.
test('TC-NEW-102 недоступный CheckboxInput не переключается и объясняет причину', async ({ page }) => {
  await openShowcase(page)
  const disabled = page.getByTestId('showcase-disabled-checkbox-input')
  await expect(disabled).toBeDisabled()
  await expect(disabled).not.toBeChecked()

  await page.getByText('Недоступная операция', { exact: true }).click({ force: true })
  await expect(disabled).not.toBeChecked()

  // Причина недоступности связана с полем, а не спрятана в одном лишь tooltip.
  const describedBy = await disabled.getAttribute('aria-describedby')
  expect(describedBy).toBeTruthy()
  await expect(page.locator(`#${describedBy}`)).toHaveText('Операция не рассчитана')
})

// TC-NEW-103 — Дано денежное поле, Когда вводится сумма с копейками,
// Тогда строка сохраняется посимвольно и не проходит через число.
// Ограничение: `12.20` обязано остаться `12.20`, а не превратиться в `12.2`.
test('TC-NEW-103 MoneyInput сохраняет точную десятичную строку без приведения к числу', async ({ page }) => {
  await openShowcase(page)
  const money = page.getByTestId('showcase-money-input')

  await money.fill('12.20')
  await expect(money).toHaveValue('12.20')
  await expect(money).toHaveAttribute('aria-invalid', 'false')

  await money.fill('0.29')
  await expect(money).toHaveValue('0.29')
  await expect(money).toHaveAttribute('aria-invalid', 'false')
})

// TC-NEW-104 — Дано денежное поле, Когда сумма мельче копейки или отрицательна,
// Тогда поле помечается недопустимым и показывает понятную причину.
// Негатив: третий знак после точки и минус не должны молча доезжать до API.
test('TC-NEW-104 MoneyInput помечает недопустимую сумму и объясняет ошибку', async ({ page }) => {
  await openShowcase(page)
  const money = page.getByTestId('showcase-money-input')

  await money.fill('12.205')
  await expect(money).toHaveAttribute('aria-invalid', 'true')
  const describedBy = await money.getAttribute('aria-describedby')
  expect(describedBy).toBeTruthy()
  await expect(page.locator(`#${describedBy}`)).toHaveText('Укажите сумму с точностью до копеек')

  await money.fill('-5.00')
  await expect(money).toHaveAttribute('aria-invalid', 'true')
  await expect(page.locator(`#${describedBy}`)).toHaveText('Сумма не может быть отрицательной')

  await money.fill('5.00')
  await expect(money).toHaveAttribute('aria-invalid', 'false')
})

// TC-NEW-105 — Дано модальное окно канона, Когда оно открыто,
// Тогда заголовок связан с окном, фокус уходит внутрь и не покидает его по Tab.
test('TC-NEW-105 AppDialog связывает заголовок и удерживает фокус внутри', async ({ page }) => {
  await openShowcase(page)
  await page.getByRole('button', { name: 'Открыть окно' }).click()

  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()

  // Заголовок связан через aria-labelledby, а не просто нарисован сверху.
  const labelledBy = await dialog.getAttribute('aria-labelledby')
  expect(labelledBy).toBeTruthy()
  await expect(page.locator(`#${labelledBy}`)).toHaveText('Подтвердите действие')

  // Начальный фокус уже внутри модалки. Проверяем именно корень модалки:
  // MUI отдаёт фокус контейнеру `.MuiDialog-container`, который лежит рядом с
  // `[role="dialog"]`, а не внутри него.
  const focusInsideModal = () =>
    page.evaluate(() => {
      const root = document.querySelector('[data-testid="showcase-app-dialog"]')
      return Boolean(root && document.activeElement && root.contains(document.activeElement))
    })

  await expect.poll(focusInsideModal).toBe(true)

  // Фокус не выпадает наружу: десяти табов достаточно, чтобы обойти ловушку по кругу.
  for (let step = 0; step < 10; step += 1) {
    await page.keyboard.press('Tab')
    expect(await focusInsideModal(), `фокус ушёл из окна на шаге ${step + 1}`).toBe(true)
  }
})

// TC-NEW-107 — Дано витрину канона, Когда открывается модальное окно,
// Тогда React не сообщает о нераспознанных пропсах на DOM-узле.
// Ограничение: пропс, который React отбросил, ничего не настраивает — молчаливо
// мёртвая «настройка доступности» уже один раз прошла зелёный юнит-тест.
test('TC-NEW-107 общие примитивы не роняют пропсы на DOM мимо MUI', async ({ page }) => {
  const leaked: string[] = []
  page.on('console', (message) => {
    const text = message.text()
    if (message.type() === 'error' && /does not recognize the `|Unknown prop|Warning: Invalid DOM property/.test(text)) {
      leaked.push(text)
    }
  })

  await openShowcase(page)
  await page.getByRole('button', { name: 'Открыть окно' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()

  expect(leaked, `React отбросил пропсы: ${leaked.join(' | ')}`).toEqual([])
})

// TC-NEW-106 — Дано открытое модальное окно, Когда нажат Escape,
// Тогда окно закрывается и фокус возвращается кнопке, которая его открыла.
// Ограничение: без возврата фокуса оператор с клавиатуры теряет место на странице.
test('TC-NEW-106 AppDialog закрывается по Escape и возвращает фокус триггеру', async ({ page }) => {
  await openShowcase(page)
  const trigger = page.getByRole('button', { name: 'Открыть окно' })
  await trigger.click()
  await expect(page.getByRole('dialog')).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()

  await expect
    .poll(() => page.evaluate(() => document.activeElement?.textContent?.trim()))
    .toBe('Открыть окно')
})
