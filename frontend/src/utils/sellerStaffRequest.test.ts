import { afterEach, describe, expect, it, vi } from 'vitest'
import { sellerStaffError, sellerStaffRequest, type SellerStaffAction } from './sellerStaffRequest'

afterEach(() => vi.unstubAllGlobals())

describe('seller staff recoverable failures', () => {
  const actions: SellerStaffAction[] = ['create', 'invite', 'profile']
  const expected = {
    create: 'Не удалось добавить сотрудника. Обновите список и попробуйте ещё раз.',
    invite: 'Не удалось отправить приглашение. Попробуйте ещё раз.',
    profile: 'Не удалось сохранить данные сотрудника. Попробуйте ещё раз.',
  }
  it.each(actions)('translates network exceptions for %s and permits retry with unchanged data', async action => {
    const body = JSON.stringify({ full_name: 'Иван', email: 'ivan@example.com' })
    const request = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch secret internals'))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', request)
    const init = { method: 'POST', body }
    const error = await sellerStaffRequest('/staff', init, action).catch(error => error)
    expect(sellerStaffError(error, action)).toBe(expected[action as keyof typeof expected])
    expect((await sellerStaffRequest('/staff', init, action)).status).toBe(204)
    expect(request.mock.calls[0]).toEqual(request.mock.calls[1])
    expect(init.body).toBe(body)
  })
  it.each(actions.flatMap(action => [500, 422].map(status => ({ action, status }))))(
    'hides unknown $status response for $action', async ({ action, status }) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
        detail: status === 500 ? 'private backend traceback' : [{ loc: ['body', 'email'], msg: 'unrecognized internal validation' }],
      }), { status })))
      const error = await sellerStaffRequest('/staff', {}, action).catch(error => error)
      expect(sellerStaffError(error, action)).toBe(expected[action as keyof typeof expected])
    },
  )
  it('keeps the actionable duplicate message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'email_taken' }), { status: 409 })))
    const error = await sellerStaffRequest('/staff', {}, 'create').catch(error => error)
    expect(sellerStaffError(error, 'create')).toBe('Этот email уже используется')
    expect(sellerStaffError(new Error('raw exception'), 'profile')).toBe(expected.profile)
  })
})
