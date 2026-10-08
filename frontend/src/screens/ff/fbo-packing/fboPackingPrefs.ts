/**
 * WMS-686 R25: галки печати упаковки FBO хранятся отдельно от FBS и не влияют на неё.
 * Включена — печатаем через WMS Print при скане; выключена — не печатаем
 * и WMS Print не требуется. По умолчанию обе выключены.
 */
export type FboPackingPrintPreferences = {
  printBarcode: boolean
  printChz: boolean
}

export const DEFAULT_FBO_PACKING_PRINT_PREFERENCES: FboPackingPrintPreferences = {
  printBarcode: false,
  printChz: false,
}

const PREFERENCE_PREFIX = 'wms:fbo:scan-auto-print'

type TokenClaims = { sub?: unknown; tenant_id?: unknown }

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
    // Непонятная личность никогда не наследует чужую включённую печать.
    return { tenant: 'unknown-tenant', user: 'unknown-user' }
  }
}

/** Ключ галок: свой для FBO, по арендатору и сотруднику (у FBS — wms:fbs:scan-auto-print:…). */
export function fboPackingPrintStorageKey(token: string): string {
  const identity = tokenIdentity(token)
  return `${PREFERENCE_PREFIX}:${identity.tenant}:${identity.user}`
}

export function loadFboPackingPrintPreferences(token: string): FboPackingPrintPreferences {
  try {
    const raw = window.localStorage.getItem(fboPackingPrintStorageKey(token))
    if (!raw) return { ...DEFAULT_FBO_PACKING_PRINT_PREFERENCES }
    const saved = JSON.parse(raw) as Partial<FboPackingPrintPreferences> | null
    return {
      printBarcode: saved?.printBarcode === true,
      printChz: saved?.printChz === true,
    }
  } catch {
    // Повреждённое или недоступное хранилище никогда не включает печать само.
    return { ...DEFAULT_FBO_PACKING_PRINT_PREFERENCES }
  }
}

export function saveFboPackingPrintPreferences(token: string, value: FboPackingPrintPreferences): void {
  try {
    window.localStorage.setItem(fboPackingPrintStorageKey(token), JSON.stringify(value))
  } catch {
    // Хранилище недоступно: галки действуют до перезагрузки страницы.
  }
}
