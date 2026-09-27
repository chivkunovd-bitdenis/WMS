import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFbsWorkspaceStage, saveFbsWorkspaceStage } from './fbsWorkspaceStage'

const storageFixture = () => {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('WMS-558 FBS stage restoration', () => {
  it.each(['boxes', 'packing', 'picking', 'composition'] as const)('restores %s after opening the same supply again', (stage) => {
    const storage = storageFixture()
    saveFbsWorkspaceStage('supply-a', stage, storage)
    expect(readFbsWorkspaceStage('supply-a', storage)).toBe(stage)
  })

  it('keeps separate selections per supply and no selection for a new supply', () => {
    const storage = storageFixture()
    saveFbsWorkspaceStage('supply-a', 'boxes', storage)
    expect(readFbsWorkspaceStage('supply-b', storage)).toBeNull()
    saveFbsWorkspaceStage('supply-b', 'packing', storage)
    expect(readFbsWorkspaceStage('supply-a', storage)).toBe('boxes')
    expect(readFbsWorkspaceStage('supply-b', storage)).toBe('packing')
  })

  it('does not erase selection when initial loading reads it repeatedly', () => {
    const storage = storageFixture()
    saveFbsWorkspaceStage('supply-a', 'composition', storage)
    expect(readFbsWorkspaceStage('supply-a', storage)).toBe('composition')
    expect(readFbsWorkspaceStage('supply-a', storage)).toBe('composition')
  })

  it('rejects corrupt or obsolete stages and tolerates inaccessible browser storage', () => {
    expect(readFbsWorkspaceStage('supply-a', { getItem: () => 'assembling', setItem: () => {} })).toBeNull()
    vi.stubGlobal('window', { get sessionStorage() { throw new Error('storage denied') } })
    expect(readFbsWorkspaceStage('supply-a')).toBeNull()
    expect(() => saveFbsWorkspaceStage('supply-a', 'boxes')).not.toThrow()
    vi.stubGlobal('window', undefined)
    expect(readFbsWorkspaceStage('supply-a')).toBeNull()
    expect(() => saveFbsWorkspaceStage('supply-a', 'boxes')).not.toThrow()
  })
})
