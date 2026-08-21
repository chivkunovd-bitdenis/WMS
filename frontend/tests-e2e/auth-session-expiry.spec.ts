import { test, expect, type Page, type Route } from '@playwright/test';

const EXPIRED_NOTICE =
  'Сессия завершилась. Войдите снова, чтобы продолжить работу.';

type Portal = 'fulfillment' | 'seller';

function profileFor(portal: Portal) {
  return portal === 'fulfillment'
    ? {
        email: 'ff-e2e@example.com',
        organization_name: 'Local E2E Fulfillment',
        role: 'fulfillment_admin',
      }
    : {
        email: 'seller-e2e@example.com',
        organization_name: 'Local E2E Seller',
        role: 'fulfillment_seller',
        seller_id: 'seller-e2e',
        seller_name: 'Local E2E Seller',
        active_seller_id: 'seller-e2e',
        active_seller_name: 'Local E2E Seller',
      };
}

async function json(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function installAuthMocks(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const authorization = request.headers().authorization ?? '';
    const portal: Portal = url.pathname.startsWith('/api/') &&
      page.url().includes('/seller')
      ? 'seller'
      : 'fulfillment';

    if (path.endsWith('/auth/me')) {
      if (authorization.includes('expired-')) {
        await json(route, 401, { detail: 'invalid_token' });
        return;
      }
      await json(route, 200, profileFor(portal));
      return;
    }

    if (path.endsWith('/auth/login')) {
      await json(route, 200, {
        access_token: `fresh-${portal}-token`,
      });
      return;
    }

    // Authenticated screens issue read requests on mount. Empty local data keeps
    // the test focused on the auth boundary and prevents any real API egress.
    await json(route, 200, []);
  });
}

async function seedExpiredSession(page: Page, portal: Portal): Promise<void> {
  await page.addInitScript((selectedPortal) => {
    localStorage.setItem(
      selectedPortal === 'seller' ? 'wms_token_seller' : 'wms_token_ff',
      `expired-${selectedPortal}-token`,
    );
    localStorage.setItem(
      selectedPortal === 'seller' ? 'wms_token_ff' : 'wms_token_seller',
      `other-${selectedPortal}-session`,
    );
  }, portal);
}

for (const portal of ['fulfillment', 'seller'] as const) {
  test(`${portal} invalid_token shows safe recovery and clears only its session`, async ({
    page,
  }) => {
    await installAuthMocks(page);
    await seedExpiredSession(page, portal);
    await page.goto(portal === 'seller' ? '/seller/' : '/app/ff/dashboard');

    await expect(page.getByTestId('session-expired-notice')).toHaveText(EXPIRED_NOTICE);
    await expect(page.getByTestId('login-form')).toBeVisible();
    await expect(page.locator('body')).not.toContainText('invalid_token');
    await expect(page.locator('body')).not.toContainText('401');
    await expect(page.locator('body')).not.toContainText('токен');

    await expect
      .poll(() =>
        page.evaluate((selectedPortal) => ({
          selected: localStorage.getItem(
            selectedPortal === 'seller' ? 'wms_token_seller' : 'wms_token_ff',
          ),
          other: localStorage.getItem(
            selectedPortal === 'seller' ? 'wms_token_ff' : 'wms_token_seller',
          ),
        }), portal),
      )
      .toEqual({ selected: null, other: `other-${portal}-session` });
  });
}

test('fulfillment restores a verified same-portal target once after login', async ({ page }) => {
  await installAuthMocks(page);
  await seedExpiredSession(page, 'fulfillment');
  await page.goto('/app/ff/dashboard?source=expiry#resume');

  await expect(page.getByTestId('session-expired-notice')).toBeVisible();
  await page.getByTestId('login-form').getByLabel('Email').fill('ff-e2e@example.com');
  await page.getByTestId('login-form').getByLabel('Пароль').fill('local-password');
  await page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click();

  await expect(page).toHaveURL(/\/app\/ff\/dashboard\?source=expiry#resume$/);
  await expect(page.getByTestId('session-expired-notice')).toHaveCount(0);
  await page.goBack();
  await expect(page.getByTestId('session-expired-notice')).toHaveCount(0);
});
