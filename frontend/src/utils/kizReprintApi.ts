import { apiUrl } from '../api'
import { readApiErrorMessage } from './readApiErrorMessage'

export type KizReprintRow = {
  id: string
  seller_id: string
  kiz: string
  created_at: string
  replayed?: boolean
}

type KizReprintListResponse = { rows: KizReprintRow[] }

export const KIZ_REPRINT_ERROR_MESSAGES: Record<string, string> = {
  not_a_kiz: 'Код Честного знака не распознан. Отсканируйте полный КИЗ ещё раз.',
  gs_separator_lost: 'Разделители КИЗ потеряны. Отсканируйте код целиком ещё раз.',
  idempotency_key_reused: 'Повторный запрос относится к другому КИЗ. Отсканируйте код ещё раз.',
  seller_not_found: 'Селлер не найден. Обновите страницу и выберите его снова.',
  forbidden: 'Нет доступа к перепечатке КИЗ в этом контексте.',
}

export function kizReprintErrorMessage(code: string): string {
  return KIZ_REPRINT_ERROR_MESSAGES[code] ?? 'Не удалось сохранить КИЗ для печати. Повторите сканирование.'
}

export function mergeKizReprintRow(rows: KizReprintRow[], row: KizReprintRow): KizReprintRow[] {
  return rows.some((current) => current.id === row.id) ? rows : [...rows, row]
}

export async function loadKizReprints(token: string, sellerId: string): Promise<KizReprintRow[]> {
  const response = await fetch(
    apiUrl(`/operations/kiz-reprints?seller_id=${encodeURIComponent(sellerId)}`),
    { headers: { Authorization: `Bearer ${token}` } },
  )
  if (!response.ok) {
    throw new Error(kizReprintErrorMessage(await readApiErrorMessage(response)))
  }
  return ((await response.json()) as KizReprintListResponse).rows
}

export async function saveKizReprint(
  token: string,
  input: { sellerId: string; kiz: string; idempotencyKey: string },
): Promise<KizReprintRow> {
  const response = await fetch(apiUrl('/operations/kiz-reprints'), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      seller_id: input.sellerId,
      kiz: input.kiz,
      idempotency_key: input.idempotencyKey,
    }),
  })
  if (!response.ok) {
    throw new Error(kizReprintErrorMessage(await readApiErrorMessage(response)))
  }
  return (await response.json()) as KizReprintRow
}
