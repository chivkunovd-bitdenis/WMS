import { fbsSameStickerScan } from '../../v2/fbsUx'
import { whereIs, type Cell, type WarehouseObject } from './objectsStub'

export type ScanContext = { cellId: string | null; objectId: string | null }
export const emptyScanContext: ScanContext = { cellId: null, objectId: null }

export function scanCandidates(raw: string): string[] {
  return [raw.trim().replace(/^\][A-Za-z][0-9]/, '')]
}

/** Context changes and stock requests share one queue, including rapid scanner bursts. */
export function createSortingScanner(initial: ScanContext, dependencies: {
  data: () => { cells: Cell[]; objects: WarehouseObject[] }
  place: (object: WarehouseObject, cellId: string) => Promise<void>
  product: (barcode: string, context: ScanContext) => Promise<string | void>
  changed: (context: ScanContext) => void
  notice: (message: string) => void
  error: (error: unknown) => void
}) {
  let context = initial
  let queue = Promise.resolve()
  const change = (next: ScanContext) => {
    context = next
    dependencies.changed(next)
  }
  const enqueue = (operation: () => Promise<void>) => {
    queue = queue.then(operation).catch(dependencies.error)
    return queue
  }
  return {
    selectCell: (cellId: string) => enqueue(async () => change({ cellId, objectId: null })),
    scan: (raw: string) => enqueue(async () => {
      const candidates = scanCandidates(raw)
      const matches = (value: string) => candidates.some((code) => fbsSameStickerScan(code.toLowerCase(), value.toLowerCase()))
      const { cells, objects } = dependencies.data()
      const cell = cells.find((one) => matches(one.barcode) || matches(one.code))
      if (cell) {
        const closing = context.cellId === cell.id
        change(closing ? emptyScanContext : { cellId: cell.id, objectId: null })
        dependencies.notice(closing ? `Ячейка ${cell.code} закрыта` : `Ячейка ${cell.code} открыта`)
        return
      }
      if (!context.cellId) throw new Error('Сначала отсканируйте ячейку')
      const object = objects.find((one) => matches(one.barcode))
      if (object) {
        if (context.objectId === object.id) {
          change({ ...context, objectId: null })
          dependencies.notice(`Тара ${object.code} закрыта; товар идёт прямо в ячейку`)
          return
        }
        // Clear the previous container even when opening the next one fails.
        change({ ...context, objectId: null })
        try {
          if (whereIs(object.holder, objects, cells).cell?.id !== context.cellId) {
            await dependencies.place(object, context.cellId)
          }
        } catch (error) {
          // Later buffered products must not fall through into the bare cell.
          change(emptyScanContext)
          throw error
        }
        change({ ...context, objectId: object.id })
        dependencies.notice(`Тара ${object.code} открыта`)
        return
      }
      const message = await dependencies.product(candidates[0], context)
      dependencies.notice(message ?? 'Перемещена 1 шт')
    }),
  }
}
