// Строки складов продавца для окна «Остаток для FBS» (WMS-457).
//
// Названия склады получают только из кабинета площадки: Wildberries отдаёт их
// по ключу продавца, Ozon — из своего справочника. Код названий не выдумывает.
// Когда имени физически нет — кабинет не ответил или склада в кабинете нет, —
// строка подписывается номером как номером («№ 2035707»), а рядом чипом
// объясняется, почему номера недостаточно. «Склад WB 2035707» выглядел как
// название, и владелец так его и прочитал.

import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { warehouseRuleKey } from './fbsWarehouseRuleKeys'
import {
  MARKETPLACE_NAMES,
  type MarketplaceCode,
  type SellerWarehouse,
  type WarehouseNameIssue,
} from './stub'

/** Строка кабинета площадки: то, что ответил Wildberries или Ozon. */
export type CabinetWarehouseRow = {
  wb_warehouse_id: number | string
  name: string | null
  wms_warehouse_id: string | null
  served: boolean
  marketplace: MarketplaceCode
}

/** Список кабинета одной площадки: получен со строками либо не получен вовсе. */
export type CabinetList =
  | { received: true; rows: CabinetWarehouseRow[] }
  | { received: false }

/** Сохранённая привязка продавца — строка GET …/warehouse-bindings. */
export type SavedWarehouseBinding = {
  wb_warehouse_id: number | string
  wms_warehouse_id: string | null
  is_active: boolean
  served: boolean
  marketplace?: MarketplaceCode
  external_warehouse_id?: string | null
}

/** Номер как номер, а не как название. */
export function warehouseNumberLabel(number: number | string): string {
  return `№ ${number}`
}

/**
 * Строки окна из ответов кабинетов и сохранённых привязок.
 *
 * Порядок прежний: строки кабинета в порядке кабинета (Wildberries, затем
 * Ozon), после них — активные привязки, которых в ответах кабинетов не
 * оказалось. Такая привязка подписывается номером и получает признак: список
 * кабинета получен, но склада в нём нет (удалён или чужой), либо список не
 * получен и имени взять неоткуда.
 *
 * Выключенная привязка без строки кабинета не показывается: строка с «заказы не
 * принимаем» приглашала бы включить её одним нажатием, а сервер при любом PUT
 * молча возвращает привязке is_active=true. Если же её склад есть в кабинете,
 * она показывается как обычная строка кабинета с выключенной галкой.
 */
export function buildSellerWarehouseRows(
  cabinets: Record<MarketplaceCode, CabinetList>,
  bindings: SavedWarehouseBinding[],
): SellerWarehouse[] {
  const rows: SellerWarehouse[] = []
  const known = new Set<string>()
  for (const marketplace of ['wb', 'ozon'] as const) {
    const list = cabinets[marketplace]
    if (!list.received) continue
    for (const one of list.rows) {
      const id = warehouseRuleKey({ wb_warehouse_id: one.wb_warehouse_id, marketplace })
      known.add(id)
      rows.push({
        id,
        name: one.name ?? warehouseNumberLabel(one.wb_warehouse_id),
        boundTo: one.wms_warehouse_id,
        fbsEnabled: one.served,
        marketplace,
      })
    }
  }
  for (const binding of bindings) {
    const marketplace = binding.marketplace ?? 'wb'
    // Ключ с площадкой: номера складов Wildberries и Ozon из разных пространств
    // и могут совпасть.
    const id = warehouseRuleKey({ wb_warehouse_id: binding.wb_warehouse_id, marketplace })
    if (known.has(id) || !binding.is_active) continue
    rows.push({
      id,
      name: warehouseNumberLabel(binding.external_warehouse_id ?? binding.wb_warehouse_id),
      boundTo: binding.wms_warehouse_id,
      fbsEnabled: binding.served,
      marketplace,
      nameIssue: cabinets[marketplace].received ? 'not_in_cabinet' : 'list_unavailable',
    })
  }
  return rows
}

