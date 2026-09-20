import { describe, expect, it } from 'vitest'
import { isChunkLoadError, nextRecovery, shouldReloadChunk } from './errorRecovery'

describe('WMS-484 recovery decisions', () => {
  it('remounts immediately, then after 1.5 seconds, then shows fallback', () => {
    const first = nextRecovery([], 100)
    expect(first).toEqual({ failures: [100], fallback: false, delayMs: 0 })
    const second = nextRecovery(first.failures, 200)
    expect(second).toEqual({ failures: [100, 200], fallback: false, delayMs: 1500 })
    expect(nextRecovery(second.failures, 1700).fallback).toBe(true)
  })
  it('expires failures individually after 30 seconds', () => {
    expect(nextRecovery([0, 1500], 30_000)).toEqual({ failures: [1500, 30_000], fallback: false, delayMs: 1500 })
    expect(nextRecovery([0, 1500], 31_500)).toEqual({ failures: [31_500], fallback: false, delayMs: 0 })
  })
  it('does not share attempts between boundaries or mutate history', () => {
    const history = [100, 200]
    expect(nextRecovery(history, 300).fallback).toBe(true)
    expect(nextRecovery([], 300).fallback).toBe(false)
    expect(history).toEqual([100, 200])
  })
  it.each([
    'Failed to fetch dynamically imported module: https://host/assets/old.js',
    'error loading dynamically imported module',
    'Importing a module script failed.',
    'Loading chunk 42 failed.',
    'Loading CSS chunk 42 failed.',
    'Unable to preload CSS for /assets/old.css',
  ])('recognises chunk failure: %s', (message) => {
    expect(isChunkLoadError(new Error(message))).toBe(true)
    expect(shouldReloadChunk(new Error(message), false)).toBe(true)
    expect(shouldReloadChunk(new Error(message), true)).toBe(false)
  })
  it('recognises the error name and ignores unrelated failures', () => {
    const error = new Error('network')
    error.name = 'ChunkLoadError'
    expect(isChunkLoadError(error)).toBe(true)
    expect(isChunkLoadError(new Error('Failed to fetch'))).toBe(false)
    expect(isChunkLoadError(new Error('removeChild'))).toBe(false)
    expect(isChunkLoadError(null)).toBe(false)
    expect(isChunkLoadError({ toString() { throw new Error('broken value') } })).toBe(false)
  })
})
