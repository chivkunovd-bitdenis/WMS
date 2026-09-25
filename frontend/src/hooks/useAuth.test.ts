import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  isCurrentSessionToken,
  loadSessionProfile,
  nameLoginPayload,
  portalRoleMismatchMessage,
  sessionChangeFromStorage,
  type Me,
} from './useAuth'

describe('name login payload', () => {
  it('passes the typed organization to the existing name-login endpoint', () => {
    expect(nameLoginPayload('Иван Иванов', 'password', 'tenant-a')).toEqual({ full_name: 'Иван Иванов', password: 'password', organization: 'tenant-a' })
  })
})

// WMS-488: токен портала лежит в общем localStorage, поэтому вход и выход в
// одной вкладке меняют сессию всех остальных. Вкладка, которая этого не
// заметила, продолжала показывать каталог прежнего селлера.
describe('cross-tab session change', () => {
  it('adopts the seller token saved by another tab', () => {
    expect(
      sessionChangeFromStorage({
        eventKey: 'wms_token_seller',
        portal: 'seller',
        sessionToken: 'token-goryachkina',
        storedToken: 'token-chulkov',
      }),
    ).toEqual({ changed: true, token: 'token-chulkov' })
  })

  it('drops the session when another tab logged out', () => {
    expect(
      sessionChangeFromStorage({
        eventKey: 'wms_token_seller',
        portal: 'seller',
        sessionToken: 'token-goryachkina',
        storedToken: null,
      }),
    ).toEqual({ changed: true, token: null })
  })

  it('drops the session when storage was cleared as a whole', () => {
    expect(
      sessionChangeFromStorage({
        eventKey: null,
        portal: 'seller',
        sessionToken: 'token-goryachkina',
        storedToken: null,
      }),
    ).toEqual({ changed: true, token: null })
  })

  it('keeps the seller session when the fulfillment tab signs in', () => {
    expect(
      sessionChangeFromStorage({
        eventKey: 'wms_token_ff',
        portal: 'seller',
        sessionToken: 'token-goryachkina',
        storedToken: 'token-goryachkina',
      }),
    ).toEqual({ changed: false })
  })

  it('keeps the fulfillment session with its own catalog access when a seller tab signs in', () => {
    expect(
      sessionChangeFromStorage({
        eventKey: 'wms_token_seller',
        portal: 'fulfillment',
        sessionToken: 'token-avpack-ff',
        storedToken: 'token-avpack-ff',
      }),
    ).toEqual({ changed: false })
  })

  it('does not reload when the stored token is the one already in use', () => {
    expect(
      sessionChangeFromStorage({
        eventKey: 'wms_token_seller',
        portal: 'seller',
        sessionToken: 'token-goryachkina',
        storedToken: 'token-goryachkina',
      }),
    ).toEqual({ changed: false })
  })
})

function meFixture(sellerName: string): Me {
  return {
    id: `user-${sellerName}`,
    email: `${sellerName}@example.test`,
    display_name: sellerName,
    organization_name: 'AVpack',
    role: 'fulfillment_seller',
    seller_id: `seller-${sellerName}`,
    seller_name: sellerName,
  }
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

// WMS-488: ответ /auth/me с прежним токеном приходил уже после того, как
// вкладка перешла на другого селлера, и возвращал на экран прежний профиль.
describe('late /auth/me response', () => {
  it('applies the profile while the session token is unchanged', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, meFixture('goryachkina'))),
    )

    const result = await loadSessionProfile('token-goryachkina', (t) => t === 'token-goryachkina')

    expect(result).toEqual({ outcome: 'loaded', me: meFixture('goryachkina') })
  })

  it('discards a profile that arrives after the tab switched to another seller', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(200, meFixture('goryachkina'))),
    )
    let sessionToken = 'token-goryachkina'

    const pending = loadSessionProfile('token-goryachkina', (t) => t === sessionToken)
    sessionToken = 'token-chulkov'

    expect(await pending).toEqual({ outcome: 'stale' })
  })

  it('keeps the new session when the previous token answers 401 late', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(401, { detail: 'invalid_token' })),
    )
    let sessionToken = 'token-goryachkina'

    const pending = loadSessionProfile('token-goryachkina', (t) => t === sessionToken)
    sessionToken = 'token-chulkov'

    expect(await pending).toEqual({ outcome: 'stale' })
  })

  it('keeps the new session when the previous token fails on the network late', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network down')
      }),
    )
    let sessionToken = 'token-goryachkina'

    const pending = loadSessionProfile('token-goryachkina', (t) => t === sessionToken)
    sessionToken = 'token-chulkov'

    expect(await pending).toEqual({ outcome: 'stale' })
  })

  it('reports 401 of the current session so the tab asks to sign in again', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(401, { detail: 'invalid_token' })),
    )

    const result = await loadSessionProfile('token-goryachkina', () => true)

    expect(result.outcome).toBe('unauthorized')
  })
})

// WMS-488, воспроизведено в Chrome на данных AVpack: соседняя вкладка уже
// записала токен второго селлера в localStorage, но событие storage до нашей
// вкладки ещё не дошло. Вкладка помнит прежний токен, поэтому её собственной
// памяти мало: по ней чужой ответ выглядит своим и стирал чужую сессию.
describe('response that outruns the storage event', () => {
  const tab = (sessionToken: string | null, storedToken: string | null) =>
    (candidate: string) => isCurrentSessionToken({ candidate, sessionToken, storedToken })

  it('calls a 401 of the previous seller stale while storage already holds the new one', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, { detail: 'invalid_token' })))

    const result = await loadSessionProfile(
      'token-goryachkina',
      tab('token-goryachkina', 'token-chulkov'),
    )

    expect(result).toEqual({ outcome: 'stale' })
  })

  it('calls a profile with a portal-unsuitable role stale in the same window', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, {
      ...meFixture('goryachkina'), role: 'fulfillment_admin',
    })))

    const result = await loadSessionProfile(
      'token-goryachkina',
      tab('token-goryachkina', 'token-chulkov'),
    )

    expect(result).toEqual({ outcome: 'stale' })
  })

  it('still demands a new sign-in when the tab and storage agree on the failing token', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, { detail: 'invalid_token' })))

    const result = await loadSessionProfile(
      'token-goryachkina',
      tab('token-goryachkina', 'token-goryachkina'),
    )

    expect(result.outcome).toBe('unauthorized')
  })

  it('treats a logout in the neighbouring tab as somebody else’s session too', () => {
    expect(isCurrentSessionToken({
      candidate: 'token-goryachkina', sessionToken: 'token-goryachkina', storedToken: null,
    })).toBe(false)
  })
})

// Роль проверяется у владельца профиля, поэтому решение вынесено в чистую
// функцию: сессию закрывает только собственная неподходящая роль.
describe('portal role check', () => {
  it('turns away a fulfillment admin who opened the seller portal', () => {
    expect(portalRoleMismatchMessage('seller', 'fulfillment_admin')).toContain('только для селлера')
  })

  it('lets a seller work in the seller portal', () => {
    expect(portalRoleMismatchMessage('seller', 'fulfillment_seller')).toBeNull()
  })

  it('turns away a seller who opened the fulfillment portal', () => {
    expect(portalRoleMismatchMessage('fulfillment', 'fulfillment_seller'))
      .toContain('для сотрудников фулфилмента')
  })

  it('lets a fulfillment admin work in the fulfillment portal', () => {
    expect(portalRoleMismatchMessage('fulfillment', 'fulfillment_admin')).toBeNull()
  })
})
