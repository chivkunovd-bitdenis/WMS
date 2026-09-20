// Сеть окна «Остаток для FBS» (WMS-469) без React: загрузка, немедленные
// действия со связкой и сохранение правила. Контейнер только раскладывает
// исходы по состоянию; здесь — то, что можно проверить с подменным fetch.
//
// Три защиты, которых требует R17 и разбор сбоев B02/B09:
// - ответ устаревшей загрузки отбрасывается: окно, открытое для новых товаров,
//   не покажет старые и не сохранит правило не тем адресатам;
// - после отказа или потери ответа немедленного действия состояние сервера
//   перечитывается: связка могла сохраниться, и следующий запрос не должен
//   отправлять прежний склад;
// - пустой набор изменений не отправляется вовсе: серверу нечего сохранять,
//   а пустой by_binding он прочитал бы как старую форму правила и стёр бы
//   независимые настройки блоков.

import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import {
  loadFbsStockDialog,
  type ApiBulkRuleItem,
  type FbsStockDialogData,
  type FbsStockDialogRow,
} from './fbsStockDialogLoader'

export type BindingRuleBody = { publish: boolean; mode: 'percent' | 'units'; value: number }

export type ServerClamp = {
  requested_value: number
  saved_value: number
  limiting_product_id: string
  limiting_product_name: string
}

/** Исход немедленного действия со связкой (сопоставление, приём заказов, добавление). */
export type BindingOutcome =
  | { ok: true; data: FbsStockDialogData }
  /** Отказ или потеря ответа. `data` — перечитанное состояние, если перечитать удалось. */
  | { ok: false; message: string; data: FbsStockDialogData | null }

export type SaveOutcome =
  /** Изменённых блоков нет — запрос не отправлялся. */
  | { kind: 'nothing' }
  | { kind: 'saved' }
  /** Сервер сохранил меньше запрошенного: остаток изменился между открытием и сохранением. */
  | { kind: 'clamped'; items: ApiBulkRuleItem[]; clamps: Record<string, ServerClamp> }
  | { kind: 'error'; message: string; data: FbsStockDialogData | null }

export type StockDialogSession = {
  /** Данные окна для этого набора товаров либо null, если за время запроса выбрали другие товары. */
  load: (chosen: FbsStockDialogRow[]) => Promise<FbsStockDialogData | null>
  putBinding: (
    marketplace: 'wb' | 'ozon',
    externalId: string,
    body: { wms_warehouse_id: string; served: boolean },
  ) => Promise<BindingOutcome>
  saveRule: (productIds: string[], byBinding: Record<string, BindingRuleBody>) => Promise<SaveOutcome>
}

export function createStockDialogSession({
  fetchImpl = fetch,
  headers,
  sellerId,
}: {
  fetchImpl?: typeof fetch
  headers: Record<string, string>
  sellerId: string
}): StockDialogSession {
  // Номер последней загрузки: ответ с другим номером устарел.
  let generation = 0
  let lastChosen: FbsStockDialogRow[] = []

  const read = (chosen: FbsStockDialogRow[]) =>
    loadFbsStockDialog({ headers, sellerId, chosen, fetchImpl })

  async function load(chosen: FbsStockDialogRow[]): Promise<FbsStockDialogData | null> {
    const mine = ++generation
    lastChosen = chosen
    const data = await read(chosen)
    return mine === generation ? data : null
  }

  /** Перечитать состояние для текущих товаров; отказ перечитывания — null. */
  async function reread(): Promise<FbsStockDialogData | null> {
    try {
      return await read(lastChosen)
    } catch {
      return null
    }
  }

  const message = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback)

  async function putBinding(
    marketplace: 'wb' | 'ozon',
    externalId: string,
    body: { wms_warehouse_id: string; served: boolean },
  ): Promise<BindingOutcome> {
    try {
      const res = await fetchImpl(apiUrl(`/fbs-sellers/${sellerId}/warehouses/${externalId}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ marketplace, ...body }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
    } catch (e) {
      // Результат неизвестен или отказ: перечитываем, чтобы окно держало
      // фактическое состояние связки, а не то, что было до запроса.
      return { ok: false, message: message(e, 'Не удалось сохранить связку'), data: await reread() }
    }
    const data = await reread()
    if (!data) {
      return { ok: false, message: 'Связка сохранена, но перечитать состояние не удалось — откройте окно заново', data: null }
    }
    return { ok: true, data }
  }

  async function saveRule(
    productIds: string[],
    byBinding: Record<string, BindingRuleBody>,
  ): Promise<SaveOutcome> {
    if (Object.keys(byBinding).length === 0) return { kind: 'nothing' }
    try {
      const res = await fetchImpl(apiUrl('/products/fbs-rule'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...headers },
        // PUT /products/fbs-rule ждёт правило вложенным в rule; by_binding
        // частичный — не переданные блоки сервер не трогает.
        body: JSON.stringify({ product_ids: productIds, rule: { by_binding: byBinding } }),
      })
      if (!res.ok) throw new Error(await readApiErrorMessage(res))
      const saved = (await res.json()) as { items?: ApiBulkRuleItem[]; clamps?: Record<string, ServerClamp> }
      const clamps = saved.clamps ?? {}
      if (Object.keys(clamps).length === 0) return { kind: 'saved' }
      return { kind: 'clamped', items: saved.items ?? [], clamps }
    } catch (e) {
      return { kind: 'error', message: message(e, 'Не удалось сохранить правило'), data: await reread() }
    }
  }

  return { load, putBinding, saveRule }
}
