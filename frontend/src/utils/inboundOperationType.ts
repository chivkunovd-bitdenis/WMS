export type InboundOperationType = 'inbound' | 'return'

export function normalizeInboundOperationType(value: unknown): InboundOperationType {
  return value === 'return' ? 'return' : 'inbound'
}

export function inboundOperationTypeLabel(value: unknown): 'Поставка' | 'Возврат' {
  return normalizeInboundOperationType(value) === 'return' ? 'Возврат' : 'Поставка'
}
