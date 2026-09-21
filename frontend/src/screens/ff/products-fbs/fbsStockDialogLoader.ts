// Загрузка данных окна «Остаток для FBS» из каталога (WMS-454, WMS-457).
//
// Четыре запроса: правила товаров, склады кабинета Wildberries, сохранённые
// привязки продавца и справочник складов Ozon. Обязательны правила и привязки:
// без правил окну нечего показывать, а без действующих привязок не разобрать,
// какой площадке принадлежит номер склада в правиле. Оба справочника кабинетов
// необязательны — их отказ (ошибка сервера, не дождавшийся ответа запрос или
// оборванное на чтении тело ответа) не мешает открыть окно: сохранённые
// активные привязки показываются номером с чипом «название недоступно», а
// причина — плашкой сверху (WB) или строкой в группе (Ozon). Раньше отказ
// любого из четырёх запросов ронял открытие целиком, хотя правила и привязки
// уже приехали.

import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import {
  buildSellerWarehouseRows,
  fbsWarehousesLoadError,
  noResponseEnvelope,
  ozonWarehousesRequestFailed,
  readFbsErrorEnvelope,
  type CabinetList,
  type CabinetWarehouseRow,
  type SavedWarehouseBinding,
} from './fbsSellerWarehouseRows'
import { qualifyWarehouseRuleValues, type WarehouseRuleBinding } from './fbsWarehouseRuleKeys'
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

/**
 * Необязательный справочник: строки, либо ответ сервера с ошибкой (конверт с
 * причиной), либо отказ без ответа — запрос отклонён или тело ответа
 * оборвалось на чтении. Ожидание ответа и чтение тела под одной защитой: 200
 * с оборванным потоком тела — такой же неполученный список, как и обрыв до
 * ответа, и не должен ронять открытие окна (WMS-457 R3).
 */
type Directory<Row> = { rows: Row[] } | { response: Response } | { failure: unknown }

async function loadDirectory<Row>(request: () => Promise<Response>): Promise<Directory<Row>> {
  try {
    const response = await request()
    if (!response.ok) return { response }
    return { rows: (await response.json()) as Row[] }
  } catch (failure) {
    return { failure }
  }
}

// Кабинет Wildberries: эта ручка отдаёт только его склады, площадка у строк
// всегда «wb».
type WbWarehouseRow = {
  wb_warehouse_id: number | string
  name: string | null
  wms_warehouse_id: string | null
  served: boolean
}

type OzonWarehouseRow = {
  warehouse_id: number
  name: string
  served: boolean
  wms_warehouse_id: string | null
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
  const [rulesRes, wb, bindingsRes, ozon] = await Promise.all([
    fetch(apiUrl('/products/fbs-rule/bulk'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({ product_ids: chosen.map((r) => r.id) }),
    }),
    loadDirectory<WbWarehouseRow>(() =>
      fetch(apiUrl(`/operations/fbs-sellers/${sellerId}/warehouses`), { headers }),
    ),
    fetch(apiUrl(`/operations/fbs-sellers/${sellerId}/warehouse-bindings`), { headers }),
    loadDirectory<OzonWarehouseRow>(() =>
      fetch(apiUrl(`/operations/fbs-sellers/${sellerId}/ozon-warehouses`), { headers }),
    ),
  ])
  if (!rulesRes.ok) throw new Error(await readApiErrorMessage(rulesRes))
  const rulesBody = (await rulesRes.json()) as { items: Array<ApiRule & { product_id: string }> }
  const ruleById = new Map(rulesBody.items.map((one) => [one.product_id, one]))

  let wbList: CabinetList = { received: false }
  let wbWarehousesError: string | null = null
  if ('rows' in wb) {
    wbList = {
      received: true,
      rows: wb.rows.map((one): CabinetWarehouseRow => ({ ...one, marketplace: 'wb' })),
    }
  } else {
    // Причина — по коду из конверта ошибки, а не по HTTP-статусу (WMS-457):
    // отозванный ключ и обрыв связи требуют разных действий от оператора.
    wbWarehousesError = fbsWarehousesLoadError(
      'response' in wb ? await readFbsErrorEnvelope(wb.response) : noResponseEnvelope(wb.failure),
    )
  }

  // Справочник складов Ozon (WMS-362). До него озоновские строки брались
  // только из сохранённых привязок: склад, которого ещё не заводили, вообще
  // не показывался. Отсюда приезжают настоящие названия кабинета и все склады.
  let ozonList: CabinetList = { received: false }
  let ozonWarehousesError: string | null = null
  if ('rows' in ozon) {
    ozonList = {
      received: true,
      rows: ozon.rows.map(
        (one): CabinetWarehouseRow => ({
          wb_warehouse_id: one.warehouse_id,
          name: one.name,
          wms_warehouse_id: one.wms_warehouse_id,
          served: one.served,
          marketplace: 'ozon',
        }),
      ),
    }
  } else if ('response' in ozon) {
    // Отказ штатный: боевые запросы к Ozon выключаются настройкой. Сервер
    // отвечает человеческим текстом, его и показываем — молчаливая пустота
    // читалась бы как «складов у продавца нет».
    ozonWarehousesError = await readApiErrorMessage(ozon.response)
  } else {
    ozonWarehousesError = ozonWarehousesRequestFailed(ozon.failure)
  }

  // Площадку номера в правиле определяют только действующие привязки — по ним
  // его собирает сервер. Справочник кабинета для этого не годится: у продавца с
  // отключённой привязкой WB 123 и работающей Ozon 123 строка Wildberries
  // показала бы озоновский лимит, а сохранение увело бы туда чужой ноль.
  // Поэтому отказ этой ручки — обычная ошибка открытия окна, а не пустой список.
  if (!bindingsRes.ok) throw new Error(await readApiErrorMessage(bindingsRes))
  const savedBindings = (await bindingsRes.json()) as SavedWarehouseBinding[]
  const ruleBindings: WarehouseRuleBinding[] = savedBindings.filter((one) => one.is_active)

  // Если кабинет не отдал список, сохранённые активные привязки всё равно
  // показываются — номером, с чипом причины (WMS-457): оператор должен видеть
  // внешний номер, выбранный WMS-склад и мочь снять приём заказов с чужого или
  // удалённого склада.
  const seller: Seller = {
    id: sellerId,
    name: sellerName,
    warehouses: buildSellerWarehouseRows({ wb: wbList, ozon: ozonList }, savedBindings),
    // Имя поля осталось от старого макета, но Select справа выбирает именно
    // наш физический WMS-склад для направления.
    wbWarehouses: wmsWarehouses,
  }
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
