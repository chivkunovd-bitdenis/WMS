import { describe, expect, it } from 'vitest'
import {
  fbsWarehousesLoadError,
  noResponseEnvelope,
  ozonWarehousesRequestFailed,
  readFbsErrorEnvelope,
  warehouseNameIssueHint,
} from './fbsSellerWarehouseRows'

// Тексты причин, почему у склада нет названия из кабинета (WMS-457). Сами
// строки/блоки окна с WMS-469 собирает fbsStockBlocks.ts — см. его тесты;
// разметка чипов — FbsStockDialog.render.test.tsx.

describe('WMS-457 C8 hints for a warehouse without a cabinet name', () => {
  it('names the marketplace and the reason', () => {
    expect(warehouseNameIssueHint('not_in_cabinet', 'ozon'))
      .toBe('В кабинете Ozon склада с таким номером нет: он удалён или принадлежит другому продавцу')
    expect(warehouseNameIssueHint('not_in_cabinet', 'wb'))
      .toBe('В кабинете Wildberries склада с таким номером нет: он удалён или принадлежит другому продавцу')
    expect(warehouseNameIssueHint('list_unavailable', 'wb'))
      .toBe('Список складов из кабинета не получен, поэтому названия нет — причина в сообщении выше')
  })
})

describe('WMS-457 C6 reason of a failed Wildberries warehouse list by envelope code', () => {
  it.each([
    { code: 'missing_marketplace_token', status: 403, message: 'Нет токена WB Marketplace.',
      expected: 'У продавца не сохранён ключ Wildberries с правами «Маркетплейс». Без него названия складов, заказы и остатки FBS не приходят.' },
    { code: 'wb_upstream_error_401', status: 502, message: 'Ошибка Wildberries.',
      expected: 'Wildberries не принял ключ продавца — он отозван или недействителен. Пока ключ не заменят, названия складов, заказы и остатки FBS этого продавца не приходят.' },
    { code: 'wb_upstream_error_403', status: 502, message: 'Ошибка Wildberries.',
      expected: 'У ключа Wildberries продавца нет прав «Маркетплейс». Нужен ключ с этой категорией.' },
    { code: 'wb_transport_error', status: 502, message: 'Ошибка Wildberries.',
      expected: 'Wildberries не ответил на запрос складов: Ошибка Wildberries. Ниже показаны сохранённые привязки без названий.' },
    { code: 'wb_upstream_error_500', status: 502, message: 'Ошибка Wildberries.',
      expected: 'Wildberries не ответил на запрос складов: Ошибка Wildberries. Ниже показаны сохранённые привязки без названий.' },
  ])('$code/$status', ({ code, status, message, expected }) => {
    const text = fbsWarehousesLoadError({ status, code, message })
    expect(text).toBe(expected)
    if (code === 'wb_upstream_error_401') expect(text.toLowerCase()).not.toContain('прав')
  })

  it('treats a request without any response as Wildberries not answering', () => {
    expect(fbsWarehousesLoadError(noResponseEnvelope(new TypeError('Failed to fetch')))).toBe(
      'Wildberries не ответил на запрос складов: Failed to fetch. Ниже показаны сохранённые привязки без названий.',
    )
    expect(noResponseEnvelope(new Error(''))).toEqual({ status: 0, code: null, message: 'Error' })
    expect(ozonWarehousesRequestFailed(new TypeError('Failed to fetch'))).toBe(
      'Справочник складов Ozon не получен: Failed to fetch. Ниже показаны сохранённые привязки без названий.',
    )
  })

  it('keeps the generic text for responses without an FBS envelope', () => {
    expect(fbsWarehousesLoadError({ status: 403, code: null, message: 'Нет доступа' }))
      .toBe('Не удалось загрузить склады Wildberries: Нет доступа')
    expect(fbsWarehousesLoadError({ status: 404, code: 'seller_not_found', message: 'Селлер не найден.' }))
      .toBe('Не удалось загрузить склады Wildberries: Селлер не найден.')
  })

  it('reads the code and the message from the server envelope', async () => {
    const envelope = await readFbsErrorEnvelope(new Response(JSON.stringify({
      detail: { code: 'wb_upstream_error_401', message: 'Ошибка Wildberries.', context: {}, retryable: true },
    }), { status: 502 }))
    expect(envelope).toEqual({ status: 502, code: 'wb_upstream_error_401', message: 'Ошибка Wildberries.' })
    expect(await readFbsErrorEnvelope(new Response(JSON.stringify({ detail: 'forbidden' }), { status: 403 })))
      .toEqual({ status: 403, code: null, message: 'forbidden' })
    expect(await readFbsErrorEnvelope(new Response('', { status: 502 })))
      .toEqual({ status: 502, code: null, message: 'Ошибка 502' })
  })
})
