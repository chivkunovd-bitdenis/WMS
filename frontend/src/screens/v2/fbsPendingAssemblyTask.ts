import { apiUrl } from '../../api'
import { createFbsAssemblyTask } from './fbsApi'

type TokenClaims = { sub?: unknown; tenant_id?: unknown }

export type PendingFbsAssemblyTask = {
  supplyIds: string[]
  idempotencyKey: string
}

function tokenIdentity(token: string): { tenant: string; user: string } {
  try {
    const payload = token.split('.')[1]
    if (!payload) throw new Error('token payload is absent')
    const claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))) as TokenClaims
    return {
      tenant: typeof claims.tenant_id === 'string' && claims.tenant_id ? claims.tenant_id : 'unknown-tenant',
      user: typeof claims.sub === 'string' && claims.sub ? claims.sub : 'unknown-user',
    }
  } catch {
    return { tenant: 'unknown-tenant', user: 'unknown-user' }
  }
}

/** The API base, tenant and actor keep an interrupted attempt out of another portal session. */
export function fbsPendingAssemblyTaskStorageKey(token: string): string {
  const identity = tokenIdentity(token)
  return `wms:fbs:assembly-task:pending:${apiUrl('/')}:${identity.tenant}:${identity.user}`
}

export function readPendingFbsAssemblyTask(token: string): PendingFbsAssemblyTask | null {
  try {
    const raw = window.localStorage.getItem(fbsPendingAssemblyTaskStorageKey(token))
    const parsed = raw ? JSON.parse(raw) as Partial<PendingFbsAssemblyTask> : null
    if (!parsed || !Array.isArray(parsed.supplyIds) || parsed.supplyIds.length === 0 || typeof parsed.idempotencyKey !== 'string') {
      return null
    }
    if (!parsed.supplyIds.every((id) => typeof id === 'string' && id)) return null
    return { supplyIds: [...parsed.supplyIds], idempotencyKey: parsed.idempotencyKey }
  } catch {
    return null
  }
}

/** Save before the POST: an interrupted reply must replay the identical payload. */
export function savePendingFbsAssemblyTask(token: string, task: PendingFbsAssemblyTask): void {
  try {
    window.localStorage.setItem(fbsPendingAssemblyTaskStorageKey(token), JSON.stringify(task))
  } catch {
    // The server idempotency key still protects a retry in the currently open dialog.
  }
}

/** Only the confirmed, identical attempt may erase the recovery record. */
export function clearPendingFbsAssemblyTask(token: string, task: PendingFbsAssemblyTask): void {
  try {
    const current = readPendingFbsAssemblyTask(token)
    if (
      current?.idempotencyKey === task.idempotencyKey
      && current.supplyIds.length === task.supplyIds.length
      && current.supplyIds.every((id, index) => id === task.supplyIds[index])
    ) {
      window.localStorage.removeItem(fbsPendingAssemblyTaskStorageKey(token))
    }
  } catch {
    // A stale local record is harmless: the server replays its original task.
  }
}

export async function resumePendingFbsAssemblyTask(
  token: string,
  authHeaders: (token: string) => Record<string, string>,
  task = readPendingFbsAssemblyTask(token),
): Promise<boolean> {
  if (!task) return false
  await createFbsAssemblyTask(token, authHeaders, {
    supply_ids: task.supplyIds,
    idempotency_key: task.idempotencyKey,
  })
  clearPendingFbsAssemblyTask(token, task)
  return true
}
