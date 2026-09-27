import type {
  WithdrawalOperation,
  WithdrawalOperationItem,
  WithdrawalRow,
} from './sellerKizWithdrawalApi'

// The submit response is the authoritative per-KIZ projection — an operation
// carries pending, failed-preflight and succeeded prior-attempt items in the
// same array. Copy each item's real status/error onto its row and stamp the
// operation_id; rows the operation does not touch are left untouched.
export const applyOperationItemsToRows = (
  rows: WithdrawalRow[],
  items: WithdrawalOperationItem[],
  operationId: string,
): WithdrawalRow[] => {
  const byRowId = new Map(items.map((item) => [item.row_id, item] as const))
  return rows.map((row) => {
    const item = byRowId.get(row.row_id)
    if (!item) return row
    return { ...row, status: item.status, error: item.error, operation_id: operationId }
  })
}

const TERMINAL_OPERATION_STATES = new Set(['succeeded', 'partial_failed', 'failed', 'cancelled'])
const IN_FLIGHT_ROW_STATUSES = new Set(['transferring', 'awaiting_crpt'])
const SELECTABLE_ROW_STATUSES = new Set(['not_withdrawn', 'error'])

export const isTerminalWithdrawalOperation = (operation: WithdrawalOperation): boolean =>
  TERMINAL_OPERATION_STATES.has(operation.state)

export const isWithdrawalProductionSubmitBlocked = (operation: WithdrawalOperation): boolean =>
  operation.integration_gate === 'WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED' &&
  !operation.reauth_required

export const failedWithdrawalItems = (operation: WithdrawalOperation): WithdrawalOperationItem[] =>
  operation.items.filter((item) => item.status === 'error')

export const isRowInFlight = (row: WithdrawalRow): boolean =>
  IN_FLIGHT_ROW_STATUSES.has(row.status)

// Fresh and terminal-error rows are eligible for a new/retry submit. An in-flight
// row is only eligible when the same operation needs same-cert reauth (BR14): that
// path is GET-only reconciliation, it never creates a second document.
export const isRowSelectable = (row: WithdrawalRow): boolean =>
  SELECTABLE_ROW_STATUSES.has(row.status) || row.resume_required === true

export const compactKiz = (value: string): string =>
  value.length <= 24 ? value : `${value.slice(0, 18)}…${value.slice(-4)}`

export const normalizeThumbprint = (value: string): string =>
  value.replace(/\s+/g, '').toUpperCase()

const decodeBase64 = (payloadBase64: string): Uint8Array => {
  const normalized = payloadBase64.replace(/[\r\n]/g, '')
  const decoded = globalThis.atob(normalized)
  const bytes = new Uint8Array(decoded.length)
  for (let index = 0; index < decoded.length; index += 1) bytes[index] = decoded.charCodeAt(index)
  return bytes
}

export const sha256Base64Payload = async (payloadBase64: string): Promise<string> => {
  const bytes = decodeBase64(payloadBase64)
  const digest = await globalThis.crypto.subtle.digest('SHA-256', Uint8Array.from(bytes).buffer)
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

type PendingRequest = {
  rowIds: string[]
  clientRequestId: string
}

export const sameSelection = (left: string[], right: string[]): boolean => {
  if (left.length !== right.length) return false
  const sortedLeft = [...left].sort()
  const sortedRight = [...right].sort()
  return sortedLeft.every((value, index) => value === sortedRight[index])
}

export const getOrCreateClientRequest = (
  rowIds: string[],
  pending: PendingRequest | null,
  createUuid: () => string,
): PendingRequest => {
  if (pending && sameSelection(pending.rowIds, rowIds)) return pending
  return { rowIds: [...rowIds].sort(), clientRequestId: createUuid() }
}

export const parsePendingRequest = (value: string | null): PendingRequest | null => {
  if (!value) return null
  try {
    const parsed = JSON.parse(value) as Partial<PendingRequest>
    if (
      !Array.isArray(parsed.rowIds) ||
      parsed.rowIds.some((rowId) => typeof rowId !== 'string') ||
      typeof parsed.clientRequestId !== 'string'
    ) {
      return null
    }
    return { rowIds: parsed.rowIds, clientRequestId: parsed.clientRequestId }
  } catch {
    return null
  }
}
