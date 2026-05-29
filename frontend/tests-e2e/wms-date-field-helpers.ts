import type { Page } from '@playwright/test';

/** ISO YYYY-MM-DD → ru display DD.MM.YYYY for MUI DatePicker. */
export function isoDateRu(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

/** Fill WmsDateField (MUI DatePicker, ru locale) and blur to commit. */
export async function setWmsDateField(
  page: Page,
  testId: string,
  isoDate: string,
): Promise<void> {
  const input = page.getByTestId(testId).locator('input').first();
  await input.waitFor({ state: 'visible' });
  await input.click();
  await input.fill(isoDateRu(isoDate));
  await input.blur();
}
