import { fbsSameStickerScan } from '../../v2/fbsUx'
import { whereIs, type Cell, type WarehouseObject } from './objectsStub'
import { randomId } from '../../../utils/randomId'

export type ScanContext = { cellId: string | null; objectId: string | null }
export const emptyScanContext: ScanContext = { cellId: null, objectId: null }

export class RejectedScan extends Error {}
type Command = { id: string; raw?: string; cellId?: string; before?: ScanContext }

export function scanCandidates(raw: string): string[] {
  return [raw.trim().replace(/^[\]ъЪ][A-Za-zА-Яа-яЁё][0-9]/, '')]
}

/** Context changes and stock requests share one queue, including rapid scanner bursts. */
export function createSortingScanner(initial: ScanContext, dependencies: {
  data: () => { cells: Cell[]; objects: WarehouseObject[] }
  place: (object: WarehouseObject, cellId: string, operationId: string) => Promise<void>
  product: (barcode: string, context: ScanContext, operationId: string) => Promise<string | void>
  changed: (context: ScanContext) => void
  notice: (message: string) => void
  error: (error: unknown) => void
  storage?: { storage: Storage; key: string }
  pending?: (count: number, paused: boolean) => void
  idle?: () => void
}) {
  let context = initial
  let commands: Command[] = []
  const disk = dependencies.storage
  if (disk) {
    const saved = disk.storage.getItem(disk.key)
    if (saved) {
      const state = JSON.parse(saved) as { context: ScanContext; commands: Command[] }
      context = state.context
      commands = state.commands
    }
  }
  let running: Promise<void> | null = null
  let paused = false
  const persist = () => {
    if (disk) disk.storage.setItem(disk.key, JSON.stringify({ context, commands }))
  }
  const notify = () => dependencies.pending?.(commands.length, paused)
  const change = (next: ScanContext) => {
    context = next
    dependencies.changed(next)
  }
  const execute = async (command: Command) => {
      if (command.cellId) {
        if (context.cellId !== command.cellId) change({ cellId: command.cellId, objectId: null })
        return
      }
      const candidates = scanCandidates(command.raw ?? '')
      const matches = (value: string) => candidates.some((code) => fbsSameStickerScan(code.toLowerCase(), value.toLowerCase()))
      const { cells, objects } = dependencies.data()
      const cell = cells.find((one) => matches(one.barcode)) ?? cells.find((one) => matches(one.code))
      if (cell) {
        const closing = context.cellId === cell.id
        change(closing ? emptyScanContext : { cellId: cell.id, objectId: null })
        dependencies.notice(closing ? `Ячейка ${cell.code} закрыта` : `Ячейка ${cell.code} открыта`)
        return
      }
      if (!context.cellId) throw new RejectedScan('Сначала отсканируйте ячейку')
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
            await dependencies.place(object, context.cellId, command.id)
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
      const message = await dependencies.product(candidates[0], context, command.id)
      dependencies.notice(message ?? 'Перемещена 1 шт')
  }
  const drain = (): Promise<void> => {
    if (running) return running
    if (paused) return Promise.resolve()
    running = Promise.resolve().then(async () => {
      while (commands.length && !paused) {
        const command = commands[0]
        try {
          command.before ??= context
          persist() // Intent + its original target survive a lost response/reload.
          context = command.before
          await execute(command)
          const remaining = commands.slice(1)
          if (disk) disk.storage.setItem(disk.key, JSON.stringify({ context, commands: remaining }))
          commands = remaining
        } catch (error) {
          if (disk && !(error instanceof RejectedScan)) {
            paused = true
            dependencies.error(new Error(`${error instanceof Error ? error.message : 'Нет ответа от сервера'}. Очередь сохранена. Обновите страницу, чтобы продолжить.`))
          } else {
            commands.shift()
            persist()
            dependencies.error(error)
          }
        }
        notify()
      }
    }).finally(() => {
      running = null
      if (!commands.length) dependencies.idle?.()
      else if (!paused) void drain()
    })
    return running
  }
  const enqueue = (command: Command) => {
    try {
      // Save synchronously, before returning control to the physical scanner.
      if (disk) disk.storage.setItem(disk.key, JSON.stringify({ context, commands: [...commands, command] }))
      commands.push(command)
      notify()
      return drain()
    } catch (error) {
      dependencies.error(error)
      return Promise.resolve()
    }
  }
  return {
    selectCell: (cellId: string) => enqueue({ id: randomId(), cellId }),
    scan: (raw: string) => enqueue({ id: randomId(), raw }),
    resume: () => { paused = false; change(context); notify(); return drain() },
  }
}
