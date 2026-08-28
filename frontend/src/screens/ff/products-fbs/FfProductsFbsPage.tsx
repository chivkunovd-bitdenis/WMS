import { useCallback, useEffect, useState } from 'react'
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

type ApiCatalogRow = {
  id: string
  seller_id: string | null
  name: string
  sku_code: string
  wb_size?: string | null
  wb_primary_barcode: string | null
  wb_subject_name?: string | null
}

type ApiRule = {
  publish: boolean
  same_everywhere: boolean
  percent: number
  by_warehouse: Record<string, number>
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
const TOTAL_KEY = '__total__'

function toProduct(row: ApiCatalogRow, rule: ApiRule | undefined, sellerId: string): Product {
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
  }
}

function toRule(productId: string, rule: ApiRule | undefined): FbsRule {
  return {
    productId,
    publish: rule?.publish ?? false,
    sameEverywhere: rule?.same_everywhere ?? true,
    percent: rule?.percent ?? 0,
    byWarehouse: rule?.by_warehouse ?? {},
  }
}

type Props = {
  token: string
  sellers: Array<{ id: string; name: string }>
}

export function FfProductsFbsPage({ token, sellers: sellerList }: Props) {
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

      // Правило запрашивается по каждому товару: одного метода на пачку сервер
      // не отдаёт. Идём пачками по восемь, чтобы не открыть двести соединений
      // разом — браузер их всё равно поставит в очередь, а сервер получит удар.
      const loadedRules = new Map<string, ApiRule>()
      const batch = 8
      for (let start = 0; start < page.items.length; start += batch) {
        const slice = page.items.slice(start, start + batch)
        const answers = await Promise.all(
          slice.map(async (row) => {
            const one = await fetch(apiUrl(`/products/${row.id}/fbs-rule`), {
              headers: headers(token),
            })
            if (!one.ok) return null
            return [row.id, (await one.json()) as ApiRule] as const
          }),
        )
        for (const answer of answers) {
          if (answer) loadedRules.set(answer[0], answer[1])
        }
      }

      const known = new Map(sellerList.map((one) => [one.id, one.name]))
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
  }, [token, sellerList])

  useEffect(() => {
    void load()
  }, [load])

  async function saveRule(productIds: string[], rule: FbsRule) {
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить правило')
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
        onSaveRule={(ids, rule) => void saveRule(ids, rule)}
        onBindWarehouse={(sellerId, warehouseId, wbWarehouseId) =>
          void bindWarehouse(sellerId, warehouseId, wbWarehouseId)
        }
      />
    </Box>
  )
}
