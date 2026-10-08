import { describe, expect, it } from 'vitest'
import { isWorkspaceWriteScreenCurrent } from './fbsWorkspaceFreshness'

describe('WMS-666 print request freshness', () => {
  it('keeps a coalesced print alive after the entry refresh advances the UI sequence', async () => {
    let openingGeneration = 1
    let writeSequence = 0
    const beginWrite = () => {
      const generation = openingGeneration
      const sequence = ++writeSequence
      return {
        isCurrent: () => generation === openingGeneration,
        isLatest: () => sequence === writeSequence,
      }
    }

    const print = beginWrite()
    let finishPrefetch!: () => void
    const coalescedPrefetch = new Promise<void>((resolve) => { finishPrefetch = resolve })
    const entryRefresh = coalescedPrefetch.then(() => {
      const refreshWrite = beginWrite()
      return refreshWrite.isCurrent() && refreshWrite.isLatest()
    })
    const printContinues = coalescedPrefetch.then(() =>
      isWorkspaceWriteScreenCurrent(print, 'same-supply', 'same-supply'),
    )

    finishPrefetch()
    await expect(entryRefresh).resolves.toBe(true)
    expect(print.isLatest()).toBe(false)
    await expect(printContinues).resolves.toBe(true)

    // Closing and reopening the same supply changes the captured generation.
    openingGeneration += 1
    expect(isWorkspaceWriteScreenCurrent(print, 'same-supply', 'same-supply')).toBe(false)
  })
})
