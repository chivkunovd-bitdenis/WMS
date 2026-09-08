import { describe, expect, it } from 'vitest'
import { isInboundMarkingScan, inboundMarkingNeedsAttention, inboundMarkingStatusLabel, type InboundMarkingCode } from './inboundMarkingCodes'
import { createSerialScanQueue } from './inboundReceivingRuntime'

describe('receiving product and KIZ scans', () => {
  it.each(['4601234567890', 'P139-24/40', '0104601234567890'])('keeps product %s on quantity path', (code) => {
    expect(isInboundMarkingScan(code)).toBe(false)
  })
  it.each(['010460123456789021serial\x1d91abcd', ']d2010460123456789021serial', '(01)04601234567890(21)serial', 'damaged\x1d91abcd'])('routes %s only to marking validation', (code) => {
    expect(isInboundMarkingScan(code)).toBe(true)
  })
  it('waits for product quantity response before attaching following KIZ; KIZ does not increment', async () => {
    const queue = createSerialScanQueue()
    let quantity = 0
    let lastProduct: string | null = null
    let release!: () => void
    const request = new Promise<void>((resolve) => { release = resolve })
    const attachments: string[] = []
    const product = queue(async () => { await request; quantity += 1; lastProduct = 'product-a' })
    const kiz = queue(async () => { if (lastProduct) attachments.push(lastProduct) })
    const repeat = queue(async () => { quantity += 1; lastProduct = 'product-a' })
    expect(attachments).toEqual([])
    release()
    await Promise.all([product, kiz, repeat])
    expect(quantity).toBe(2)
    expect(attachments).toEqual(['product-a'])
  })
  it('does not label pending or unavailable codes as introduced', () => {
    expect(inboundMarkingStatusLabel('pending')).toBe('Ожидает проверки')
    expect(inboundMarkingStatusLabel('unavailable')).toBe('Не удалось проверить')
    expect(inboundMarkingNeedsAttention({ cz_status: 'pending' } as InboundMarkingCode)).toBe(false)
    expect(inboundMarkingNeedsAttention({ cz_status: 'unavailable' } as InboundMarkingCode)).toBe(true)
  })
})
