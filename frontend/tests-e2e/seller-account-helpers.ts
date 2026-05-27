import { expect, type APIRequestContext } from '@playwright/test';

export async function createSellerAccountViaApi(
  request: APIRequestContext,
  headers: Record<string, string>,
  sellerId: string,
  email: string,
): Promise<void> {
  const res = await request.post('/api/auth/seller-accounts', {
    headers,
    data: { seller_id: sellerId, email },
  });
  expect(res.ok()).toBeTruthy();
}
