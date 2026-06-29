import { expect, type Page } from '@playwright/test'

/** Open MUI seller Autocomplete and pick seller by id (Honest Sign screens). */
export async function selectMarkingSeller(
  page: Page,
  testIdPrefix: string,
  sellerId: string,
): Promise<void> {
  const picker = page.getByTestId(`${testIdPrefix}-seller-picker`)
  await expect(picker).toBeVisible({ timeout: 30_000 })
  await picker.click()
  const option = page.getByTestId(`${testIdPrefix}-seller-${sellerId}`)
  await expect(option).toBeVisible()
  await option.click()
}

export async function selectHonestSignSeller(page: Page, sellerId: string): Promise<void> {
  await selectMarkingSeller(page, 'ff-honest-sign', sellerId)
}

type ProductSeed = {
  id: string
  sku_code: string
}

type MarkingImportSeedResult = {
  personalPoolId: string
  sharedPoolId: string
  productX: ProductSeed
  productY: ProductSeed
  productZ: ProductSeed
}

function buildCisCsv(gtin: string, count: number, serialChar: string): Buffer {
  const lines = ['cis']
  for (let i = 1; i <= count; i += 1) {
    const seq = String(i).padStart(4, '0')
    lines.push(`01${gtin}21${serialChar.repeat(16)}${seq}`)
  }
  return Buffer.from(lines.join('\n'))
}

async function importMarkingPool(
  page: Page,
  e2eApi: string,
  bearer: Record<string, string>,
  sellerId: string,
  spec: { title: string; gtin: string; productIds: string[]; count: number; serialChar: string },
): Promise<string> {
  const imp = await page.request.post(`${e2eApi}/operations/marking-codes/import`, {
    headers: bearer,
    multipart: {
      seller_id: sellerId,
      pools_json: JSON.stringify([
        { title: spec.title, gtin: spec.gtin, product_ids: spec.productIds },
      ]),
      files: {
        name: `${spec.gtin}.csv`,
        mimeType: 'text/csv',
        buffer: buildCisCsv(spec.gtin, spec.count, spec.serialChar),
      },
    },
  })
  expect(imp.ok()).toBeTruthy()
  const body = (await imp.json()) as {
    accepted_count: number
    pools: { pool_id: string }[]
  }
  expect(body.accepted_count).toBe(spec.count)
  return String(body.pools[0].pool_id)
}

async function createProduct(
  page: Page,
  e2eApi: string,
  auth: Record<string, string>,
  sellerId: string,
  sku: string,
  name: string,
): Promise<ProductSeed> {
  const res = await page.request.post(`${e2eApi}/products`, {
    headers: auth,
    data: JSON.stringify({
      name,
      sku_code: sku,
      length_mm: 10,
      width_mm: 10,
      height_mm: 10,
      seller_id: sellerId,
    }),
  })
  expect(res.ok()).toBeTruthy()
  const body = (await res.json()) as { id: string; sku_code: string }
  return { id: String(body.id), sku_code: body.sku_code }
}

/** Product X personal pool (100) + shared basket B (X,Y,Z, 1000) — mirrors SVC-01 seed. */
export async function seedHonestSignProductFirstInventory(
  page: Page,
  e2eApi: string,
  auth: Record<string, string>,
  bearer: Record<string, string>,
  sellerId: string,
  skuPrefix: string,
): Promise<MarkingImportSeedResult> {
  const productX = await createProduct(page, e2eApi, auth, sellerId, `${skuPrefix}-X`, 'Product X')
  const productY = await createProduct(page, e2eApi, auth, sellerId, `${skuPrefix}-Y`, 'Product Y')
  const productZ = await createProduct(page, e2eApi, auth, sellerId, `${skuPrefix}-Z`, 'Product Z')

  const personalPoolId = await importMarkingPool(page, e2eApi, bearer, sellerId, {
    title: 'Personal A',
    gtin: '04600000000001',
    productIds: [productX.id],
    count: 100,
    serialChar: 'A',
  })

  const sharedPoolId = await importMarkingPool(page, e2eApi, bearer, sellerId, {
    title: 'Shared B',
    gtin: '04600000000002',
    productIds: [productX.id, productY.id, productZ.id],
    count: 1000,
    serialChar: 'B',
  })

  return { personalPoolId, sharedPoolId, productX, productY, productZ }
}
