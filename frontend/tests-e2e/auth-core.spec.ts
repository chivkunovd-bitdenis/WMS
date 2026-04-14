import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';

// TC-S01-002 — регистрация отклоняется при дубликате slug/email (валидация и сообщение).
test('registration rejected on duplicate slug', async ({ page }) => {
  const slug = `ff-dup-${Date.now()}`;
  const email1 = `e2e-dup1-${Date.now()}@example.com`;
  const email2 = `e2e-dup2-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('register-form')).toBeVisible();

  // First registration succeeds.
  await page.getByTestId('register-form').getByLabel('Организация').fill('Dup Slug Org 1');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email1);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await page.getByTestId('logout').click();
  await expect(page.getByTestId('register-form')).toBeVisible();

  // Second registration with same slug must fail visibly.
  await page.getByTestId('register-form').getByLabel('Организация').fill('Dup Slug Org 2');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email2);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/register') && r.status() >= 400),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('auth-error')).toBeVisible();
  await expect(page.getByTestId('dashboard')).toHaveCount(0);
});

// TC-S02-002 — ошибка логина при неверном пароле (без доступа в приватные разделы).
test('login failure shows error and does not enter app', async ({ page }) => {
  const slug = `ff-wrongpass-${Date.now()}`;
  const email = `e2e-wrongpass-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('register-form')).toBeVisible();

  await page.getByTestId('register-form').getByLabel('Организация').fill('Wrong Pass Org');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();

  await page.getByTestId('login-form').getByLabel('Email').fill(email);
  await page.getByTestId('login-form').getByLabel('Пароль').fill('wrong-password');

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/login') && r.status() >= 400),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);

  await expect(page.getByTestId('auth-error')).toBeVisible();
  await expect(page.getByTestId('catalog-section')).toHaveCount(0);
  await expect(page.getByTestId('operations-section')).toHaveCount(0);
});

// TC-S02-003 — логаут возвращает на публичный экран; приватные секции скрыты.
// TC-S15-001 — меню/разделы видимы после входа.
test('logout returns to public screen and hides private sections', async ({ page }) => {
  const slug = `ff-logout-${Date.now()}`;
  const email = `e2e-logout-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('register-form')).toBeVisible();

  await page.getByTestId('register-form').getByLabel('Организация').fill('Logout Org');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('app-section-nav')).toBeVisible();
  await expect(page.getByTestId('catalog-section')).toBeVisible();
  await expect(page.getByTestId('operations-section')).toBeVisible();

  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await expect(page.getByTestId('catalog-section')).toHaveCount(0);
  await expect(page.getByTestId('operations-section')).toHaveCount(0);
});

// TC-S15-002 — состояние загрузки профиля (индикатор loading виден, затем исчезает).
test('profile loading state appears while /me is slow', async ({ page }) => {
  const slug = `ff-loading-${Date.now()}`;
  const email = `e2e-loading-${Date.now()}@example.com`;
  const password = 'password123';

  await page.goto('/');
  await expect(page.getByTestId('register-form')).toBeVisible();

  await page.getByTestId('register-form').getByLabel('Организация').fill('Loading Org');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);

  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await page.getByTestId('logout').click();
  await expect(page.getByTestId('login-form')).toBeVisible();

  await page.getByTestId('login-form').getByLabel('Email').fill(email);
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password);

  // Delay /api/auth/me to force visible loading state.
  await page.route('**/api/auth/me', async (route) => {
    await new Promise((r) => setTimeout(r, 1200));
    await route.continue();
  });

  await Promise.all([
    waitForPostOk(page, '/api/auth/login'),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);

  await expect(page.getByTestId('loading')).toBeVisible();
  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('loading')).toHaveCount(0);
});

