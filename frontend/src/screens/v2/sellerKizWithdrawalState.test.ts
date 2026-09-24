import { describe, expect, it } from 'vitest'

import type { WithdrawalOperation } from './sellerKizWithdrawalApi'
import {
  getOrCreateClientRequest,
  isTerminalWithdrawalOperation,
  parsePendingRequest,
  sha256Base64Payload,
  shouldPollWithdrawalOperation,
} from './sellerKizWithdrawalState'

const operation = (state: string): WithdrawalOperation => ({
  operation_id: 'operation-id',
  state,
  attempt: 1,
  integration_gate: null,
  auth_challenge: null,
  documents: [],
  auth_error: null,
  items: [],
})

describe('seller KIZ withdrawal state', () => {
  it('reuses the request id only for the exact same selection', () => {
    const pending = { rowIds: ['b', 'a'], clientRequestId: 'stable-id' }
    expect(getOrCreateClientRequest(['a', 'b'], pending, () => 'new-id')).toEqual(pending)
    expect(getOrCreateClientRequest(['a', 'c'], pending, () => 'new-id')).toEqual({
      rowIds: ['a', 'c'],
      clientRequestId: 'new-id',
    })
  })

  it('rejects malformed persisted requests', () => {
    expect(parsePendingRequest('{"rowIds":[1],"clientRequestId":"id"}')).toBeNull()
    expect(parsePendingRequest('not-json')).toBeNull()
  })

  it('separates durable polling states from terminal states', () => {
    expect(shouldPollWithdrawalOperation(operation('reconciling'))).toBe(true)
    expect(isTerminalWithdrawalOperation(operation('reconciling'))).toBe(false)
    expect(shouldPollWithdrawalOperation(operation('documents_pending_signature'))).toBe(false)
    expect(isTerminalWithdrawalOperation(operation('partial_failed'))).toBe(true)
    expect(isTerminalWithdrawalOperation(operation('succeeded'))).toBe(true)
  })

  it('hashes the exact bytes represented by base64', async () => {
    expect(await sha256Base64Payload('aGVsbG8=')).toBe(
      '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
    )
  })
})
