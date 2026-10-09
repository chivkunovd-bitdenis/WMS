import { apiUrl } from '../../api'
import { randomId } from '../../utils/randomId'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type IntakeMutation = { method: 'POST' | 'PATCH' | 'PUT' | 'DELETE'; path: string; body?: Record<string, unknown> }
export type InboundLabelAttempt = {
  id: string
  printedBefore: Record<string, string | null>
  paths: string[]
  state: 'unknown' | 'transferred' | 'complete'
}
type SavedIntake = {
  labelAttempt?: InboundLabelAttempt
  pending?: IntakeMutation[]
  totals?: Record<string, string>
  pickerAttempt?: true
  applied?: IntakeMutation[]
  rejected?: IntakeMutation
}
const active = new Set<string>()
const INTAKE_KEY_PREFIX = 'wms440:'

export function intakeStorageKey(token: string, document: string): string {
  const claims = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) as { sub: string; tenant_id: string }
  return `${INTAKE_KEY_PREFIX}${apiUrl('')}:${claims.tenant_id}:${claims.sub}:${document}`
}
export function readIntake(token: string, document: string): SavedIntake {
  // Read-only screens do not need draft persistence. Keep them renderable when
  // authentication is represented by a non-JWT token (for example in an
  // isolated UI harness), while preserving strict persistence for real edits.
  let storageKey: string
  try {
    storageKey = intakeStorageKey(token, document)
  } catch {
    return {}
  }
  const raw = localStorage.getItem(storageKey)
  const saved = raw ? JSON.parse(raw) as SavedIntake : {}
  // A reserve exists only while localStorage refused the newer record of the label attempt.
  const remembered = readReserve(storageKey)
  return remembered ? { ...saved, labelAttempt: remembered } : saved
}
function writeIntake(token: string, document: string, value: SavedIntake) {
  localStorage.setItem(intakeStorageKey(token, document), JSON.stringify(value))
}
/**
 * Recovery data of a label print attempt: its identity, its state and the technical marks still to be set.
 * Never the label HTML or barcode images: hundreds of base64 images do not fit the browser storage and
 * nothing reads them, because a new print builds the labels again. The fields are picked one by one, so a
 * record written by an earlier version (with html) is not carried over. A completed attempt keeps only
 * its identity.
 */
function storedLabelAttempt(attempt: InboundLabelAttempt): InboundLabelAttempt {
  const { id, printedBefore, paths, state } = attempt
  return state === 'complete' ? { id, printedBefore: {}, paths: [], state } : { id, printedBefore, paths, state }
}
/** Earlier versions kept the whole label HTML in the attempt. Nothing reads it, but it still fills the storage. */
function dropStaleLabelHtml() {
  for (let index = localStorage.length - 1; index >= 0; index--) {
    const key = localStorage.key(index)
    if (!key?.startsWith(INTAKE_KEY_PREFIX)) continue
    try {
      const saved = JSON.parse(localStorage.getItem(key) ?? 'null') as SavedIntake | null
      if (!saved?.labelAttempt || !('html' in saved.labelAttempt)) continue
      localStorage.setItem(key, JSON.stringify({ ...saved, labelAttempt: storedLabelAttempt(saved.labelAttempt) }))
    } catch {
      // A record that cannot be read or rewritten stays as it is.
    }
  }
}
/**
 * Reserve of the label print attempt while localStorage refuses its record (full quota): the page memory,
 * for a repeat in the open screen, and sessionStorage under the same tenant/user/document key, for a
 * repeat after a reload of the tab. Without it the repeat would not find the attempt and would send a
 * second tape instead of asking the operator or repairing the marks. A reserve is newer than whatever
 * localStorage still holds, so it is read first and is removed as soon as localStorage takes a record.
 */
const reserve = new Map<string, InboundLabelAttempt>()
function readReserve(key: string): InboundLabelAttempt | undefined {
  const inPage = reserve.get(key)
  if (inPage) return inPage
  try {
    const raw = sessionStorage.getItem(key)
    const saved = raw ? JSON.parse(raw) as InboundLabelAttempt : undefined
    return typeof saved?.id === 'string' ? saved : undefined
  } catch {
    return undefined
  }
}
function writeReserve(key: string, attempt: InboundLabelAttempt) {
  reserve.set(key, attempt)
  try {
    sessionStorage.setItem(key, JSON.stringify(attempt))
  } catch {
    // The page memory still holds it. An older copy must not outlive a reload as if it were current.
    try { sessionStorage.removeItem(key) } catch { /* nothing more to do */ }
  }
}
function clearReserve(key: string) {
  reserve.delete(key)
  try { sessionStorage.removeItem(key) } catch { /* nothing to clear */ }
}
function localRecordHasAttempt(key: string): boolean {
  try {
    const raw = localStorage.getItem(key)
    return Boolean(raw && (JSON.parse(raw) as SavedIntake).labelAttempt)
  } catch {
    return true
  }
}
/**
 * Keep the recovery data of a label print attempt in the existing tenant/user/document record.
 * The record only protects against a second silent print, so a failing storage (full quota, blocked
 * storage) must never stop the print itself: nothing is thrown, the print continues and the attempt is
 * kept in the reserve instead.
 */
export function saveInboundLabelAttempt(token: string, document: string, labelAttempt: InboundLabelAttempt) {
  const stored = storedLabelAttempt(labelAttempt)
  const write = () => writeIntake(token, document, { ...readIntake(token, document), labelAttempt: stored })
  let recorded = false
  try {
    write()
    recorded = true
  } catch {
    try {
      dropStaleLabelHtml()
      write()
      recorded = true
    } catch {
      // Falls back to the reserve below.
    }
  }
  let key: string
  try {
    key = intakeStorageKey(token, document)
  } catch {
    return
  }
  // A finished attempt needs no reserve unless an older unfinished record in localStorage would come back.
  if (recorded || (stored.state === 'complete' && !localRecordHasAttempt(key))) clearReserve(key)
  else writeReserve(key, stored)
}
export function saveIntakeTotals(token: string, document: string, totals: Record<string, string>) {
  writeIntake(token, document, { ...readIntake(token, document), totals })
}
export function beginIntakePickerAttempt(token: string, document: string) {
  const saved = readIntake(token, document)
  if (!saved.pending?.length) {
    writeIntake(token, document, { ...saved, pickerAttempt: true, applied: undefined, rejected: undefined })
  }
}
export function finishIntakePickerAttempt(token: string, document: string) {
  const saved = readIntake(token, document)
  writeIntake(token, document, {
    ...saved,
    pickerAttempt: undefined,
    ...(saved.pending?.length ? {} : { applied: undefined, rejected: undefined }),
  })
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
  const continuingPickerAttempt = mutations != null
    && saved.pickerAttempt === true
    && Boolean(saved.applied?.length)
  const previous = continuingPickerAttempt ? saved : { ...saved, applied: undefined, rejected: undefined }
  let pending = mutations ?? saved.pending ?? []
  if (continuingPickerAttempt) {
    pending = pending.filter((mutation) => !saved.applied?.some((applied) => samePickerProduct(mutation, applied)))
  }
  if (!pending.length) {
    if (continuingPickerAttempt) {
      finishIntakePickerAttempt(token, document)
      return new Response(null, { status: 204 })
    }
    throw new Error('Нет запроса для повторения.')
  }
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
        pickerAttempt: pending.length ? latest.pickerAttempt : undefined,
      })
    }
    return result!
  } finally { active.delete(key) }
}
