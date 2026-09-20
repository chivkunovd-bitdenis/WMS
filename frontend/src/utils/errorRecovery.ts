/** Decisions are independent of React, browser storage and timers. */
export const RECOVERY_WINDOW_MS = 30_000
export const RECOVERY_DELAY_MS = 1_500
export const CHUNK_RELOAD_KEY = 'wms-client-error-chunk-reloaded'

export function nextRecovery(failures: readonly number[], now: number) {
  const recent = [...failures.filter((at) => now - at < RECOVERY_WINDOW_MS), now]
  return {
    failures: recent,
    fallback: recent.length >= 3,
    delayMs: recent.length === 2 ? RECOVERY_DELAY_MS : 0,
  }
}

export function isChunkLoadError(error: unknown): boolean {
  try {
    const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error)
    return /ChunkLoadError|Loading (?:CSS )?chunk .+ failed|Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(message)
  } catch {
    return false
  }
}

export function shouldReloadChunk(error: unknown, alreadyReloaded: boolean): boolean {
  return !alreadyReloaded && isChunkLoadError(error)
}
