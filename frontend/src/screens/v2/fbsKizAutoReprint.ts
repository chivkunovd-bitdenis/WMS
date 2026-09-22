export type FbsKizAutoPrintSnapshot = {
  /** Idempotency key of the exact KIZ commit that allowed this print. */
  attemptId: string
  orderId: string
  kiz: string
  enabled: boolean
}

export type FbsKizAutoPrint = (kiz: string) => Promise<void>

const PREFERENCE_PREFIX = 'wms:fbs:kiz-auto-reprint:enabled'
const ATTEMPT_PREFIX = 'wms:fbs:kiz-auto-reprint:started'

type TokenClaims = { sub?: unknown; tenant_id?: unknown }

function tokenIdentity(token: string): { tenant: string; user: string } {
  try {
    const payload = token.split('.')[1]
    if (!payload) throw new Error('token payload is absent')
    const claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))) as TokenClaims
    const tenant = typeof claims.tenant_id === 'string' && claims.tenant_id ? claims.tenant_id : 'unknown-tenant'
    const user = typeof claims.sub === 'string' && claims.sub ? claims.sub : 'unknown-user'
    return { tenant, user }
  } catch {
    // A malformed token must never turn on a printer unexpectedly.
    return { tenant: 'unknown-tenant', user: 'unknown-user' }
  }
}

/** The setting belongs to one FF operator in one browser, not to a supply or warehouse. */
export function fbsKizAutoReprintStorageKey(token: string): string {
  const identity = tokenIdentity(token)
  return `${PREFERENCE_PREFIX}:${identity.tenant}:${identity.user}`
}

export function loadFbsKizAutoReprintEnabled(token: string): boolean {
  try {
    return window.localStorage.getItem(fbsKizAutoReprintStorageKey(token)) === 'true'
  } catch {
    return false
  }
}

export function saveFbsKizAutoReprintEnabled(token: string, value: boolean): void {
  try {
    window.localStorage.setItem(fbsKizAutoReprintStorageKey(token), value ? 'true' : 'false')
  } catch {
    // Storage can be disabled on a hardened warehouse workstation. The in-memory
    // checkbox state still applies to the current open workspace.
  }
}

function attemptStorageKey(attemptId: string): string {
  return `${ATTEMPT_PREFIX}:${attemptId}`
}

/**
 * A scan commit can be replayed after a lost response. Claim the browser-side
 * print before scheduling it, then retain that claim for the current browser
 * session. The queue keeps rapid scans in their original order.
 */
export class FbsKizAutoPrintQueue {
  private readonly startedAttempts = new Set<string>()
  private tail: Promise<void> = Promise.resolve()

  enqueue(snapshot: FbsKizAutoPrintSnapshot, print: FbsKizAutoPrint): Promise<boolean> {
    if (!snapshot.enabled || !this.claim(snapshot.attemptId)) return Promise.resolve(false)

    const job = this.tail.then(async () => {
      await print(snapshot.kiz)
    })
    // A failed print must not prevent the next saved scan from reaching its printer.
    this.tail = job.catch(() => undefined)
    return job.then(() => true)
  }

  private claim(attemptId: string): boolean {
    if (this.startedAttempts.has(attemptId)) return false
    this.startedAttempts.add(attemptId)
    try {
      const key = attemptStorageKey(attemptId)
      if (window.sessionStorage.getItem(key) === 'true') return false
      window.sessionStorage.setItem(key, 'true')
    } catch {
      // The in-memory claim is still enough for this open page.
    }
    return true
  }
}
