import { CryptoProError } from './cryptoProCades'

const SCRIPT_ID = 'wms-cryptopro-cades-api'
const SCRIPT_SRC = '/vendor/cryptopro/cadesplugin_api.js'

type CryptoProWindow = Window & { cadesplugin?: unknown }

let pendingLoad: Promise<void> | null = null

export const loadCryptoProBrowserPlugin = async (): Promise<void> => {
  if (typeof window === 'undefined') throw new CryptoProError('plugin_script_missing')
  if ((window as CryptoProWindow).cadesplugin !== undefined) return
  if (pendingLoad) return pendingLoad

  pendingLoad = new Promise<void>((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null
    const script = existing ?? document.createElement('script')
    const onLoad = () => resolve()
    const onError = () => reject(new CryptoProError('plugin_script_missing'))

    script.addEventListener('load', onLoad, { once: true })
    script.addEventListener('error', onError, { once: true })
    if (!existing) {
      script.id = SCRIPT_ID
      script.src = SCRIPT_SRC
      script.async = true
      document.head.appendChild(script)
    }
  }).finally(() => {
    if ((window as CryptoProWindow).cadesplugin === undefined) pendingLoad = null
  })

  return pendingLoad
}
