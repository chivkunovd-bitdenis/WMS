import type { KizReprintRow } from './kizReprintApi'

export type KizPrint = (codes: string[]) => Promise<void>

/** A network replay must not cause a second automatic printer invocation. */
export async function printScannedKiz(row: KizReprintRow, print: KizPrint): Promise<boolean> {
  if (row.replayed) return false
  await print([row.kiz])
  return true
}

export async function printKizHistory(rows: KizReprintRow[], print: KizPrint): Promise<void> {
  if (rows.length === 0) return
  await print(rows.map((row) => row.kiz))
}
