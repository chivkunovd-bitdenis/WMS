import { useCallback, useEffect, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { ErrorNotice } from '../../../ui-kit'
import { ProductsScreen } from './ProductsScreen'
import type { FbsRule, Product, Seller } from './stub'

// Экран управления остатком FBS, подключённый к серверу.
//
// Сам экран приняли по макету и он не знает про сеть; здесь только загрузка и
// сохранение. Разделение не ради красоты: превью макета должно открываться без
// сервера, иначе смотреть на экран можно будет только после готового бэка.

function headers(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

export type ApiCatalogRow = {
  id: string
  seller_id: string | null
  name: string
  sku_code: string
  wb_size?: string | null
  wb_primary_barcode: string | null
  wb_subject_name?: string | null
  // Площадки товара считает сервер (WMS-348). Окно квоты по ним решает, звать
  // ли строку Ozon; своего правила здесь не заводим.
  marketplaces?: string[]
}

export type ApiRule = {
  publish: boolean
  same_everywhere: boolean
  percent: number
  by_warehouse: Record<string, number>
  units_mode: boolean
  units_by_warehouse: Record<string, number>
  units_remaining_by_warehouse: Record<string, number>
  free_stock: number
  on_hand: number
  reserved: number
  published_now: number
}

type ApiSellerWarehouse = {
  wb_warehouse_id: number
  served: boolean
  wms_warehouse_id: string | null
  name: string | null
}

/**
 * Сервер отдаёт остаток тремя итоговыми числами, а не разбивкой по складам.
 *
 * Экран разбивку и не показывает: доли по складам берутся из правила, а числа
 * «на складе / занято / свободно» — суммарные. Поэтому кладём итог одной
 * записью под служебным ключом, вместо того чтобы выдумывать распределение,
 * которого сервер не знает.
 */
export const TOTAL_KEY = '__total__'

export function toProduct(row: ApiCatalogRow, rule: ApiRule | undefined, sellerId: string): Product {
  const onHand = rule?.on_hand ?? 0
  const reserved = rule?.reserved ?? 0
  return {
    id: row.id,
    name: row.name,
    sku: row.sku_code,
    size: row.wb_size ?? null,
    barcode: row.wb_primary_barcode ?? '',
    sellerId,
    category: row.wb_subject_name ?? '—',
    stock: { [TOTAL_KEY]: { onHand, reserved } },
    marketplaces: row.marketplaces,
  }
}

export function toRule(productId: string, rule: ApiRule | undefined): FbsRule {
  return {
    productId,
    publish: rule?.publish ?? false,
    sameEverywhere: rule?.same_everywhere ?? true,
    percent: rule?.percent ?? 0,
    byWarehouse: rule?.by_warehouse ?? {},
    unitsMode: rule?.units_mode ?? false,
    // В поля ввода подставляется ОСТАТОК квоты, а не то, что когда-то выделили:
    // оператор правит числа, глядя на сегодняшний расклад. Сохранение запишет
    // введённое как новое выделение и сдвинет точку отсчёта расхода.
    unitsByWarehouse: rule?.units_remaining_by_warehouse ?? {},
  }
}

type Props = {
  token: string
  sellers: Array<{ id: string; name: string }>
}

export function FfProductsFbsPage({ token, sellers: sellerList }: Props) {
  // Список продавцов приходит сверху новым массивом на каждую перерисовку.
  // Если держать загрузку зависимой от самого массива, она перезапускает себя
  // бесконечно: загрузила — обновила состояние — перерисовка — новый массив —
  // загрузила снова. На боевых данных это давало сотни повторных запросов и
  // экран, который никогда не догружался. Держимся за состав, а не за ссылку.
  const sellerKey = sellerList.map((one) => `${one.id}:${one.name}`).join('|')
  const sellerRef = useRef(sellerList)
  sellerRef.current = sellerList
  const [products, setProducts] = useState<Product[]>([])
  const [rules, setRules] = useState<FbsRule[]>([])
  const [sellers, setSellers] = useState<Seller[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/products/ff-catalog-page?limit=200&offset=0'), {
        headers: headers(token),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const page = (await res.json()) as { items: ApiCatalogRow[] }

      // Правила забираем одним запросом на всю страницу каталога. Раньше здесь
      // был запрос на каждый товар — на боевых данных это двести обращений на
      // одно открытие экрана, и таблица заметно висела.
      const loadedRules = new Map<string, ApiRule>()
      // Товары без продавца в пачку не кладём. Сервер отвергает такую пачку
      // целиком: у товара без продавца нет складов WB, а значит и правила. Один
      // заведённый руками товар без селлера иначе превращает весь экран в ошибку
      // загрузки — экран показывает только товары с продавцом, и спрашивать
      // правила надо ровно про них.
      const ruleTargets = page.items.filter((row) => row.seller_id !== null)
      if (ruleTargets.length > 0) {
        const bulk = await fetch(apiUrl('/products/fbs-rule/bulk'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...headers(token) },
          body: JSON.stringify({ product_ids: ruleTargets.map((row) => row.id) }),
        })
        if (!bulk.ok) throw new Error(await readApiErrorMessage(bulk))
        const answer = (await bulk.json()) as { items: Array<ApiRule & { product_id: string }> }
        for (const item of answer.items) loadedRules.set(item.product_id, item)
      }

      const known = new Map(sellerRef.current.map((one) => [one.id, one.name]))
      const withSeller = page.items.filter((row) => row.seller_id !== null)
      setProducts(
        withSeller.map((row) => toProduct(row, loadedRules.get(row.id), row.seller_id as string)),
      )
      setRules(withSeller.map((row) => toRule(row.id, loadedRules.get(row.id))))

      // Склады продавца нужны для ползунков: без них модалка не знает, между чем
      // делить процент. Тянем только по тем продавцам, чьи товары на экране.
      const sellerIds = [...new Set(withSeller.map((row) => row.seller_id as string))]
      const built: Seller[] = []
      for (const id of sellerIds) {
        const whRes = await fetch(apiUrl(`/operations/fbs-sellers/${id}/warehouses`), {
          headers: headers(token),
        })
        const rows = whRes.ok ? ((await whRes.json()) as ApiSellerWarehouse[]) : []
        built.push({
          id,
          name: known.get(id) ?? '—',
          warehouses: rows.map((one) => ({
            id: String(one.wb_warehouse_id),
            name: one.name ?? `Склад ${one.wb_warehouse_id}`,
            boundTo: one.wms_warehouse_id,
            fbsEnabled: one.served,
            // Эта ручка отдаёт кабинет Wildberries и ничего кроме него.
            marketplace: 'wb' as const,
          })),
          wbWarehouses: rows.map((one) => ({
            id: String(one.wb_warehouse_id),
            name: one.name ?? `Склад ${one.wb_warehouse_id}`,
          })),
        })
      }
      setSellers(built)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить товары')
    } finally {
      setLoading(false)
    }
  }, [token, sellerKey])

  useEffect(() => {
    void load()
  }, [load])

  async function saveRule(productIds: string[], rule: FbsRule): Promise<string | null> {
    setError(null)
    const body = {
      publish: rule.publish,
      same_everywhere: rule.sameEverywhere,
      percent: rule.percent,
      by_warehouse: rule.byWarehouse,
    }
    try {
      if (productIds.length === 1) {
        const res = await fetch(apiUrl(`/products/${productIds[0]}/fbs-rule`), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...headers(token) },
          body: JSON.stringify(body),
        })
        if (!res.ok) throw new Error(await readApiErrorMessage(res))
      } else {
        const res = await fetch(apiUrl('/products/fbs-rule'), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...headers(token) },
          body: JSON.stringify({ product_ids: productIds, ...body }),
        })
        if (!res.ok) throw new Error(await readApiErrorMessage(res))
      }
      await load()
      return null
    } catch (err) {
      // Возвращаем текст наверх: окно правила покажет его у себя и останется
      // открытым, чтобы не терять введённое.
      return err instanceof Error ? err.message : 'Не удалось сохранить правило'
    }
  }

  async function bindWarehouse(sellerId: string, warehouseId: string, wbWarehouseId: string) {
    setError(null)
    try {
      const current = sellers
        .find((one) => one.id === sellerId)
        ?.warehouses.find((one) => one.id === warehouseId)
      const res = await fetch(apiUrl(`/fbs-sellers/${sellerId}/warehouses/${warehouseId}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...headers(token) },
        body: JSON.stringify({
          served: current?.fbsEnabled ?? true,
          wms_warehouse_id: wbWarehouseId || null,
        }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сопоставить склад')
    }
  }

  return (
    <Box>
      {error ? <ErrorNotice testId="products-fbs-error">{error}</ErrorNotice> : null}
      <ProductsScreen
        onNote={() => undefined}
        products={products}
        sellers={sellers}
        rules={rules}
        loading={loading}
        onSaveRule={(ids, rule) => saveRule(ids, rule)}
        onBindWarehouse={(sellerId, warehouseId, wbWarehouseId) =>
          void bindWarehouse(sellerId, warehouseId, wbWarehouseId)
        }
      />
    </Box>
  )
}
