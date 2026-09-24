import { describe, expect, it } from 'vitest'

import type {
  WithdrawalOperation,
  WithdrawalOperationItem,
  WithdrawalRow,
} from './sellerKizWithdrawalApi'
import {
  applyOperationItemsToRows,
  getOrCreateClientRequest,
  isRowInFlight,
  isRowSelectable,
  isWithdrawalProductionSubmitBlocked,
  isTerminalWithdrawalOperation,
  parsePendingRequest,
  sha256Base64Payload,
} from './sellerKizWithdrawalState'

const operation = (state: string): WithdrawalOperation => ({
  operation_id: 'operation-id',
  state,
  attempt: 1,
  integration_gate: null,
  reauth_required: false,
  certificate_thumbprint: null,
  auth_challenge: null,
  documents: [],
  auth_error: null,
  items: [],
})

const row = (overrides: Partial<WithdrawalRow>): WithdrawalRow => ({
  row_id: 'row-1',
  product_id: null,
  delivered_at: '2026-09-24T09:30:00Z',
  wb_order_id: '1',
  sku: 'sku',
  product_name: 'product',
  cis: '0104601234567890211',
  status: 'not_withdrawn',
  error: null,
  operation_id: null,
  ...overrides,
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

  it('recognises the four durable non-terminal, in-flight and terminal states', () => {
    expect(isTerminalWithdrawalOperation(operation('reconciling'))).toBe(false)
    expect(isTerminalWithdrawalOperation(operation('partial_failed'))).toBe(true)
    expect(isTerminalWithdrawalOperation(operation('succeeded'))).toBe(true)
  })

  it('keeps new production submit fail-closed but permits certificate reauth for read-only recovery', () => {
    const gated = {
      ...operation('auth_pending'),
      integration_gate: 'WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED' as const,
    }
    expect(isWithdrawalProductionSubmitBlocked(gated)).toBe(true)
    expect(isWithdrawalProductionSubmitBlocked({
      ...gated,
      state: 'reconciling',
      reauth_required: true,
      certificate_thumbprint: 'AABB',
    })).toBe(false)
  })

  it('hashes the exact bytes represented by base64', async () => {
    expect(await sha256Base64Payload('aGVsbG8=')).toBe(
      '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
    )
  })

  it('lets the operator retry only fresh or terminal-error rows', () => {
    expect(isRowSelectable(row({ status: 'not_withdrawn' }))).toBe(true)
    expect(isRowSelectable(row({ status: 'error' }))).toBe(true)
    expect(isRowSelectable(row({ status: 'withdrawn' }))).toBe(false)
    expect(isRowSelectable(row({ status: 'transferring' }))).toBe(false)
    expect(isRowSelectable(row({ status: 'awaiting_crpt' }))).toBe(false)
  })

  it('copies the accepted-signature per-KIZ projection without rewinding terminal items', () => {
    // Mixed operation: succeeded prior-attempt, failed preflight and freshly signed
    // pending KIZ share the same operation.items array. The seed must preserve
    // real terminal state and only tag the pending row as transferring — the
    // status the backend already projects for a signed pending item.
    const rows: WithdrawalRow[] = [
      row({ row_id: 'row-succeeded', status: 'withdrawn' }),
      row({
        row_id: 'row-failed',
        status: 'error',
        error: { source: 'crpt', code: 'cost_missing', message: 'нет цены' },
      }),
      row({ row_id: 'row-pending', status: 'not_withdrawn' }),
      row({ row_id: 'row-unrelated', status: 'not_withdrawn' }),
    ]
    const items: WithdrawalOperationItem[] = [
      { row_id: 'row-succeeded', cis: 'a', wb_order_id: '1', status: 'withdrawn', error: null },
      {
        row_id: 'row-failed',
        cis: 'b',
        wb_order_id: '2',
        status: 'error',
        error: { source: 'crpt', code: 'cost_missing', message: 'нет цены' },
      },
      { row_id: 'row-pending', cis: 'c', wb_order_id: '3', status: 'transferring', error: null },
    ]
    const merged = applyOperationItemsToRows(rows, items, 'op-42')
    expect(merged.map((r) => [r.row_id, r.status, r.operation_id])).toEqual([
      ['row-succeeded', 'withdrawn', 'op-42'],
      ['row-failed', 'error', 'op-42'],
      ['row-pending', 'transferring', 'op-42'],
      ['row-unrelated', 'not_withdrawn', null],
    ])
    expect(merged[1].error).toEqual({ source: 'crpt', code: 'cost_missing', message: 'нет цены' })
  })

  it('opens the in-flight row for the same-operation reauth path but not for a fresh submit', () => {
    // WMS-517 BR14: after an uncertain create the worker only reconciles via GET.
    // The row is selectable to route the user through same-cert reauth, never to
    // POST a second document. `resume_required` is the only signal that flips it.
    const stuck = row({
      status: 'awaiting_crpt',
      operation_id: 'operation-1',
      resume_required: true,
    })
    expect(isRowSelectable(stuck)).toBe(true)
    expect(isRowSelectable({ ...stuck, resume_required: false })).toBe(false)
    expect(isRowInFlight(stuck)).toBe(true)
  })
})
