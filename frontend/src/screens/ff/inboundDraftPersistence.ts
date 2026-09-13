import { apiUrl } from '../../api'
import { randomId } from '../../utils/randomId'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type IntakeMutation = { method: 'POST' | 'PATCH' | 'PUT' | 'DELETE'; path: string; body?: Record<string, unknown> }
type SavedIntake = {
  pending?: IntakeMutation[]
  totals?: Record<string, string>
  applied?: IntakeMutation[]
  rejected?: IntakeMutation
}
const active = new Set<string>()

export function intakeStorageKey(token: string, document: string): string {
  const claims = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) as { sub: string; tenant_id: string }
  return `wms440:${apiUrl('')}:${claims.tenant_id}:${claims.sub}:${document}`
}
export function readIntake(token: string, document: string): SavedIntake {
  const raw = localStorage.getItem(intakeStorageKey(token, document))
  return raw ? JSON.parse(raw) as SavedIntake : {}
}
function writeIntake(token: string, document: string, value: SavedIntake) {
  localStorage.setItem(intakeStorageKey(token, document), JSON.stringify(value))
}
export function saveIntakeTotals(token: string, document: string, totals: Record<string, string>) {
  writeIntake(token, document, { ...readIntake(token, document), totals })
}
export function intakeMutation(method: IntakeMutation['method'], path: string, body?: Record<string, unknown>): IntakeMutation {
  return { method, path, ...(body ? { body: { ...body, mutation_id: randomId() } } : {}) }
}
function samePickerProduct(left: IntakeMutation, right: IntakeMutation): boolean {
  return left.method === right.method
    && left.path === right.path
    && left.body?.product_id != null
    && left.body.product_id === right.body?.product_id
}
/** Only the already submitted action is retained, not an offline work queue. */
export async function sendIntakeMutations(token: string, document: string, mutations?: IntakeMutation[]): Promise<Response> {
  const key = intakeStorageKey(token, document)
  if (active.has(key)) throw new Error('Дождитесь сохранения предыдущего запроса.')
  const saved = readIntake(token, document)
  if (mutations && saved.pending?.length) throw new Error('Проверьте результат предыдущего запроса приёмки.')
  const continuingRejectedPicker = mutations != null
    && saved.rejected != null
    && mutations.some((mutation) => samePickerProduct(mutation, saved.rejected!))
  const previous = continuingRejectedPicker ? saved : { ...saved, applied: undefined, rejected: undefined }
  let pending = mutations ?? saved.pending ?? []
  if (continuingRejectedPicker) {
    pending = pending.filter((mutation) => !saved.applied?.some((applied) => samePickerProduct(mutation, applied)))
  }
  if (!pending.length) throw new Error('Нет запроса для повторения.')
  active.add(key)
  try {
    writeIntake(token, document, { ...previous, pending }) // synchronous, before the first HTTP request
    let result: Response | undefined
    while (pending.length) {
      const mutation = pending[0]
      result = await fetch(apiUrl(mutation.path), {
        method: mutation.method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        ...(mutation.body ? { body: JSON.stringify(mutation.body) } : {}),
      })
      if (!result.ok && !(mutation.method === 'DELETE' && result.status === 404)) {
        const error = await readApiErrorMessage(result.clone())
        // A definite refusal did not apply this item or the untouched tail. Keep only the
        // already applied prefix while the picker corrects the rejected item.
        if (result.status >= 400 && result.status < 500 && ![408, 429].includes(result.status)) {
          const latest = readIntake(token, document)
          writeIntake(token, document, {
            ...latest,
            pending: undefined,
            ...(latest.applied?.length ? { rejected: mutation } : {}),
          })
        }
        throw new Error(error)
      }
      if (mutation.method === 'PATCH' && mutation.path.endsWith('/expected')) {
        const lineId = mutation.path.split('/').at(-2)!
        const latest = readIntake(token, document)
        if (latest.totals?.[lineId] === String(mutation.body?.expected_qty)) {
          const totals = { ...latest.totals }; delete totals[lineId]
          writeIntake(token, document, { ...latest, totals })
        }
      }
      pending = pending.slice(1)
      const latest = readIntake(token, document)
      writeIntake(token, document, {
        ...latest,
        pending: pending.length ? pending : undefined,
        applied: pending.length ? [...(latest.applied ?? []), mutation] : undefined,
        rejected: undefined,
      })
    }
    return result!
  } finally { active.delete(key) }
}
