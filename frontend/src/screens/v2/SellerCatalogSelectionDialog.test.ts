import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  addKeysToFulfillment,
  buildAddToFulfillmentPayload,
  chunkKeys,
  displaySellerCatalogRow,
  fetchAddableSellerCatalogKeys,
  hasAnySellerCatalogCards,
  shouldCloseAfterAddToFulfillment,
  shouldOpenCatalogSelectionAfterKeySave,
  type SellerCatalogPageRow,
} from './SellerCatalogSelectionDialog'

// Диалог всегда рендерится открытым (<Dialog open>), а MUI Modal выносит
// содержимое в портал — react-dom/server его не печатает (portal — вещь
// браузера), поэтому renderToStaticMarkup здесь ничего осмысленного не
// проверяет. Разметку и текст окна смотрим глазами в браузере (см. отчёт),
// а всю логику отбора/отправки — приведёнными выше чистыми функциями.

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

// R2: одна и та же таблица показывает и товары на ФФ (поля сегодняшней строки
// /products/wb-catalog), и карточки, у которых товара ещё нет (nm_id/vendor_code/
// photo_url/barcodes/sizes из контракта /seller-catalog/page).
describe('displaySellerCatalogRow', () => {
  it('reads a product already on fulfillment from its today-catalog fields', () => {
    const row: SellerCatalogPageRow = {
      key: 'product:11111111-1111-1111-1111-111111111111',
      on_fulfillment: true,
      marketplace: 'wildberries',
      name: 'Палантин',
      wb_vendor_code: 'PAL-1',
      wb_nm_id: 555,
      wb_primary_image_url: 'https://example.test/photo.jpg',
      wb_barcodes: ['1000000000001', '1000000000002'],
      wb_primary_barcode: '1000000000001',
      wb_size: 'M',
    }
    expect(displaySellerCatalogRow(row)).toEqual({
      key: row.key,
      name: 'Палантин',
      vendorCode: 'PAL-1',
      photoUrl: 'https://example.test/photo.jpg',
      primaryBarcode: '1000000000001',
      extraBarcodeCount: 1,
      sizesText: 'M',
      onFulfillment: true,
    })
  })

  it('reads a card not on fulfillment from the snapshot-shaped fields', () => {
    const row: SellerCatalogPageRow = {
      key: 'wb:777',
      on_fulfillment: false,
      marketplace: 'wildberries',
      name: 'Шарф',
      vendor_code: 'SHF-2',
      photo_url: 'https://example.test/shf.jpg',
      barcodes: ['2000000000001', '2000000000002', '2000000000003'],
      sizes: ['S', 'M', 'L'],
    }
    expect(displaySellerCatalogRow(row)).toEqual({
      key: 'wb:777',
      name: 'Шарф',
      vendorCode: 'SHF-2',
      photoUrl: 'https://example.test/shf.jpg',
      primaryBarcode: '2000000000001',
      extraBarcodeCount: 2,
      sizesText: 'S, M, L',
      onFulfillment: false,
    })
  })

  it('reads a card not on fulfillment even when wb_barcodes/wb_size arrive as empty arrays, not null (real backend shape)', () => {
    // Настоящий бэкенд (Pydantic default_factory=list) всегда шлёт оба поля ШК:
    // у карточки не на ФФ wb_barcodes = [] (а не отсутствует/null). Простое
    // «??»-слияние здесь ошибочно предпочло бы пустой список настоящему.
    const row: SellerCatalogPageRow = {
      key: 'wb:424242',
      on_fulfillment: false,
      marketplace: 'wildberries',
      name: 'E2E-MOCK-BRAND',
      wb_barcodes: [],
      wb_primary_barcode: null,
      wb_size: null,
      vendor_code: 'E2E-MOCK',
      photo_url: 'data:image/png;base64,xxx',
      barcodes: ['E2E-MOCK-BARCODE'],
      sizes: ['L'],
    }
    expect(displaySellerCatalogRow(row)).toEqual({
      key: 'wb:424242',
      name: 'E2E-MOCK-BRAND',
      vendorCode: 'E2E-MOCK',
      photoUrl: 'data:image/png;base64,xxx',
      primaryBarcode: 'E2E-MOCK-BARCODE',
      extraBarcodeCount: 0,
      sizesText: 'L',
      onFulfillment: false,
    })
  })

  it('falls back to dashes when nothing is known', () => {
    const row: SellerCatalogPageRow = {
      key: 'ozon:42',
      on_fulfillment: false,
      marketplace: 'ozon',
      name: 'Без фото',
    }
    const view = displaySellerCatalogRow(row)
    expect(view.photoUrl).toBeNull()
    expect(view.primaryBarcode).toBeNull()
    expect(view.sizesText).toBeNull()
    expect(view.extraBarcodeCount).toBe(0)
  })
})

