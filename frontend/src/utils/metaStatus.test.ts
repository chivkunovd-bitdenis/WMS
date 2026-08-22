import { describe, expect, it } from 'vitest'

import type { FbsOrderVerdict } from '../screens/v2/fbsApi'
import { metaStatusView } from './metaStatus'

const verdict = (
  signature: FbsOrderVerdict['signature'],
  delivery_allowed: boolean,
  reason: string | null = null,
): FbsOrderVerdict => ({ signature, tone: 'stop', reason, delivery_allowed })

describe('metaStatusView', () => {
  it.each([
    ['WB: принято', true, 'WB: принято', 'ok'],
    ['WB: код не требуется', true, 'WB: код не требуется', 'neutral'],
    ['WB не принял', false, 'WB не принял', 'stop'],
    ['WB: проверяет', false, 'WB: проверяет', 'stop'],
    ['WB: нужен код', false, 'WB: нужен код', 'stop'],
    ['Нет ответа WB', false, 'Нет ответа WB', 'stop'],
  ] as const)('maps %s to the contract label and tone', (signature, deliveryAllowed, label, tone) => {
    expect(metaStatusView(verdict(signature, deliveryAllowed))).toMatchObject({
      label,
      tone,
      disabledReason: deliveryAllowed ? null : 'Сдача пока недоступна',
    })
  })

  it('translates the real WB uinBadStatus rejection without exposing its technical code', () => {
    expect(metaStatusView(verdict('WB: принято', false, 'uinBadStatus'))).toEqual({
      label: 'WB не принял',
      tone: 'stop',
      reason: 'неверный статус УИН',
      disabledReason: 'WB не принял: неверный статус УИН',
    })
  })

  it('keeps an unknown WB reason visible as a safe fallback', () => {
    expect(metaStatusView(verdict('WB не принял', false, 'otherWbReason'))).toMatchObject({
      label: 'WB не принял',
      tone: 'stop',
      reason: 'otherWbReason',
    })
  })
})
