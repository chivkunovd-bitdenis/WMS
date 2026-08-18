# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: f05-browser-product-qa-final-current.spec.ts >> F05 final current — FF conducts receiving and seller opens the same factual card
- Location: ../docs/reviews/product-operations-ux/2026-08-12/evidence/f05-browser-product-qa-final-current/f05-browser-product-qa-final-current.spec.ts:233:5

# Error details

```
Error: expect(received).toBeLessThanOrEqual(expected)

Expected: <= 959
Received:    1080
```

# Test source

```ts
  292 |   await expect(ffAddedRow.getByTestId('ff-inbound-line-actual-display')).toHaveText('1');
  293 |   await expect(ffAddedRow.getByTestId('ff-inbound-line-discrepancy')).toHaveText('Излишек 1');
  294 |   await screenshot(page, '01-ff-card-before-complete-1280.png', true);
  295 | 
  296 |   await page.getByTestId('ff-inbound-verify-complete').click();
  297 |   recordStep('FF clicked complete receiving');
  298 |   await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
  299 |   await expect(page.getByTestId('ff-inbound-discrepancy-line').filter({ hasText: seed.sku })).toContainText(
  300 |     'Недостача 1',
  301 |   );
  302 |   await expect(page.getByTestId('ff-inbound-discrepancy-line').filter({ hasText: addedSku })).toContainText(
  303 |     'Излишек 1',
  304 |   );
  305 |   await screenshot(page, '02-ff-discrepancy-dialog-1280.png', true);
  306 |   await Promise.all([
  307 |     waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
  308 |     page.getByTestId('ff-inbound-discrepancy-confirm').click(),
  309 |   ]);
  310 |   recordStep('FF confirmed discrepancy completion');
  311 |   await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
  312 | 
  313 |   await page.route('**/api/operations/marketplace-unload-requests', async (route) => {
  314 |     if (route.request().method() === 'GET') {
  315 |       await route.fulfill({
  316 |         status: 200,
  317 |         contentType: 'application/json',
  318 |         body: JSON.stringify([
  319 |           { id: 'mp-collecting-f05', status: 'collecting', line_count: 1, created_at: '2026-08-13T10:00:00Z' },
  320 |           { id: 'mp-cancelled-f05', status: 'cancelled', line_count: 1, created_at: '2026-08-12T10:00:00Z' },
  321 |         ]),
  322 |       });
  323 |       return;
  324 |     }
  325 |     await route.fallback();
  326 |   });
  327 | 
  328 |   await loginSellerPortal(page, seed.sellerEmail, seed.password);
  329 |   recordStep('Seller logged in through the seller portal');
  330 |   await page.getByTestId('nav-seller-documents').click();
  331 |   recordStep('Seller opened documents');
  332 |   await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  333 |   const documentsText = await visibleText(page.getByTestId('seller-documents-table'));
  334 |   expect(documentsText).toContain('Поставка');
  335 |   expect(documentsText).toContain('В сортировке');
  336 |   expect(documentsText).toContain('На сборке');
  337 |   expect(documentsText).toContain('Отменено');
  338 |   expectNoRawTechnicalText(documentsText);
  339 |   qaResult.checks.documentsHumanStatuses = documentsText;
  340 |   saveResult();
  341 |   await screenshot(page, '03-seller-documents-human-statuses-1280.png', true);
  342 | 
  343 |   const sellerDocRow = page.locator(`[data-testid="seller-documents-row"][data-doc-id="${requestId}"]`);
  344 |   await expect(sellerDocRow).toBeVisible();
  345 |   await sellerDocRow.click();
  346 |   recordStep('Seller opened the same conducted inbound card');
  347 | 
  348 |   await expect(page.getByRole('heading', { name: /Карточка приёмки.*Поставка/ })).toBeVisible();
  349 |   await expect(page.getByText('Новая заявка на поставку', { exact: true })).toHaveCount(0);
  350 |   await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  351 |   await expect(page.getByTestId('seller-inbound-draft-form')).toHaveCount(0);
  352 |   await expect(page.getByTestId('seller-inbound-add-products')).toHaveCount(0);
  353 |   await expect(page.getByTestId('seller-inbound-submit-warehouse')).toHaveCount(0);
  354 |   await expect(page.getByTestId('seller-inbound-save-draft')).toHaveCount(0);
  355 |   await expect(page.getByTestId('seller-inbound-line-delete')).toHaveCount(0);
  356 | 
  357 |   await expect(page.getByTestId('seller-inbound-summary-status')).toContainText('В сортировке');
  358 |   await expect(page.getByTestId('seller-inbound-summary-operation')).toContainText('Поставка');
  359 |   await expect(page.getByTestId('seller-inbound-summary-warehouse')).toContainText('WH');
  360 |   await expect(page.getByTestId('seller-inbound-summary-boxes')).toContainText('План 2');
  361 |   await expect(page.getByTestId('seller-inbound-summary-discrepancy')).toContainText('Есть');
  362 |   await expect(page.getByTestId('seller-inbound-summary-units')).toContainText('Заявлено 3');
  363 |   await expect(page.getByTestId('seller-inbound-summary-units')).toContainText('Факт 3');
  364 | 
  365 |   const sellerShortageRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: seed.sku });
  366 |   await expect(sellerShortageRow).toBeVisible();
  367 |   await expect(sellerShortageRow.getByTestId('seller-inbound-line-expected')).toHaveText('3');
  368 |   await expect(sellerShortageRow.getByTestId('seller-inbound-line-actual')).toHaveText('2');
  369 |   await expect(sellerShortageRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Недостача 1');
  370 | 
  371 |   const sellerAddedRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: addedSku });
  372 |   await expect(sellerAddedRow).toBeVisible();
  373 |   await expect(sellerAddedRow.getByTestId('seller-inbound-line-added-by-ff')).toContainText('Добавлено ФФ');
  374 |   await expect(sellerAddedRow.getByTestId('seller-inbound-line-expected')).toHaveText('0');
  375 |   await expect(sellerAddedRow.getByTestId('seller-inbound-line-actual')).toHaveText('1');
  376 |   await expect(sellerAddedRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Излишек 1');
  377 | 
  378 |   const factCardText = await visibleText(page.getByTestId('seller-inbound-fact-card'));
  379 |   expect(factCardText).toContain('Заявлено');
  380 |   expect(factCardText).toContain('Факт');
  381 |   expect(factCardText).toContain('Недостача 1');
  382 |   expect(factCardText).toContain('Излишек 1');
  383 |   expect(factCardText).toContain('Добавлено ФФ');
  384 |   expectNoRawTechnicalText(factCardText);
  385 |   qaResult.checks.sellerFactCardText = factCardText;
  386 |   saveResult();
  387 | 
  388 |   const geometry = await captureSellerFactGeometry(page);
  389 |   await screenshot(page, '04-seller-fact-card-1280.png', true);
  390 |   expect(geometry.documentScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
  391 |   expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
> 392 |   expect(geometry.containerScrollWidth).toBeLessThanOrEqual(geometry.containerClientWidth + 1);
      |                                         ^ Error: expect(received).toBeLessThanOrEqual(expected)
  393 |   expect(geometry.discrepancyHeaderRight).toBeLessThanOrEqual(geometry.containerRight + 1);
  394 |   expect(geometry.headerCells).toBe(geometry.bodyCells);
  395 |   expect(geometry.minNameWidth).toBeGreaterThanOrEqual(240);
  396 |   expect(geometry.maxRowHeight).toBeLessThanOrEqual(120);
  397 |   expect(geometry.headerBottom).toBeLessThanOrEqual(geometry.firstBodyTop + 1);
  398 |   expect(geometry.firstNameRight).toBeLessThanOrEqual(geometry.firstExpectedLeft + 1);
  399 |   expect(geometry.visibleButtonTexts).not.toContain('Добавить товары');
  400 |   expect(geometry.visibleButtonTexts).not.toContain('Передать на склад');
  401 |   expect(geometry.visibleButtonTexts).not.toContain('Сохранить');
  402 |   expect(geometry.visibleButtonTexts).not.toContain('Удалить');
  403 | });
  404 | 
```