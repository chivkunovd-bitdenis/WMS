import { describe, expect, it } from 'vitest'

import type { FbsOrderVerdict } from '../screens/v2/fbsApi'
import { metaStatusView } from './metaStatus'

const verdict = (
  signature: FbsOrderVerdict['signature'],
  delivery_allowed: boolean,
  reason: string | null = null,
): FbsOrderVerdict => ({ signature, tone: 'stop', reason, delivery_allowed })

const assertServerDeliveryAllowedIsReadonly = (serverVerdict: FbsOrderVerdict) => {
  // @ts-expect-error The screen must not overwrite the server's delivery decision.
  serverVerdict.delivery_allowed = false
}
void assertServerDeliveryAllowedIsReadonly

describe('metaStatusView', () => {
  it.each([
    ['WB: принято', true, 'WB: принято', 'ok'],
    ['WB: код не требуется', true, 'WB: код не требуется', 'neutral'],
    ['WB не принял', false, 'WB не принял', 'stop'],
  ] as const)('maps %s to the contract label and tone', (signature, deliveryAllowed, label, tone) => {
    expect(metaStatusView(verdict(signature, deliveryAllowed))).toMatchObject({
      label,
      tone,
      disabledReason: deliveryAllowed ? null : 'Сдача пока недоступна',
    })
  })

  it('keeps a pending WB check neutral and explains why delivery is blocked', () => {
    expect(metaStatusView(verdict('WB: проверяет', false))).toEqual({
      label: 'WB: проверяет',
      tone: 'neutral',
      reason: null,
      disabledReason: 'WB ещё не подтвердил код',
    })
  })

  it('shows the next action when WB requires a marking code', () => {
    expect(metaStatusView(verdict('WB: нужен код', false))).toEqual({
      label: 'WB: нужен код',
      tone: 'stop',
      reason: 'Пришлите ЧЗ',
      disabledReason: 'Пришлите ЧЗ',
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

  it('lets a rejection reason override an otherwise positive verdict', () => {
    expect(metaStatusView(verdict('WB: принято', true, 'invalid_code'))).toEqual({
      label: 'WB не принял',
      tone: 'stop',
      reason: 'Код маркировки не принят',
      disabledReason: 'WB не принял: Код маркировки не принят',
    })
  })

  it('fails closed when the WB verdict is missing or has an unknown signature', () => {
    const unknownVerdict = {
      signature: 'unexpected',
      tone: 'ok',
      reason: null,
      delivery_allowed: true,
    } as unknown as FbsOrderVerdict

    expect(metaStatusView(undefined)).toEqual({
      label: 'Нет ответа WB',
      tone: 'stop',
      reason: null,
      disabledReason: 'Ждём ответа Wildberries',
    })
    expect(metaStatusView(verdict('Нет ответа WB', false))).toEqual({
      label: 'Нет ответа WB',
      tone: 'stop',
      reason: null,
      disabledReason: 'Ждём ответа Wildberries',
    })
    expect(metaStatusView(unknownVerdict)).toEqual({
      label: 'Нет ответа WB',
      tone: 'stop',
      reason: null,
      disabledReason: 'Ждём ответа Wildberries',
    })
  })
})
