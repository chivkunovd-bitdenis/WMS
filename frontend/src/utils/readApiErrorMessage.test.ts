import { describe, expect, it } from 'vitest'
import { insufficientAvailableMessage, readApiErrorMessage } from './readApiErrorMessage'

// WMS-530 R12: нехватка называется одними словами — «доступно», без склада,
// ячейки, FBO и FBS-пула.

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('WMS-530 R12 сообщения о нехватке', () => {
  it('полный текст сервера показывается как есть', async () => {
    const message =
      'Недостаточно доступного остатка: Туфли (6720-5A/29). Доступно 9 шт, пытаются 10 шт.'
    const res = jsonResponse(422, {
      detail: { code: 'insufficient_available', available: 9, attempted: 10, message },
    })
    expect(await readApiErrorMessage(res)).toBe(message)
  })

  it('ответ одним кодом не упоминает ячейку, FBO и FBS-пул', async () => {
    for (const code of ['insufficient_available', 'insufficient_free_fbo']) {
      const text = await readApiErrorMessage(jsonResponse(422, { detail: code }))
      expect(text).toBe('Недостаточно доступного остатка.')
    }
  })

  it('проверка на экране пишет тот же текст, что сервер', () => {
    expect(
      insufficientAvailableMessage({ name: 'Туфли', sku: '6720-5A/29' }, 9, 10),
    ).toBe('Недостаточно доступного остатка: Туфли (6720-5A/29). Доступно 9 шт, пытаются 10 шт.')
    // Доступно меньше нуля для проверок — ноль (WMS-530 R3).
    expect(insufficientAvailableMessage({ name: 'Туфли', sku: 'Туфли' }, -2, 1)).toBe(
      'Недостаточно доступного остатка: Туфли. Доступно 0 шт, пытаются 1 шт.',
    )
  })
})
