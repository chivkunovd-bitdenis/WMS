import { describe, expect, it } from 'vitest'
import { createFoundQueue, FoundPlaceDeferredError, type FoundPlace } from './foundQueue'

function place(scanId: string, countId = 'count-1'): FoundPlace {
  return { barcodes: ['x'], cellId: null, containerKind: null, containerId: null, scanId, countId }
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

describe('находка помнит свой документ', () => {
  it('не уходит в чужой пересчёт и не теряется, а ждёт возвращения в свой', async () => {
    // Раньше недоставленная находка уходила в тот документ, который открыт
    // сейчас: оператор возвращался в список, открывал другой черновик — и чужая
    // находка попадала туда. Потом это закрыли отказом, но находка стала просто
    // пропадать: отказ считался сетевым, четыре попытки — и очередь её
    // выбрасывала. Оператор возвращался в свой документ и спокойно проводил его
    // без отсканированного товара.
    const delivered: string[] = []
    // Какой документ открыт у оператора прямо сейчас.
    let openCountId = 'count-7'
    const queue = createFoundQueue<string>({
      send: async (p) => {
        if (p.countId !== openCountId) {
          throw new FoundPlaceDeferredError('другой документ')
        }
        delivered.push(p.scanId)
        return 'ok'
      },
      onApplied: () => undefined,
      onRejected: () => expect.unreachable('находку нельзя выбрасывать'),
      onPendingChange: () => undefined,
      isRetryable: () => true,
      delay: noWait,
    })

    // Скан сделан в своём документе, но оператор успел уйти в другой.
    openCountId = 'count-9'
    queue.push(place('scan-1', 'count-7'))
    await new Promise((r) => setTimeout(r, 0))

    expect(delivered).toEqual([])
    expect(queue.parked()).toBe(1)
    // Работа в чужом документе при этом не заблокирована.
    expect(queue.pending()).toBe(0)

    // Оператор вернулся в свой пересчёт — находка доезжает сама.
    openCountId = 'count-7'
    queue.resumeFor('count-7')
    await new Promise((r) => setTimeout(r, 0))

    expect(delivered).toEqual(['scan-1'])
    expect(queue.parked()).toBe(0)
  })
})
