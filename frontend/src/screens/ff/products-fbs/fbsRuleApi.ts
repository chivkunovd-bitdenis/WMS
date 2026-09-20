import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import type { FbsRule } from './stub'

// Тело правила публикации для PUT. Поштучные поля обязательны: сервер объявил
// их со значениями по умолчанию (units_mode=False, пустой units_by_warehouse),
// поэтому правило без них не «оставляет как было», а стирает режим штук и все
// лимиты. Явный ноль в units_by_warehouse — операторский лимит 0 шт., а не
// отсутствие ключа, и должен доезжать до сервера как ключ.
function ruleBody(rule: FbsRule) {
  return {
    publish: rule.publish,
    same_everywhere: rule.sameEverywhere,
    percent: rule.percent,
    by_warehouse: rule.byWarehouse,
    units_mode: rule.unitsMode,
    units_by_warehouse: rule.unitsByWarehouse,
  }
}

export async function putFbsRule(
  headers: Record<string, string>,
  productIds: string[],
  rule: FbsRule,
): Promise<void> {
  const body = ruleBody(rule)
  const json = { 'Content-Type': 'application/json', ...headers }
  if (productIds.length === 1) {
    const res = await fetch(apiUrl(`/products/${productIds[0]}/fbs-rule`), {
      method: 'PUT',
      headers: json,
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await readApiErrorMessage(res))
    return
  }
  const res = await fetch(apiUrl('/products/fbs-rule'), {
    method: 'PUT',
    headers: json,
    // Групповая ручка ждёт правило вложенным в rule и запрещает лишние поля:
    // плоское тело она отбивала как «rule: Field required».
    body: JSON.stringify({ product_ids: productIds, rule: body }),
  })
  if (!res.ok) throw new Error(await readApiErrorMessage(res))
}
