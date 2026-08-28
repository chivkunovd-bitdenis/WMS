import { beforeEach, describe, expect, it, vi } from 'vitest'

const hookRuntime = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
}))

vi.mock('react', () => ({
  useEffect: (effect: () => void | (() => void)) => {
    hookRuntime.effects.push(effect)
  },
  useRef: <T>(value: T) => ({ current: value }),
}))

import { useFfInboundRequestScanner } from './useFfInboundRequestScanner'

function commitEffects(): Array<() => void> {
  const scheduled = hookRuntime.effects.splice(0)
  return scheduled
    .map((effect) => effect())
    .filter((cleanup): cleanup is () => void => typeof cleanup === 'function')
}

describe('TC-NEW-A3-004 scanner subscription lifecycle', () => {
  const addEventListener = vi.fn()
  const removeEventListener = vi.fn()

  beforeEach(() => {
    hookRuntime.effects.length = 0
    addEventListener.mockReset()
    removeEventListener.mockReset()
    vi.stubGlobal('document', {
      activeElement: null,
      addEventListener,
      removeEventListener,
    })
  })

  it('switches receiving to draft without duplicate document listeners and cleans up on unmount', () => {
    useFfInboundRequestScanner({
      receivingEnabled: true,
      draftEnabled: false,
      onReceivingScan: vi.fn(),
      onDraftScan: vi.fn(),
    })
    const receivingCleanups = commitEffects()

    expect(addEventListener).toHaveBeenCalledTimes(1)
    expect(addEventListener).toHaveBeenLastCalledWith('keydown', expect.any(Function), true)
    expect(receivingCleanups).toHaveLength(1)

    for (const cleanup of receivingCleanups) cleanup()
    expect(removeEventListener).toHaveBeenCalledTimes(1)

    useFfInboundRequestScanner({
      receivingEnabled: false,
      draftEnabled: true,
      onReceivingScan: vi.fn(),
      onDraftScan: vi.fn(),
    })
    const draftCleanups = commitEffects()

    expect(addEventListener).toHaveBeenCalledTimes(2)
    expect(draftCleanups).toHaveLength(1)

    for (const cleanup of draftCleanups) cleanup()
    expect(removeEventListener).toHaveBeenCalledTimes(2)
  })
})
