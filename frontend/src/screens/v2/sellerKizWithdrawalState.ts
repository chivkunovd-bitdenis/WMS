import type { WithdrawalOperation, WithdrawalOperationItem } from './sellerKizWithdrawalApi'

const TERMINAL_OPERATION_STATES = new Set(['succeeded', 'partial_failed', 'failed', 'cancelled'])
const POLLING_OPERATION_STATES = new Set(['submitting', 'submitted', 'reconciling'])

export const isTerminalWithdrawalOperation = (operation: WithdrawalOperation): boolean =>
  TERMINAL_OPERATION_STATES.has(operation.state)

export const shouldPollWithdrawalOperation = (operation: WithdrawalOperation): boolean =>
  POLLING_OPERATION_STATES.has(operation.state)

export const failedWithdrawalItems = (operation: WithdrawalOperation): WithdrawalOperationItem[] =>
  operation.items.filter((item) => item.status === 'error')

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
