// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { CryptoProError } from './cryptoProCades'
import { loadCryptoProBrowserPlugin } from './loadCryptoProBrowserPlugin'

type PluginWindow = Window & { cadesplugin?: unknown }
afterEach(() => {
  delete (window as PluginWindow).cadesplugin
  document.getElementById('wms-cryptopro-cades-api')?.remove()
})

describe('WMS-517 incident: native browser plugin rejection', () => {
  it.each(['Native messaging host not found', undefined, new Error('native host denied')])(
    'maps a raw native rejection to a useful CryptoPro error (%s)', async (reason) => {
      ;(window as PluginWindow).cadesplugin = { then: (_resolve: unknown, reject: (error: unknown) => void) => reject(reason) }
      await expect(loadCryptoProBrowserPlugin(100)).rejects.toBeInstanceOf(CryptoProError)
      await expect(loadCryptoProBrowserPlugin(100)).rejects.toMatchObject({
        code: 'plugin_unavailable',
        message: 'КриптоПро недоступен. Проверьте расширение и локальный сервис.',
      })
    },
  )
  it('normalizes rejection after script.onload too', async () => {
    const loading = loadCryptoProBrowserPlugin(100)
    ;(window as PluginWindow).cadesplugin = { then: (_resolve: unknown, reject: (error: unknown) => void) => reject(undefined) }
    document.getElementById('wms-cryptopro-cades-api')!.dispatchEvent(new Event('load'))
    await expect(loading).rejects.toMatchObject({ code: 'plugin_unavailable' })
  })
})

describe('WMS-517 incident: readiness recovery and preserved typed errors (IC9)', () => {
  it('normalizes a synchronous native then exception', async () => {
    ;(window as PluginWindow).cadesplugin = { then: () => { throw new Error('native bridge failed') } }
    await expect(loadCryptoProBrowserPlugin(100)).rejects.toMatchObject({ code: 'plugin_unavailable' })
  })
  it('keeps a typed CryptoPro runtime error', async () => {
    const reason = new CryptoProError('csp_missing')
    ;(window as PluginWindow).cadesplugin = { then: (_resolve: unknown, reject: (error: unknown) => void) => reject(reason) }
    await expect(loadCryptoProBrowserPlugin(100)).rejects.toBe(reason)
  })
  it('a failed attempt does not poison a later ready runtime', async () => {
    ;(window as PluginWindow).cadesplugin = { then: (_resolve: unknown, reject: (error: unknown) => void) => reject(undefined) }
    await loadCryptoProBrowserPlugin(100).catch(() => undefined)
    ;(window as PluginWindow).cadesplugin = { then: (resolve: () => void) => resolve() }
    await expect(loadCryptoProBrowserPlugin(100)).resolves.toBeUndefined()
  })
})