describe('chunkKeys', () => {
  it('splits into groups of the given size, keeping order', () => {
    expect(chunkKeys([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]])
  })

  it('returns a single chunk when everything fits', () => {
    expect(chunkKeys(['a', 'b'], 500)).toEqual([['a', 'b']])
  })

  it('returns no chunks for an empty list', () => {
    expect(chunkKeys([], 500)).toEqual([])
  })
})

describe('buildAddToFulfillmentPayload', () => {
  it('extracts numeric nm_id for wildberries keys and ignores foreign-marketplace keys', () => {
    expect(buildAddToFulfillmentPayload(['wb:123', 'wb:456', 'ozon:9', 'product:x'], 'wildberries')).toEqual({
      wb_nm_ids: [123, 456],
      ozon_product_ids: [],
    })
  })

  it('extracts ozon product ids for ozon keys', () => {
    expect(buildAddToFulfillmentPayload(['ozon:abc-1', 'ozon:abc-2', 'wb:1'], 'ozon')).toEqual({
      wb_nm_ids: [],
      ozon_product_ids: ['abc-1', 'abc-2'],
    })
  })
})

// R1, решение А9: окно — только на первый ключ этой площадки, не на замену;
// не открываем, если проверка не прошла или нет права «Товары» (R14).
describe('shouldOpenCatalogSelectionAfterKeySave', () => {
  it('opens on the first key of a platform once validation passed and the user manages products', () => {
    expect(
      shouldOpenCatalogSelectionAfterKeySave({ hadKeyBefore: false, validationOk: true, canManageProducts: true }),
    ).toBe(true)
  })

  it('does not open when a key of this platform already existed (replacement)', () => {
    expect(
      shouldOpenCatalogSelectionAfterKeySave({ hadKeyBefore: true, validationOk: true, canManageProducts: true }),
    ).toBe(false)
  })

  it('does not open when validation failed (e.g. missing marketplace scope)', () => {
    expect(
      shouldOpenCatalogSelectionAfterKeySave({ hadKeyBefore: false, validationOk: false, canManageProducts: true }),
    ).toBe(false)
  })

  it('treats an unknown validation outcome as passing (older responses without the flag)', () => {
    expect(
      shouldOpenCatalogSelectionAfterKeySave({ hadKeyBefore: false, validationOk: undefined, canManageProducts: true }),
    ).toBe(true)
  })

  it('does not open for a user without the Товары permission', () => {
    expect(
      shouldOpenCatalogSelectionAfterKeySave({ hadKeyBefore: false, validationOk: true, canManageProducts: false }),
    ).toBe(false)
  })
})

describe('hasAnySellerCatalogCards', () => {
  it('is true when the page reports a non-zero scope_total', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { items: [], total: 0, scope_total: 3, categories: [] }))
    expect(await hasAnySellerCatalogCards(fetchImpl, 'http://x/seller-catalog/page', {})).toBe(true)
  })

  it('is false when there are no cards at all', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { items: [], total: 0, scope_total: 0, categories: [] }))
    expect(await hasAnySellerCatalogCards(fetchImpl, 'http://x/seller-catalog/page', {})).toBe(false)
  })

  it('is false (not thrown) on a server error, so a failed key save never crashes the settings screen', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(500, { detail: 'boom' }))
    expect(await hasAnySellerCatalogCards(fetchImpl, 'http://x/seller-catalog/page', {})).toBe(false)
  })

  it('is false on a network error', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error('network down')
    })
    expect(await hasAnySellerCatalogCards(fetchImpl, 'http://x/seller-catalog/page', {})).toBe(false)
  })
})

