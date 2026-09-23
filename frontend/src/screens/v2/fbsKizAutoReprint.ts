export type FbsKizAutoPrintSnapshot = {
  /** Idempotency key of the exact KIZ commit that allowed this print. */
  attemptId: string
  orderId: string
  kiz: string
  enabled: boolean
}

export type FbsKizAutoPrint = (kiz: string) => Promise<void>

export type FbsAutomaticPrintClaimState = {
  claimed: boolean
  started: boolean
}

export type FbsAutomaticPrintClaimApi = {
  claim: (attemptKey: string) => Promise<FbsAutomaticPrintClaimState>
  markStarted: (attemptKey: string) => Promise<FbsAutomaticPrintClaimState>
  releaseClaim: (attemptKey: string) => Promise<unknown>
}

export type FbsAutomaticPrintResult = {
  started: boolean
  printedNow: boolean
}

export class FbsPrintOutcomeUnknownError extends Error {
  readonly printOutcomeUnknown = true

  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'FbsPrintOutcomeUnknownError'
  }
}

type PrintOutcomeError = Error & { printOutcomeUnknown?: boolean }

function outcomeMayBeUnknown(cause: unknown): boolean {
  return cause instanceof Error && (cause as PrintOutcomeError).printOutcomeUnknown === true
}

/**
 * Persist a print claim around one browser print invocation. A target already
 * marked started is complete without another copy; an outstanding foreign
 * claim is an unknown physical outcome and must never be retried blindly.
 */
export async function startClaimedAutomaticPrint(
  attemptKey: string,
  print: () => Promise<void>,
  api: FbsAutomaticPrintClaimApi,
): Promise<FbsAutomaticPrintResult> {
  const claim = await api.claim(attemptKey)
  if (!claim.claimed) {
    if (claim.started) return { started: true, printedNow: false }
    throw new FbsPrintOutcomeUnknownError(
      'Предыдущий запуск печати не подтверждён; автоматический повтор остановлен.',
    )
  }
  try {
    await print()
  } catch (cause) {
    await api.releaseClaim(attemptKey).catch(() => undefined)
    throw cause
  }
  try {
    const started = await api.markStarted(attemptKey)
    return { started: started.started, printedNow: true }
  } catch (cause) {
    throw new FbsPrintOutcomeUnknownError(
      'Печать была запущена, но подтверждение результата не получено.',
      { cause },
    )
  }
}

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
      try {
        await print(snapshot.kiz)
      } catch (cause) {
        // Release only a proven pre-print failure. If window.print() may have
        // run, retaining the claim is the only safe way to avoid a blind copy.
        if (!outcomeMayBeUnknown(cause)) this.release(snapshot.attemptId)
        throw cause
      }
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

  private release(attemptId: string): void {
    this.startedAttempts.delete(attemptId)
    try {
      window.sessionStorage.removeItem(attemptStorageKey(attemptId))
    } catch {
      // In-memory release is sufficient for the open page.
    }
  }
}