export const WAREHOUSE_NAME_ISSUE_LABELS: Record<WarehouseNameIssue, string> = {
  not_in_cabinet: 'нет в кабинете',
  list_unavailable: 'название недоступно',
}

/** Подсказка чипа: почему у строки номер вместо названия. */
export function warehouseNameIssueHint(
  issue: WarehouseNameIssue,
  marketplace: MarketplaceCode,
): string {
  return issue === 'not_in_cabinet'
    ? `В кабинете ${MARKETPLACE_NAMES[marketplace]} склада с таким номером нет: он удалён или принадлежит другому продавцу`
    : 'Список складов из кабинета не получен, поэтому названия нет — причина в сообщении выше'
}

/**
 * Конверт ошибки FBS: статус ответа, код из detail.code (если это конверт) и
 * текст. Статус 0 — ответа от API не было вовсе (обрыв, тайм-аут, отклонённый
 * fetch): ни кода, ни серверного текста, только сообщение браузера.
 */
export type FbsErrorEnvelope = { status: number; code: string | null; message: string }

/** Конверт для запроса, который не дождался ответа. */
export function noResponseEnvelope(error: unknown): FbsErrorEnvelope {
  const message = error instanceof Error && error.message.trim() ? error.message : String(error)
  return { status: 0, code: null, message }
}

/** Справочник Ozon не получен без ответа сервера — текст строки в группе «Ozon». */
export function ozonWarehousesRequestFailed(error: unknown): string {
  return `Справочник складов Ozon не получен: ${noResponseEnvelope(error).message}. Ниже показаны сохранённые привязки без названий.`
}

/**
 * Код и текст из ответа с ошибкой. Сервер FBS отвечает конвертом
 * {"detail": {"code", "message", …}}; у ответов без конверта кода нет, текст
 * берётся так же, как везде.
 */
export async function readFbsErrorEnvelope(res: Response): Promise<FbsErrorEnvelope> {
  let code: string | null = null
  try {
    const payload = (await res.clone().json()) as { detail?: { code?: unknown } }
    const detail = payload.detail
    if (detail && typeof detail === 'object' && typeof detail.code === 'string') {
      code = detail.code
    }
  } catch {
    // Тело не JSON или не конверт — кода нет, текст ниже.
  }
  return { status: res.status, code, message: await readApiErrorMessage(res) }
}

/**
 * Почему кабинет Wildberries не отдал список складов — по коду из конверта, а не
 * по HTTP-статусу: сервер любую ошибку Wildberries отдаёт как 502 с кодом вида
 * wb_upstream_error_<статус WB>, и отозванный ключ (401 у WB) раньше показывался
 * тем же текстом «проверьте права», что и обрыв связи. Тот же ключ нужен
 * автоопросу заказов и публикации остатков, поэтому текст говорит и о них.
 */
export function fbsWarehousesLoadError({ status, code, message }: FbsErrorEnvelope): string {
  if (code === 'missing_marketplace_token') {
    return 'У продавца не сохранён ключ Wildberries с правами «Маркетплейс». Без него названия складов, заказы и остатки FBS не приходят.'
  }
  if (code === 'wb_upstream_error_401') {
    return 'Wildberries не принял ключ продавца — он отозван или недействителен. Пока ключ не заменят, названия складов, заказы и остатки FBS этого продавца не приходят.'
  }
  if (code === 'wb_upstream_error_403') {
    return 'У ключа Wildberries продавца нет прав «Маркетплейс». Нужен ключ с этой категорией.'
  }
  // Прочие ошибки Wildberries и запрос, не дождавшийся ответа (обрыв, тайм-аут).
  if (code?.startsWith('wb_') || status === 0) {
    return `Wildberries не ответил на запрос складов: ${message}. Ниже показаны сохранённые привязки без названий.`
  }
  // Не конверт FBS: отказ доступа, потерянный продавец и прочее — как раньше.
  return `Не удалось загрузить склады Wildberries: ${message || `Ошибка ${status}`}`
}
