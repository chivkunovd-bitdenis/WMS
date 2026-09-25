import type { KizReprintRow } from './kizReprintApi'

export type KizPrint = (codes: string[]) => Promise<void>

export type AutoKizReprintApi = {
  claim: (row: KizReprintRow, attemptKey: string) => Promise<{ row: KizReprintRow; claimed: boolean }>
  markStarted: (row: KizReprintRow) => Promise<KizReprintRow>
  releaseClaim: (row: KizReprintRow, attemptKey: string) => Promise<unknown>
}

export type AutoKizReprintResult = {
  row: KizReprintRow
  printStarted: boolean
}

export class KizPrintOutcomeUnknownError extends Error {
  readonly printOutcomeUnknown = true

  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'KizPrintOutcomeUnknownError'
  }
}

/** A network replay must not cause a second automatic printer invocation. */
export async function printScannedKiz(row: KizReprintRow, print: KizPrint): Promise<boolean> {
  if (row.replayed) return false
  await print([row.kiz])
  return true
}

/**
 * Starts the automatic scan print exactly once per persisted history row.
 * A replayed save response is deliberately not used as a printing verdict:
 * after a lost response the retry obtains the still-pending server claim.
 */
export async function startAutoKizReprintPrint(
  row: KizReprintRow,
  attemptKey: string,
  print: KizPrint,
  api: AutoKizReprintApi,
): Promise<AutoKizReprintResult> {
  const claim = await api.claim(row, attemptKey)
  if (!claim.claimed) {
    if (claim.row.print_started_at == null) {
      throw new KizPrintOutcomeUnknownError(
        'Предыдущий запуск печати не подтверждён; автоматический повтор остановлен.',
      )
    }
    return { row: claim.row, printStarted: false }
  }
  try {
    await print([claim.row.kiz])
  } catch (cause) {
    await api.releaseClaim(claim.row, attemptKey).catch(() => undefined)
    throw cause
  }
  try {
    return { row: await api.markStarted(claim.row), printStarted: true }
  } catch (cause) {
    // window.print() has already been called. A lost acknowledgement must not
    // release either browser or server claim and cause a blind second copy.
    throw new KizPrintOutcomeUnknownError(
      'Печать была запущена, но подтверждение результата не получено.',
      { cause },
    )
  }
}

export async function printKizHistory(rows: KizReprintRow[], print: KizPrint): Promise<void> {
  if (rows.length === 0) return
  await print(rows.map((row) => row.kiz))
}
