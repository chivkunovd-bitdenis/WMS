import { apiUrl, getStoredToken, type AuthStoragePortal } from '../api'
import { CHUNK_RELOAD_KEY, shouldReloadChunk } from './errorRecovery'

export type ClientErrorContext = { screen?: string; component?: string; action?: string }
const FIELD_LIMITS = {
  message: 2_000, stack: 8_000, url: 1_000, screen: 300,
  component: 500, action: 300, user_agent: 500, app_build: 200,
}
const seen = new Map<string, number>()
let portal: AuthStoragePortal = 'fulfillment'

// Limit JSON-encoded UTF-8 bytes, including escaped control characters.
function clip(value: string, limit: number): string {
  let result = ''
  let size = 0
  const encoder = new TextEncoder()
  for (const char of value) {
    size += encoder.encode(JSON.stringify(char)).length - 2
    if (size > limit) break
    result += char
  }
  return result
}

export function reportClientError(error: unknown, context: ClientErrorContext = {}): void {
  try {
    const token = getStoredToken(portal)
    if (!token) return
    const message = clip(error instanceof Error ? error.message : String(error), FIELD_LIMITS.message)
    const now = Date.now()
    for (const [key, at] of seen) if (now - at >= 60_000) seen.delete(key)
    if (seen.has(message)) return
    // Bound memory even when every error message is different.
    if (seen.size >= 200) seen.delete(seen.keys().next().value!)
    seen.set(message, now)
    const fields = {
      message,
      stack: error instanceof Error ? (error.stack ?? '').split('\n').slice(0, 40).join('\n') : '',
      // Query strings/fragments may contain login links; the route is enough to locate the screen.
      url: window.location.origin + window.location.pathname,
      screen: context.screen ?? window.location.pathname,
      component: context.component ?? '',
      action: context.action ?? '',
      user_agent: navigator.userAgent,
      app_build: import.meta.url.split('/').pop() ?? '',
    }
    const body = JSON.stringify(Object.fromEntries(
      Object.entries(fields).map(([key, value]) => [key, clip(value, FIELD_LIMITS[key as keyof typeof FIELD_LIMITS])]),
    ))
    const authHeaders = { Authorization: `Bearer ${token}` }
    void fetch(apiUrl('/client-errors'), {
      method: 'POST', headers: { ...authHeaders, 'Content-Type': 'application/json' },
      body, keepalive: true,
    }).catch(() => { /* Reporting must never cause another error. */ })
  } catch { /* Includes unavailable storage and unusual rejection values. */ }
}

/** Do not reload when storage is unavailable: a persistent guard is mandatory. */
export function reloadChunkOnce(error: unknown): boolean {
  try {
    if (!shouldReloadChunk(error, sessionStorage.getItem(CHUNK_RELOAD_KEY) !== null)) return false
    sessionStorage.setItem(CHUNK_RELOAD_KEY, '1')
    window.location.reload()
    return true
  } catch {
    return false
  }
}

export function installClientErrorHandlers(activePortal: AuthStoragePortal): () => void {
  portal = activePortal
  const onError = (event: ErrorEvent) => {
    const error = event.error ?? new Error(event.message)
    reportClientError(error, { component: 'window', action: 'error' })
    reloadChunkOnce(error)
  }
  const onRejection = (event: PromiseRejectionEvent) => {
    reportClientError(event.reason, { component: 'window', action: 'unhandledrejection' })
    reloadChunkOnce(event.reason)
  }
  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
  }
}
