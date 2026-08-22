import type { StatusTone } from '../ui-kit'
import type { FbsOrderVerdict, FbsOrderVerdictSignature } from '../screens/v2/fbsApi'

const REASON_LABELS: Record<string, string> = {
  uinbadstatus: 'неверный статус УИН',
  missing_code: 'Не найден обязательный код маркировки',
  code_required: 'Нужен обязательный код маркировки',
  invalid_code: 'Код маркировки не принят',
  code_not_found: 'WB не нашёл код маркировки',
  already_used: 'Код маркировки уже использован',
  rejected: 'WB отклонил код маркировки',
}

export type MetaStatusLabel = FbsOrderVerdictSignature

export type MetaStatusView = {
  label: MetaStatusLabel
  tone: StatusTone
  reason: string | null
  disabledReason: string | null
}

function reasonLabel(reason: string | null): string | null {
  if (typeof reason !== 'string') return null
  const normalized = reason.trim()
  if (!normalized) return null
  return REASON_LABELS[normalized.toLowerCase()] ?? normalized
}

const BLOCKED_REASON = 'Сдача пока недоступна'

function blockedView(
  label: MetaStatusLabel,
  reason: string | null = null,
  disabledReason: string = BLOCKED_REASON,
): MetaStatusView {
  return { label, tone: 'stop', reason, disabledReason }
}

/** Maps the server verdict to the fixed operator-facing vocabulary. */
export function metaStatusView(verdict: FbsOrderVerdict | null | undefined): MetaStatusView {
  if (!verdict) {
    return blockedView('Нет ответа WB')
  }

  const knownSignatures: FbsOrderVerdictSignature[] = [
    'WB: принято',
    'WB: код не требуется',
    'WB не принял',
    'WB: проверяет',
    'WB: нужен код',
    'Нет ответа WB',
  ]
  if (!knownSignatures.includes(verdict.signature)) return blockedView('Нет ответа WB')

  const reason = reasonLabel(verdict.reason)
  if (reason) {
    return blockedView('WB не принял', reason, `WB не принял: ${reason}`)
  }

  switch (verdict.signature) {
    case 'WB: принято':
      return {
        label: 'WB: принято',
        tone: 'ok',
        reason: null,
        disabledReason: verdict.delivery_allowed ? null : BLOCKED_REASON,
      }
    case 'WB: код не требуется':
      return {
        label: 'WB: код не требуется',
        tone: 'neutral',
        reason: null,
        disabledReason: verdict.delivery_allowed ? null : BLOCKED_REASON,
      }
    case 'WB: проверяет':
      return blockedView('WB: проверяет')
    case 'WB: нужен код':
      return blockedView('WB: нужен код')
    case 'WB не принял':
      return blockedView('WB не принял')
    case 'Нет ответа WB':
      return blockedView('Нет ответа WB')
    default:
      return blockedView('Нет ответа WB')
  }
}
