// Загрузка данных окна «Остаток для FBS» из каталога (WMS-454, WMS-457).
//
// Четыре запроса: правила товаров и три запроса складов продавца
// (loadFbsSellerWarehouses: кабинет Wildberries, сохранённые привязки,
// справочник Ozon). Обязательны только правила: без них окну нечего
// показывать, и оно не открывается. Оба справочника необязательны — их отказ
// не мешает открыть окно. Раньше отказ любого из четырёх запросов ронял
// открытие целиком, хотя правила и привязки уже приехали.

import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { loadFbsSellerWarehouses } from './fbsSellerWarehouseRows'
import { qualifyWarehouseRuleValues } from './fbsWarehouseRuleKeys'
import { toProduct, toRule, type ApiCatalogRow, type ApiRule } from './FfProductsFbsPage'
import type { FbsRule, Product, Seller } from './stub'

/** Строка каталога, из которой открывают окно. */
export type FbsStockDialogRow = ApiCatalogRow & { seller_name?: string | null }

export type FbsStockDialogData = {
  products: Array<Product & { savedPublishedNow?: number }>
  seller: Seller
  rule: FbsRule
  /** Почему кабинет Wildberries не отдал список складов — плашка сверху окна. */
  wbWarehousesError: string | null
  /** Почему не приехал справочник складов Ozon — строка в группе «Ozon». */
  ozonWarehousesError: string | null
}

export async function loadFbsStockDialog({
  headers,
  sellerId,
  sellerName,
  chosen,
  wmsWarehouses,
}: {
  headers: Record<string, string>
  sellerId: string
  sellerName: string
  /** Товары одного продавца, для которых открывается окно. */
  chosen: FbsStockDialogRow[]
  /** Физические склады WMS для выбора «Склад WMS». */
  wmsWarehouses: Array<{ id: string; name: string }>
}): Promise<FbsStockDialogData> {
  const [rulesRes, { seller, ruleBindings, wbWarehousesError, ozonWarehousesError }] =
    await Promise.all([
      fetch(apiUrl('/products/fbs-rule/bulk'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ product_ids: chosen.map((r) => r.id) }),
      }),
      loadFbsSellerWarehouses({ headers, sellerId, sellerName, wmsWarehouses }),
    ])
  if (!rulesRes.ok) throw new Error(await readApiErrorMessage(rulesRes))
  const rulesBody = (await rulesRes.json()) as { items: Array<ApiRule & { product_id: string }> }
  const ruleById = new Map(rulesBody.items.map((one) => [one.product_id, one]))

  const products = chosen.map((row) =>
    toProduct(
      {
        id: row.id,
        seller_id: row.seller_id,
        name: row.name,
        sku_code: row.sku_code,
        wb_size: row.wb_size,
        wb_primary_barcode: row.wb_primary_barcode,
        marketplaces: row.marketplaces,
      },
      ruleById.get(row.id),
      sellerId,
    ),
  )
  const first = chosen[0]!
  const rawRule = toRule(first.id, ruleById.get(first.id))
  const rule: FbsRule = {
    ...rawRule,
    byWarehouse: qualifyWarehouseRuleValues(rawRule.byWarehouse, ruleBindings),
    unitsByWarehouse: qualifyWarehouseRuleValues(rawRule.unitsByWarehouse, ruleBindings),
  }
  return { products, seller, rule, wbWarehousesError, ozonWarehousesError }
}
