import { afterEach, expect, it, vi } from 'vitest'
import { trackPickSave, waitForPickSaves } from './pickSaveLifecycle'
afterEach(() => vi.useRealTimers())
it('waits for a save across close/reopen and releases the settled promise', async () => {
  let finish!: () => void
  const save = new Promise<void>((resolve) => { finish = resolve })
  trackPickSave(['s-success'], save)
  const done = vi.fn()
  const read = waitForPickSaves(['s-success']).then(done)
  await Promise.resolve(); expect(done).not.toHaveBeenCalled()
  finish(); await read; expect(done).toHaveBeenCalledOnce()
  await waitForPickSaves(['s-success'])
})
it('reports a failed save to the reopening document', async () => {
  const save = Promise.reject(new Error('Save rejected'))
  trackPickSave(['s-fail'], save)
  await expect(waitForPickSaves(['s-fail'])).rejects.toThrow('Save rejected')
  await waitForPickSaves(['s-fail'])
})
it('bounds the wait for a request whose response never arrives', async () => {
  vi.useFakeTimers()
  trackPickSave(['s-timeout'], new Promise<void>(() => undefined))
  const observed = expect(waitForPickSaves(['s-timeout'])).rejects.toThrow('Сохранение подбора ещё не подтверждено')
  await vi.advanceTimersByTimeAsync(10000)
  await observed
})
