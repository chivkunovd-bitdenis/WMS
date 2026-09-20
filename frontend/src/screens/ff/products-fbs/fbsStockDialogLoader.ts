// Загрузка данных окна «Остаток для FBS» (WMS-454, WMS-457, WMS-469).
//
// Четыре запроса параллельно: правила товаров по привязкам, сохранённые
// привязки продавца, склады кабинета Wildberries и справочник складов Ozon.
// Обязательны правила и привязки: без них блокам не из чего строиться, и окно
// не открывается. Оба справочника необязательны — их отказ (ошибка сервера, не
// дождавшийся ответа запрос или оборванное на чтении тело ответа) не мешает
// открыть окно: сохранённые активные привязки показываются номером с чипом
// «название недоступно», а причина — плашкой в окне. Новую связку из
// неполученного справочника добавить нельзя: список для «Добавить склад»
// строится только из полученных кабинетов.

import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import {
  fbsWarehousesLoadError,
  noResponseEnvelope,
  ozonWarehousesRequestFailed,
  readFbsErrorEnvelope,
  type CabinetList,
  type CabinetWarehouseRow,
  type SavedWarehouseBinding,
} from './fbsSellerWarehouseRows'
import {
  buildStockBindings,
  toProductBindingState,
  type ApiBindingRule,
  type StockBinding,
  type StockDialogProduct,
} from './fbsStockBlocks'
import type { MarketplaceCode } from './stub'

/** Строка каталога, из которой открывают окно. */
export type FbsStockDialogRow = {
  id: string
  name: string
  sku_code: string
  wb_size?: string | null
}

export type FbsStockDialogData = {
  products: StockDialogProduct[]
  /** Активные привязки продавца с названиями из кабинетов, порядок сервера. */
  bindings: StockBinding[]
  /** Что ответили кабинеты — источник списка «Добавить склад». */
  cabinets: Record<MarketplaceCode, CabinetList>
  /** Почему кабинет Wildberries не отдал список складов — плашка в окне. */
  wbWarehousesError: string | null
  /** Почему не приехал справочник складов Ozon. */
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

export type ApiBulkRuleItem = {
  product_id: string
  by_binding?: Record<string, ApiBindingRule>
}

/** Товар окна из строки каталога и его правила по привязкам. */
export function toStockDialogProduct(
  row: FbsStockDialogRow,
  rule: ApiBulkRuleItem | undefined,
): StockDialogProduct {
  return {
    id: row.id,
    name: row.name,
    sku: row.sku_code,
    size: row.wb_size ?? null,
    byBinding: Object.fromEntries(
      Object.entries(rule?.by_binding ?? {}).map(([bindingId, one]) => [
        bindingId,
        toProductBindingState(one),
      ]),
    ),
  }
}

export async function loadFbsStockDialog({
  headers,
  sellerId,
  chosen,
}: {
  headers: Record<string, string>
  sellerId: string
  /** Товары одного продавца, для которых открывается окно. */
  chosen: FbsStockDialogRow[]
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
  const rulesBody = (await rulesRes.json()) as { items: ApiBulkRuleItem[] }
  const ruleById = new Map(rulesBody.items.map((one) => [one.product_id, one]))
  if (!bindingsRes.ok) throw new Error(await readApiErrorMessage(bindingsRes))
  const savedBindings = (await bindingsRes.json()) as SavedWarehouseBinding[]

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

  // Справочник складов Ozon (WMS-362): настоящие названия кабинета и все
  // склады, в том числе ещё не связанные.
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

  const cabinets = { wb: wbList, ozon: ozonList }
  return {
    products: chosen.map((row) => toStockDialogProduct(row, ruleById.get(row.id))),
    bindings: buildStockBindings(cabinets, savedBindings),
    cabinets,
    wbWarehousesError,
    ozonWarehousesError,
  }
}
