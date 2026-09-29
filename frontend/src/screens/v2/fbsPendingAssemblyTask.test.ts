// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  fbsPendingAssemblyTaskStorageKey,
  readPendingFbsAssemblyTask,
  resumePendingFbsAssemblyTask,
  savePendingFbsAssemblyTask,
} from './fbsPendingAssemblyTask'

const token = (tenant = 'ff-a', user = 'operator-a') =>
  `header.${btoa(JSON.stringify({ tenant_id: tenant, sub: user }))}.signature`

const authHeaders = () => ({ Authorization: 'Bearer test' })
const task = { supplyIds: ['supply-a', 'supply-b'], idempotencyKey: 'assembly-attempt-1' }
const originalFetch = globalThis.fetch

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  globalThis.fetch = originalFetch
})

describe('WMS-588: durable assembly-task replay', () => {
  it('keeps the exact attempt through a pre-commit failure and reload, then creates one task', async () => {
    const calls: Array<{ body: unknown; stored: boolean }> = []
    let committed = 0
    let failBeforeCommit = true
    globalThis.fetch = (async (_input, init) => {
      calls.push({ body: JSON.parse(String(init?.body)), stored: readPendingFbsAssemblyTask(token()) !== null })
      if (failBeforeCommit) throw new TypeError('network offline before commit')
      committed += 1
      return json({ id: 'task-1', number: '1', created_at: '', created_by: { id: null, name: '' }, supplies: [] })
    }) as typeof fetch

    savePendingFbsAssemblyTask(token(), task)
    await expect(resumePendingFbsAssemblyTask(token(), authHeaders)).rejects.toThrow('network offline before commit')
    // Simulated reload: the next entry reads the same local record and key.
    failBeforeCommit = false
    await expect(resumePendingFbsAssemblyTask(token(), authHeaders)).resolves.toBe(true)

    expect(committed).toBe(1)
    expect(calls).toEqual([
      { body: { supply_ids: task.supplyIds, idempotency_key: task.idempotencyKey }, stored: true },
      { body: { supply_ids: task.supplyIds, idempotency_key: task.idempotencyKey }, stored: true },
    ])
    expect(readPendingFbsAssemblyTask(token())).toBeNull()
  })

  it('replays the same key after a lost committed reply and never creates a duplicate task', async () => {
    const keys: string[] = []
    let committed = false
    globalThis.fetch = (async (_input, init) => {
      const body = JSON.parse(String(init?.body)) as { idempotency_key: string }
      keys.push(body.idempotency_key)
      if (!committed) {
        committed = true
        throw new TypeError('reply lost after commit')
      }
      return json({ id: 'task-1', number: '1', created_at: '', created_by: { id: null, name: '' }, supplies: [] })
    }) as typeof fetch

    savePendingFbsAssemblyTask(token(), task)
    await expect(resumePendingFbsAssemblyTask(token(), authHeaders)).rejects.toThrow('reply lost after commit')
    await resumePendingFbsAssemblyTask(token(), authHeaders)

    expect(keys).toEqual([task.idempotencyKey, task.idempotencyKey])
    expect(readPendingFbsAssemblyTask(token())).toBeNull()
    expect(fbsPendingAssemblyTaskStorageKey(token())).not.toBe(fbsPendingAssemblyTaskStorageKey(token('ff-b', 'operator-a')))
  })
})
