import { afterEach, describe, expect, it, vi } from 'vitest'
import { putFbsRule } from './fbsRuleApi'
import type { FbsRule } from './stub'

const rule: FbsRule = {
  productId: 'product-1',
  publish: true,
  sameEverywhere: false,
  percent: 0,
  byWarehouse: {},
  unitsMode: true,
  // Явный операторский ноль по одному складу и незаданный второй склад.
  unitsByWarehouse: { '1': 0 },
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('сохранение правила остатка FBS', () => {
  it('везёт режим штук и явный ноль, а не молчаливый сброс лимитов', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await putFbsRule({ Authorization: 'Bearer token' }, ['product-1'], rule)

    expect(fetchMock.mock.calls[0]![0]).toBe('/api/products/product-1/fbs-rule')
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({
      publish: true,
      same_everywhere: false,
      percent: 0,
      by_warehouse: {},
      units_mode: true,
      units_by_warehouse: { '1': 0 },
    })
  })

  // Групповая ручка объявлена как {product_ids, rule} с extra="forbid": плоское
  // тело она отбивает целиком, и групповое сохранение не доезжает до сервера.
  it('кладёт правило внутрь rule, когда товаров несколько', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await putFbsRule({ Authorization: 'Bearer token' }, ['product-1', 'product-2'], rule)

    expect(fetchMock.mock.calls[0]![0]).toBe('/api/products/fbs-rule')
    const body = JSON.parse(fetchMock.mock.calls[0]![1].body)
    expect(body.product_ids).toEqual(['product-1', 'product-2'])
    expect(body.rule).toMatchObject({ units_mode: true, units_by_warehouse: { '1': 0 } })
    expect(body.publish).toBeUndefined()
  })

  it('поднимает наверх причину отказа сервера', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Склад продавца не найден.' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(putFbsRule({}, ['product-1'], rule)).rejects.toThrow('Склад продавца не найден.')
  })
})
