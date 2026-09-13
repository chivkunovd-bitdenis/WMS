import { describe, expect, it } from 'vitest'
import { nameLoginPayload } from './useAuth'

describe('name login payload', () => {
  it('passes the typed organization to the existing name-login endpoint', () => {
    expect(nameLoginPayload('Иван Иванов', 'password', 'tenant-a')).toEqual({ full_name: 'Иван Иванов', password: 'password', organization: 'tenant-a' })
  })
})