describe('fetchAddableSellerCatalogKeys', () => {
  it('keeps only keys of the requested marketplace from a bare array response', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, ['wb:1', 'wb:2', 'product:abc', 'ozon:9']))
    expect(await fetchAddableSellerCatalogKeys('wildberries', fetchImpl, 'http://x/keys', {})).toEqual([
      'wb:1',
      'wb:2',
    ])
  })

  it('reads a {keys: [...]} wrapper the same way', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { keys: ['ozon:1', 'wb:2'] }))
    expect(await fetchAddableSellerCatalogKeys('ozon', fetchImpl, 'http://x/keys', {})).toEqual(['ozon:1'])
  })

  it('throws the server message on failure', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(403, { detail: 'forbidden' }))
    await expect(fetchAddableSellerCatalogKeys('wildberries', fetchImpl, 'http://x/keys', {})).rejects.toThrow(
      'forbidden',
    )
  })
})

// R9, R15: порции по 500 отправляются по очереди; если порция не прошла,
// уже добавленное остаётся, а сама неудачная порция и всё, что за ней, не
// отправляются — их ключи остаются в выделении для повтора (компонент их
// просто не удаляет из selectedKeys).
describe('addKeysToFulfillment', () => {
  it('adds everything in one request when it fits one chunk', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, { added: [{ marketplace: 'wildberries', id: 123, vendor_code: 'A-1' }], skipped: [] }),
    )
    const outcome = await addKeysToFulfillment(['wb:123'], 'wildberries', fetchImpl, 'http://x/add', {})
    expect(outcome).toEqual({ addedKeys: ['wb:123'], skipped: [], failureMessage: null })
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('records skipped cards with their reason without failing the whole batch', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, {
        added: [{ id: 1, vendor_code: 'A-1' }],
        skipped: [{ id: 2, vendor_code: 'A-2', reason: 'vendor_code_conflict' }],
      }),
    )
    const outcome = await addKeysToFulfillment(['wb:1', 'wb:2'], 'wildberries', fetchImpl, 'http://x/add', {})
    expect(outcome.addedKeys).toEqual(['wb:1'])
    expect(outcome.skipped).toEqual([{ vendorCode: 'A-2', reason: 'vendor_code_conflict' }])
    expect(outcome.failureMessage).toBeNull()
  })

  it('stops at the first failing chunk and leaves the rest unattempted, keeping the earlier chunk added', async () => {
    let call = 0
    const fetchImpl = vi.fn(async () => {
      call += 1
      if (call === 1) {
        return jsonResponse(200, { added: [{ id: 1, vendor_code: 'A-1' }], skipped: [] })
      }
      return jsonResponse(500, { detail: 'db_unavailable' })
    })
    const outcome = await addKeysToFulfillment(
      ['wb:1', 'wb:2', 'wb:3'],
      'wildberries',
      fetchImpl,
      'http://x/add',
      {},
      1, // chunkSize=1, чтобы получить три отдельные порции
    )
    expect(outcome.addedKeys).toEqual(['wb:1'])
    expect(outcome.failureMessage).toBe('db_unavailable')
    // Третья порция не отправлялась вовсе — обрыв на второй её не запускает.
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })

  it('reports a network failure the same way as a server error', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error('offline')
    })
    const outcome = await addKeysToFulfillment(['wb:1'], 'wildberries', fetchImpl, 'http://x/add', {})
    expect(outcome).toEqual({ addedKeys: [], skipped: [], failureMessage: 'offline' })
  })
})

// WMS-548 ревью Astra №1, F7: окно закрывается только при полном успехе —
// ни одна порция не оборвалась и ни одна карточка не пропущена. При ошибке
// или пропуске (R9, А12) окно и выделение недобавленных остаются.
describe('shouldCloseAfterAddToFulfillment', () => {
  it('closes when everything selected was added, nothing skipped', () => {
    expect(
      shouldCloseAfterAddToFulfillment({ addedKeys: ['wb:1'], skipped: [], failureMessage: null }),
    ).toBe(true)
  })

  it('stays open when a chunk failed, even if something was added before the failure', () => {
    expect(
      shouldCloseAfterAddToFulfillment({
        addedKeys: ['wb:1'],
        skipped: [],
        failureMessage: 'db_unavailable',
      }),
    ).toBe(false)
  })

  it('stays open when a card was skipped (conflict), even without a transport failure', () => {
    expect(
      shouldCloseAfterAddToFulfillment({
        addedKeys: ['wb:1'],
        skipped: [{ vendorCode: 'A-2', reason: 'vendor_code_conflict' }],
        failureMessage: null,
      }),
    ).toBe(false)
  })
})
