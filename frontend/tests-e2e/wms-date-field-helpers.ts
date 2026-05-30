import { expect, type Page } from '@playwright/test';

/** ISO YYYY-MM-DD → ru display DD.MM.YYYY for MUI DatePicker. */
export function isoDateRu(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

const MONTH_RU = [
  'январ',
  'феврал',
  'март',
  'апрел',
  'май',
  'июн',
  'июл',
  'август',
  'сентябр',
  'октябр',
  'ноябр',
  'декабр',
];

/** Close MUI Select/Popover overlays without Escape (Escape closes full-screen Dialog). */
async function dismissOpenMenus(page: Page): Promise<void> {
  const menu = page.locator(
    '[role="presentation"].MuiMenu-root, [role="presentation"].MuiPopover-root',
  );
  if (!(await menu.first().isVisible().catch(() => false))) {
    return;
  }
  const dialog = page.getByRole('dialog').first();
  if (await dialog.isVisible().catch(() => false)) {
    await dialog.getByRole('heading').first().click();
  } else {
    await page.locator('main').first().click({ position: { x: 8, y: 8 } });
  }
  await menu.first().waitFor({ state: 'hidden', timeout: 5000 }).catch(() => undefined);
}

async function fillViaCalendar(
  page: Page,
  root: ReturnType<Page['getByTestId']>,
  isoDate: string,
): Promise<void> {
  const [yearStr, monthStr, dayStr] = isoDate.split('-');
  const monthHint = MONTH_RU[Number(monthStr) - 1] ?? '';
  const dayNum = String(Number(dayStr));

  await root.getByRole('button', { name: 'Choose date' }).click();
  const calendar = page.locator('.MuiDateCalendar-root').last();
  await calendar.waitFor({ state: 'visible' });

  for (let step = 0; step < 36; step += 1) {
    const header = ((await calendar.locator('.MuiPickersCalendarHeader-label').textContent()) ?? '')
      .toLowerCase()
      .replace(/\s+/g, ' ');
    if (header.includes(yearStr) && header.includes(monthHint)) {
      break;
    }
    await calendar.getByRole('button', { name: 'Next month' }).click();
  }

  const monthGrid = calendar.getByRole('grid', {
    name: new RegExp(`${monthHint}.*${yearStr}`, 'i'),
  });
  await monthGrid.getByRole('gridcell', { name: dayNum, exact: true }).first().click();
  await calendar.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => undefined);
}

async function fillViaSpinbuttons(
  page: Page,
  testId: string,
  isoDate: string,
): Promise<void> {
  const root = page.getByTestId(testId);
  const [yearStr, monthStr, dayStr] = isoDate.split('-');
  const parts: Array<{ label: 'Day' | 'Month' | 'Year'; value: string }> = [
    { label: 'Day', value: dayStr.padStart(2, '0') },
    { label: 'Month', value: monthStr.padStart(2, '0') },
    { label: 'Year', value: yearStr },
  ];
  for (const part of parts) {
    const section = root.getByRole('spinbutton', { name: part.label });
    await section.waitFor({ state: 'visible' });
    await section.click({ force: true });
    await page.keyboard.press('ControlOrMeta+a');
    await page.keyboard.press('Backspace');
    await page.keyboard.type(part.value, { delay: 60 });
  }
  await root.getByRole('spinbutton', { name: 'Year' }).blur();
}

/** Fill WmsDateField (MUI X v9, ru locale). */
export async function setWmsDateField(
  page: Page,
  testId: string,
  isoDate: string,
): Promise<void> {
  await dismissOpenMenus(page);
  await page
    .locator('[role="presentation"].MuiMenu-root, [role="presentation"].MuiPopover-root')
    .first()
    .waitFor({ state: 'hidden', timeout: 5000 })
    .catch(() => undefined);

  const root = page.getByTestId(testId);
  await root.waitFor({ state: 'visible' });

  const [yearStr] = isoDate.split('-');
  const chooseDate = root.getByRole('button', { name: 'Choose date' });
  if (await chooseDate.isVisible().catch(() => false)) {
    await fillViaCalendar(page, root, isoDate);
  } else {
    await fillViaSpinbuttons(page, testId, isoDate);
  }

  await expect(root.getByRole('spinbutton', { name: 'Year' })).toHaveText(yearStr, {
    timeout: 5000,
  });
}
