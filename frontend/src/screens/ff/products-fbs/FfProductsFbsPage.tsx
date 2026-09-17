import { useCallback, useEffect, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { ErrorNotice } from '../../../ui-kit'
import { ProductsScreen } from './ProductsScreen'
import type { FbsRule, MarketplaceCode, Product, Seller } from './stub'
import { qualifyWarehouseRuleValues, warehouseNumberFromRuleKey, warehouseRuleKey,
  type WarehouseRuleBinding } from './fbsWarehouseRuleKeys'

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
  publish_ozon?: boolean | null
  same_everywhere: boolean
  percent: number
  by_warehouse: Record<string, number>
  units_mode: boolean
  units_by_warehouse: Record<string, number>
  // Режим «весь свободный остаток в оба кабинета» (WMS-455). Сервер отдаёт
  // уже эффективное значение: без связки Ozon — false. Нет в ответе — false.
  shared_pool?: boolean
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

export function toProduct(row: ApiCatalogRow, rule: ApiRule | undefined, sellerId: string): Product & { savedPublishedNow?: number } {
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
    savedPublishedNow: rule?.published_now,
  }
}

export function toRule(
  productId: string, rule: ApiRule | undefined, bindings?: WarehouseRuleBinding[],
): FbsRule {
  const qualify = (values: Record<string, number>) => bindings
    ? qualifyWarehouseRuleValues(values, bindings) : values
  return {
    productId,
    publish: rule?.publish ?? false,
    publishOzon: rule?.publish_ozon ?? rule?.publish ?? false,
    sameEverywhere: rule?.same_everywhere ?? true,
    percent: rule?.percent ?? 0,
    byWarehouse: qualify(rule?.by_warehouse ?? {}),
    unitsMode: rule?.units_mode ?? false,
    // Stored operator caps survive orders and percentage mode unchanged.
    unitsByWarehouse: qualify(rule?.units_by_warehouse ?? {}),
    sharedPool: rule?.shared_pool ?? false,
  }
}

/**
 * Тело правила для PUT /products/{id}/fbs-rule и поле rule в PUT /products/fbs-rule.
 *
 * Флаги передачи уходят только если их трогали в этом открытии окна; иначе поле
 * не отправляется, и сервер оставляет прежнее значение. У товара без карточки
 * Ozon окно само помечает флаг Ozon тронутым и выключенным, поэтому publish_ozon
 * у него равен false при каждом сохранении (WMS-454).
 *
 * WMS-060/WMS-338: поштучный режим и числа по складам обязательны, иначе API
 * подставит `units_mode=false` и `units_by_warehouse={}`, и любое сохранение
 * молча сбросит режим штук и операторский потолок. По той же причине всегда
 * уходит и `shared_pool` (WMS-455): не прислали — сервер считает false и
 * выключил бы режим.
 */
export function fbsRuleBody(rule: FbsRule): {
  publish: boolean | undefined
  publish_ozon: boolean | undefined
  same_everywhere: boolean
  percent: number
  by_warehouse: Record<string, number>
  units_mode: boolean
  units_by_warehouse: Record<string, number>
  shared_pool: boolean
} {
  const touched = (marketplace: MarketplaceCode) =>
    !rule.changedPublication || rule.changedPublication.includes(marketplace)
  return {
    publish: touched('wb') ? rule.publish : undefined,
    publish_ozon: touched('ozon') ? (rule.publishOzon ?? rule.publish) : undefined,
    same_everywhere: rule.sameEverywhere,
    percent: rule.percent,
    by_warehouse: rule.byWarehouse,
    units_mode: rule.unitsMode,
    // Что оператор видел в поле, то и записывается как новое выделение: сервер
    // сдвинет точку отсчёта расхода на «сейчас», и съеденное до этой секунды
    // уже учтено в том, что было показано.
    units_by_warehouse: rule.unitsByWarehouse,
    // При включённом режиме сервер доли и штуки выше не читает — они уходят
    // как есть, чтобы у товара остались его прежние значения на выключение.
    shared_pool: rule.sharedPool,
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
      const loadedBindings = new Map<string, WarehouseRuleBinding[]>()

      // Склады продавца нужны для ползунков: без них модалка не знает, между чем
      // делить процент. Тянем только по тем продавцам, чьи товары на экране.
      const sellerIds = [...new Set(withSeller.map((row) => row.seller_id as string))]
      const built: Seller[] = []
      for (const id of sellerIds) {
        const whRes = await fetch(apiUrl(`/operations/fbs-sellers/${id}/warehouses`), {
          headers: headers(token),
        })
        const rows = whRes.ok ? ((await whRes.json()) as ApiSellerWarehouse[]) : []
        const bindingsRes = await fetch(apiUrl(`/operations/fbs-sellers/${id}/warehouse-bindings`), {
          headers: headers(token),
        })
        if (!bindingsRes.ok) throw new Error(await readApiErrorMessage(bindingsRes))
        const bindings = (await bindingsRes.json()) as Array<WarehouseRuleBinding & { is_active: boolean }>
        loadedBindings.set(id, bindings.filter((one) => one.is_active))
        built.push({
          id,
          name: known.get(id) ?? '—',
          warehouses: rows.map((one) => ({
            id: warehouseRuleKey(one),
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
      setRules(withSeller.map((row) => toRule(
        row.id, loadedRules.get(row.id), loadedBindings.get(row.seller_id as string),
      )))
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
    const body = fbsRuleBody(rule)
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
          body: JSON.stringify({ product_ids: productIds, rule: body }),
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
      const res = await fetch(apiUrl(`/fbs-sellers/${sellerId}/warehouses/${warehouseNumberFromRuleKey(warehouseId)}`), {
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
