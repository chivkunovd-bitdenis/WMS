import { apiUrl } from '../api'
import { readApiErrorMessage } from './readApiErrorMessage'

export type KizReprintRow = {
  id: string
  seller_id: string
  kiz: string
  created_at: string
  print_started_at?: string | null
  replayed?: boolean
}

type KizReprintListResponse = { rows: KizReprintRow[] }
type KizReprintPrintClaimResponse = { row: KizReprintRow; claimed: boolean }

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
  const existing = rows.find((current) => current.id === row.id)
  return existing
    ? rows.map((current) => (current.id === row.id ? { ...current, ...row } : current))
    : [...rows, row]
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

export async function claimKizReprintPrint(
  token: string,
  reprintId: string,
  attemptKey: string,
): Promise<{ row: KizReprintRow; claimed: boolean }> {
  const response = await fetch(apiUrl(`/operations/kiz-reprints/${encodeURIComponent(reprintId)}/print-claim`), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ attempt_key: attemptKey }),
  })
  if (!response.ok) throw new Error(kizReprintErrorMessage(await readApiErrorMessage(response)))
  return (await response.json()) as KizReprintPrintClaimResponse
}

export async function markKizReprintPrintStarted(
  token: string,
  reprintId: string,
): Promise<KizReprintRow> {
  const response = await fetch(apiUrl(`/operations/kiz-reprints/${encodeURIComponent(reprintId)}/print-started`), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(kizReprintErrorMessage(await readApiErrorMessage(response)))
  return (await response.json()) as KizReprintRow
}

export async function releaseKizReprintPrintClaim(
  token: string,
  reprintId: string,
  attemptKey: string,
): Promise<KizReprintRow> {
  const response = await fetch(apiUrl(`/operations/kiz-reprints/${encodeURIComponent(reprintId)}/print-failed`), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ attempt_key: attemptKey }),
  })
  if (!response.ok) throw new Error(kizReprintErrorMessage(await readApiErrorMessage(response)))
  return (await response.json()) as KizReprintRow
}
