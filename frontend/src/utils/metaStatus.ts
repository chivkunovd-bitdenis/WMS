import type { StatusTone } from '../ui-kit'
import type { FbsOrderVerdict } from '../screens/v2/fbsApi'

const REASON_LABELS: Record<string, string> = {
  missing_code: 'Не найден обязательный код маркировки',
  code_required: 'Нужен обязательный код маркировки',
  invalid_code: 'Код маркировки не принят',
  code_not_found: 'WB не нашёл код маркировки',
  already_used: 'Код маркировки уже использован',
  rejected: 'WB отклонил код маркировки',
}

export type MetaStatusView = {
  label: 'WB: принято' | 'WB: код не требуется' | 'WB не принял' | 'WB: проверяет' | 'WB: нужен код' | 'Нет ответа WB'
  tone: StatusTone
  reason: string | null
  disabledReason: string | null
}

function reasonLabel(reason: string | null): string | null {
  if (!reason) return null
  return REASON_LABELS[reason.trim().toLowerCase()] ?? reason
}

/** Maps the server verdict to the fixed operator-facing vocabulary. */
export function metaStatusView(verdict: FbsOrderVerdict | null | undefined): MetaStatusView {
  if (!verdict) {
    return { label: 'Нет ответа WB', tone: 'stop', reason: null, disabledReason: 'Сдача пока недоступна' }
  }

  const reason = reasonLabel(verdict.reason)
  if (reason) {
    return { label: 'WB не принял', tone: 'stop', reason, disabledReason: `WB не принял: ${reason}` }
  }

  switch (verdict.signature) {
    case 'WB: принято':
      return { label: 'WB: принято', tone: 'ok', reason: null, disabledReason: verdict.delivery_allowed ? null : 'Сдача пока недоступна' }
    case 'WB: код не требуется':
      return { label: 'WB: код не требуется', tone: 'neutral', reason: null, disabledReason: verdict.delivery_allowed ? null : 'Сдача пока недоступна' }
    case 'WB: проверяет':
      return { label: 'WB: проверяет', tone: 'stop', reason: null, disabledReason: 'Сдача пока недоступна' }
    case 'WB: нужен код':
      return { label: 'WB: нужен код', tone: 'stop', reason: null, disabledReason: 'Сдача пока недоступна' }
    case 'WB не принял':
      return { label: 'WB не принял', tone: 'stop', reason: null, disabledReason: 'Сдача пока недоступна' }
    default:
      return { label: 'Нет ответа WB', tone: 'stop', reason: null, disabledReason: 'Сдача пока недоступна' }
  }
}
