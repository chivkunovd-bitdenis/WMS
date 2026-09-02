import { describe, expect, it } from 'vitest'
import { createFoundQueue, type FoundPlace } from './foundQueue'

function place(scanId: string): FoundPlace {
  return { barcodes: ['x'], cellId: null, containerKind: null, containerId: null, scanId }
}

const noWait = () => Promise.resolve()

describe('очередь находок', () => {
  it('обрыв связи повторяется тем же идентификатором скана', async () => {
    // Ровно тот случай, ради которого очередь и заведена: сервер уже записал,
    // а ответ потерялся. Повторить обязаны мы и тем же скан-идентификатором —
    // если это сделает человек, скан будет другим, и на остатке станет двойка.
    const sent: string[] = []
    let fail = 2
    const applied: string[] = []
    const queue = createFoundQueue<string>({
      send: async (p) => {
        sent.push(p.scanId)
        if (fail-- > 0) throw new TypeError('Failed to fetch')
        return 'ok'
      },
      onApplied: (_r, p) => applied.push(p.scanId),
      onRejected: () => expect.unreachable('сетевой обрыв не должен доходить до оператора'),
      onPendingChange: () => undefined,
      isRetryable: (err) => err instanceof TypeError,
      delay: noWait,
    })

    queue.push(place('scan-1'))
    await new Promise((r) => setTimeout(r, 0))

    expect(sent).toEqual(['scan-1', 'scan-1', 'scan-1'])
    expect(applied).toEqual(['scan-1'])
  })

  it('сканы уходят строго по одному и в порядке', async () => {
    // Раньше запросы летели независимо, ответы возвращались вперемешку, и
    // поздний ответ со старым документом стирал с экрана строку от раннего.
    const order: string[] = []
    const queue = createFoundQueue<string>({
      send: async (p) => {
        order.push(`старт:${p.scanId}`)
        await new Promise((r) => setTimeout(r, p.scanId === 'a' ? 20 : 1))
        order.push(`конец:${p.scanId}`)
        return 'ok'
      },
      onApplied: () => undefined,
      onRejected: () => undefined,
      onPendingChange: () => undefined,
      isRetryable: () => false,
      delay: noWait,
    })

    queue.push(place('a'))
    queue.push(place('b'))
    await new Promise((r) => setTimeout(r, 60))

    expect(order).toEqual(['старт:a', 'конец:a', 'старт:b', 'конец:b'])
  })

  it('отказ сервера не повторяется, а показывается человеку', async () => {
    const rejected: string[] = []
    let calls = 0
    const queue = createFoundQueue<string>({
      send: async () => {
        calls += 1
        throw new Error('Товар не найден')
      },
      onApplied: () => undefined,
      onRejected: (_e, p) => rejected.push(p.scanId),
      onPendingChange: () => undefined,
      isRetryable: () => false,
      delay: noWait,
    })

    queue.push(place('scan-9'))
    await new Promise((r) => setTimeout(r, 0))

    expect(calls).toBe(1)
    expect(rejected).toEqual(['scan-9'])
  })

  it('очередь честно говорит, сколько сканов ещё не доставлено', async () => {
    const seen: number[] = []
    const queue = createFoundQueue<string>({
      send: async () => {
        await new Promise((r) => setTimeout(r, 5))
        return 'ok'
      },
      onApplied: () => undefined,
      onRejected: () => undefined,
      onPendingChange: (n) => seen.push(n),
      isRetryable: () => false,
      delay: noWait,
    })

    queue.push(place('a'))
    queue.push(place('b'))
    await new Promise((r) => setTimeout(r, 40))

    expect(Math.max(...seen)).toBeGreaterThanOrEqual(2)
    expect(seen[seen.length - 1]).toBe(0)
  })
})
