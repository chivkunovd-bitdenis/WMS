import type { Page } from '@playwright/test';

/** ISO YYYY-MM-DD → ru display DD.MM.YYYY for MUI DatePicker. */
export function isoDateRu(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

async function dismissOpenMenus(page: Page): Promise<void> {
  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');
  const menu = page.locator('[role="presentation"].MuiMenu-root');
  if (await menu.count()) {
    await menu.first().waitFor({ state: 'hidden', timeout: 5000 }).catch(() => undefined);
  }
}

async function fillDateSection(
  page: Page,
  root: ReturnType<Page['getByTestId']>,
  label: 'Day' | 'Month' | 'Year',
  value: string,
): Promise<void> {
  const section = root.getByRole('spinbutton', { name: label });
  await section.click();
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type(value);
}

/** Fill WmsDateField (MUI X v9 section field, ru locale). */
export async function setWmsDateField(
  page: Page,
  testId: string,
  isoDate: string,
): Promise<void> {
  await dismissOpenMenus(page);

  const root = page.getByTestId(testId);
  await root.waitFor({ state: 'visible' });

  const [yearStr, monthStr, dayStr] = isoDate.split('-');
  await fillDateSection(page, root, 'Day', dayStr.padStart(2, '0'));
  await fillDateSection(page, root, 'Month', monthStr.padStart(2, '0'));
  await fillDateSection(page, root, 'Year', yearStr);
  await root.getByRole('spinbutton', { name: 'Year' }).blur();
}
