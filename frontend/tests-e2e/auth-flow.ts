import type { Page } from '@playwright/test';

import { waitForPostOk } from './api-waits';

/** Публичный экран по умолчанию показывает вход; регистрация — по кнопке. */
export async function openFulfillmentRegistration(page: Page): Promise<void> {
  await page.getByTestId('go-to-register').click();
  await page.getByTestId('register-form').waitFor({ state: 'visible' });
}

/**
 * Вход селлера. При firstTime — пустой пароль и при необходимости экран установки пароля.
 */
export async function loginAsSeller(
  page: Page,
  email: string,
  password: string,
  opts?: { firstTime?: boolean },
): Promise<void> {
  const firstTime = opts?.firstTime ?? true;
  await page.getByTestId('login-form').getByLabel('Email').fill(email);
  const pass = page.getByTestId('login-form').getByLabel('Пароль');
  if (firstTime) {
    await pass.fill('');
  } else {
    await pass.fill(password);
  }
  await Promise.all([
    page.waitForResponse((r) => {
      if (!r.url().includes('/api/auth/login')) {
        return false;
      }
      return r.status() === 200 || r.status() === 403;
    }),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);
  const setup = page.getByTestId('seller-password-setup-form');
  if (await setup.isVisible()) {
    await setup.getByLabel('Новый пароль').fill(password);
    await setup.getByLabel('Повтор пароля').fill(password);
    await Promise.all([
      waitForPostOk(page, '/api/auth/set-initial-password'),
      page.getByTestId('seller-password-setup-submit').click(),
    ]);
  }
}
