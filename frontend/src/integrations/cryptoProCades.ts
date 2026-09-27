const CRYPTO_PRO_2012_PROVIDER = 'Crypto-Pro GOST R 34.10-2012 Cryptographic Service Provider'
const CRYPTO_PRO_2012_PROVIDER_TYPE = 80
const MINIMUM_PLUGIN_VERSION = [2, 0, 15003] as const
const MINIMUM_CSP_VERSION = [5, 0, 13003] as const

export type CryptoProErrorCode =
  | 'plugin_script_missing'
  | 'plugin_load_timeout'
  | 'plugin_unavailable'
  | 'unsupported_runtime'
  | 'unsupported_browser'
  | 'unsupported_operating_system'
  | 'untested_operating_system'
  | 'plugin_version_unsupported'
  | 'csp_version_unsupported'
  | 'csp_missing'
  | 'store_unavailable'
  | 'certificate_not_found'
  | 'certificate_has_no_private_key'
  | 'certificate_invalid'
  | 'invalid_payload'
  | 'signature_failed'

const ERROR_MESSAGES: Record<CryptoProErrorCode, string> = {
  plugin_script_missing: 'КриптоПро недоступен: локальный скрипт плагина не загружен.',
  plugin_load_timeout: 'КриптоПро не ответил вовремя. Проверьте расширение и локальный сервис.',
  plugin_unavailable: 'КриптоПро недоступен. Проверьте расширение и локальный сервис.',
  unsupported_runtime: 'Эта версия браузера или КриптоПро не поддерживает безопасный режим подписи.',
  unsupported_browser: 'Этот браузер или его версия не поддерживаются для локальной подписи.',
  unsupported_operating_system: 'Эта версия операционной системы не поддерживается для локальной подписи.',
  untested_operating_system: 'Операционная система не подтверждена для локальной подписи.',
  plugin_version_unsupported: 'Версия КриптоПро Browser Plug-in слишком старая.',
  csp_version_unsupported: 'Версия КриптоПро CSP слишком старая.',
  csp_missing: 'КриптоПро CSP не установлен или недоступен.',
  store_unavailable: 'Не удалось открыть хранилище сертификатов КриптоПро.',
  certificate_not_found: 'Выбранный сертификат больше недоступен.',
  certificate_has_no_private_key: 'У выбранного сертификата нет доступного закрытого ключа.',
  certificate_invalid: 'Сертификат не прошёл проверку срока действия или цепочки доверия.',
  invalid_payload: 'Данные документа для подписи имеют неверный формат.',
  signature_failed: 'КриптоПро не смог подписать документ.',
}

export class CryptoProError extends Error {
  readonly code: CryptoProErrorCode

  constructor(code: CryptoProErrorCode) {
    super(ERROR_MESSAGES[code])
    this.name = 'CryptoProError'
    this.code = code
  }
}

export type CryptoProReadiness = {
  pluginVersion: string
  cspVersion: string
}

export type CryptoProCertificate = {
  thumbprint: string
  subject: string
  issuer: string
  validFrom: string
  validTo: string
}

export type DetachedDocumentToSign = {
  payloadBase64: string
  certificateThumbprint: string
}

export type DetachedDocumentSignature = {
  signatureBase64: string
  certificateThumbprint: string
}

export type AttachedAuthChallengeToSign = {
  challengeData: string
  certificateThumbprint: string
}

export type AttachedAuthChallengeSignature = {
  signatureBase64: string
  certificateThumbprint: string
}

export type TestedOperatingSystem =
  | { family: 'windows'; major: 10 | 11; evidenceId: string }
  | { family: 'macos'; major: 11 | 12 | 13 | 14; evidenceId: string }

type SupportedBrowser = 'chrome' | 'edge' | 'firefox'

type RuntimeEnvironment = {
  browser: SupportedBrowser
  browserMajor: number
  operatingSystem: 'windows-10-or-11' | 'macos-11' | 'macos-12' | 'macos-13' | 'macos-14'
}

type CadesObject = Record<string, unknown>

type CadesRuntime = {
  CreateObjectAsync: (objectName: string) => Promise<unknown>
  getLastError?: (error: unknown) => unknown
  then?: (onFulfilled: () => void, onRejected: (reason: unknown) => void) => unknown
  CAPICOM_CURRENT_USER_STORE: number
  CAPICOM_MY_STORE: string
  CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED: number
  CAPICOM_CERTIFICATE_FIND_SHA1_HASH: number
  CAPICOM_CERTIFICATE_FIND_TIME_VALID: number
  CADESCOM_BASE64_TO_BINARY: number
  CADESCOM_CADES_BES: number
}

type ReadyCadesRuntime = Omit<CadesRuntime, 'then'>

type RuntimeWindow = Window & { cadesplugin?: unknown }

const asObject = (value: unknown, _label: string): CadesObject => {
  void _label
  if (typeof value !== 'object' || value === null) {
    throw new CryptoProError('plugin_unavailable')
  }
  return value as CadesObject
}

const readMember = async <T>(object: CadesObject, name: string): Promise<T> =>
  (await Promise.resolve(object[name])) as T

const callMember = async <T>(object: CadesObject, name: string, ...args: unknown[]): Promise<T> => {
  const method = object[name]
  if (typeof method !== 'function') {
    throw new CryptoProError('unsupported_runtime')
  }
  return (await Promise.resolve(Reflect.apply(method, object, args))) as T
}

const internalNativeErrorText = (runtime: Partial<CadesRuntime> | undefined, error: unknown): string => {
  let detail: unknown = error
  try {
    if (runtime?.getLastError) detail = runtime.getLastError(error)
  } catch {
    detail = error
  }

  const text = detail instanceof Error ? detail.message : String(detail ?? '')
  return text.slice(0, 2_000)
}

const normalizeThumbprint = (value: string): string => value.replace(/\s+/g, '').toUpperCase()

const normalizeDate = (value: unknown, _label: string): string => {
  void _label
  const date = value instanceof Date ? value : new Date(String(value))
  if (Number.isNaN(date.getTime())) {
    throw new CryptoProError('certificate_invalid')
  }
  return date.toISOString()
}

const normalizeSignature = (value: unknown): string => {
  if (typeof value !== 'string') {
    throw new CryptoProError('signature_failed')
  }
  const signature = value.replace(/[\r\n]/g, '')
  if (!isBase64(signature)) {
    throw new CryptoProError('signature_failed')
  }
  return signature
}

const isBase64 = (value: string): boolean =>
  value.length > 0 &&
  value.length % 4 === 0 &&
  /^[A-Za-z0-9+/]*={0,2}$/.test(value) &&
  !/=/.test(value.slice(0, -2))

const versionToString = async (value: unknown): Promise<string> => {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  const object = asObject(value, 'version')
  const toString = object.toString
  if (typeof toString === 'function') {
    const result = await Promise.resolve(Reflect.apply(toString, object, []))
    if (typeof result === 'string' && result !== '[object Object]') return result
  }

  const major = await readMember<unknown>(object, 'MajorVersion')
  const minor = await readMember<unknown>(object, 'MinorVersion')
  const build = await readMember<unknown>(object, 'BuildVersion')
  return [major, minor, build].map(String).join('.')
}

const isCspMissing = (detail: string): boolean => detail.toLowerCase().includes('0x80090019')

const mapRuntimeError = (
  runtime: Partial<CadesRuntime> | undefined,
  error: unknown,
  fallback: CryptoProErrorCode,
): CryptoProError => {
  if (error instanceof CryptoProError) return error
  const detail = internalNativeErrorText(runtime, error)
  return new CryptoProError(isCspMissing(detail) ? 'csp_missing' : fallback)
}

const parseVersion = (value: string): [number, number, number] | null => {
  const parts = value.match(/\d+/g)?.slice(0, 3).map(Number)
  if (!parts || parts.length < 3 || parts.some((part) => !Number.isSafeInteger(part))) return null
  return [parts[0], parts[1], parts[2]]
}

const isVersionAtLeast = (value: string, minimum: readonly [number, number, number]): boolean => {
  const parsed = parseVersion(value)
  if (!parsed) return false
  for (let index = 0; index < minimum.length; index += 1) {
    if (parsed[index] > minimum[index]) return true
    if (parsed[index] < minimum[index]) return false
  }
  return true
}

const detectSupportedBrowser = (userAgent: string): { browser: SupportedBrowser; major: number } => {
  const edge = userAgent.match(/Edg\/(\d+)/)
  if (edge) {
    const major = Number(edge[1])
    if (major >= 104) return { browser: 'edge', major }
    throw new CryptoProError('unsupported_browser')
  }

  const firefox = userAgent.match(/Firefox\/(\d+)/)
  if (firefox) {
    const major = Number(firefox[1])
    if (major >= 52) return { browser: 'firefox', major }
    throw new CryptoProError('unsupported_browser')
  }

  const chrome = userAgent.match(/Chrome\/(\d+)/)
  if (chrome && !/OPR\//.test(userAgent)) {
    const major = Number(chrome[1])
    if (major >= 104) return { browser: 'chrome', major }
    throw new CryptoProError('unsupported_browser')
  }

  throw new CryptoProError('unsupported_browser')
}

const confirmedOperatingSystem = (confirmation: TestedOperatingSystem | undefined): RuntimeEnvironment['operatingSystem'] => {
  if (!confirmation || confirmation.evidenceId.trim() === '') {
    throw new CryptoProError('untested_operating_system')
  }
  if (confirmation.family === 'windows') return 'windows-10-or-11'
  return `macos-${confirmation.major}`
}

const detectSupportedOperatingSystem = (
  userAgent: string,
  confirmation: TestedOperatingSystem | undefined,
): RuntimeEnvironment['operatingSystem'] => {
  if (/Windows NT 10\.0/.test(userAgent)) return 'windows-10-or-11'
  if (/Windows NT/.test(userAgent)) throw new CryptoProError('unsupported_operating_system')

  const macos = userAgent.match(/Mac OS X (\d+)[_.]/)
  if (macos) {
    const major = Number(macos[1])
    if (major >= 11 && major <= 14) return `macos-${major}` as RuntimeEnvironment['operatingSystem']
    // Chromium may freeze the macOS token at 10_15 even on a newer OS. Only a scoped,
    // evidence-bearing confirmation may resolve that ambiguity; it cannot override macOS 15+.
    if (major === 10) return confirmedOperatingSystem(confirmation)
    throw new CryptoProError('unsupported_operating_system')
  }
  if (/Macintosh|MacIntel/.test(userAgent)) throw new CryptoProError('untested_operating_system')

  return confirmedOperatingSystem(confirmation)
}

const assertRuntimeSupport = (
  browserWindow: RuntimeWindow,
  readiness: CryptoProReadiness,
  confirmation: TestedOperatingSystem | undefined,
): RuntimeEnvironment => {
  const userAgent = browserWindow.navigator?.userAgent ?? ''
  const { browser, major: browserMajor } = detectSupportedBrowser(userAgent)
  const operatingSystem = detectSupportedOperatingSystem(userAgent, confirmation)
  if (!isVersionAtLeast(readiness.pluginVersion, MINIMUM_PLUGIN_VERSION)) {
    throw new CryptoProError('plugin_version_unsupported')
  }
  if (!isVersionAtLeast(readiness.cspVersion, MINIMUM_CSP_VERSION)) {
    throw new CryptoProError('csp_version_unsupported')
  }
  return { browser, browserMajor, operatingSystem }
}

const assertRuntime = (value: unknown): ReadyCadesRuntime => {
  if (typeof value !== 'object' || value === null) {
    throw new CryptoProError('plugin_unavailable')
  }
  const runtime = value as Partial<CadesRuntime>
  if (typeof runtime.CreateObjectAsync !== 'function') {
    throw new CryptoProError('unsupported_runtime')
  }
  const requiredConstants: Array<keyof CadesRuntime> = [
    'CAPICOM_CURRENT_USER_STORE',
    'CAPICOM_MY_STORE',
    'CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED',
    'CAPICOM_CERTIFICATE_FIND_SHA1_HASH',
    'CAPICOM_CERTIFICATE_FIND_TIME_VALID',
    'CADESCOM_BASE64_TO_BINARY',
    'CADESCOM_CADES_BES',
  ]
  if (requiredConstants.some((name) => runtime[name] === undefined)) {
    throw new CryptoProError('unsupported_runtime')
  }
  return runtime as ReadyCadesRuntime
}

const settleRuntime = async (
  runtimeValue: unknown,
  timeoutMs: number,
): Promise<{ runtime: ReadyCadesRuntime }> => {
  const candidate = runtimeValue as Partial<CadesRuntime>
  if (typeof candidate?.then === 'function') {
    let timeoutId: ReturnType<typeof setTimeout> | undefined
    try {
      await Promise.race([
        new Promise<void>((resolve, reject) => {
          candidate.then?.(resolve, reject)
        }),
        new Promise<never>((_, reject) => {
          timeoutId = setTimeout(() => reject(new CryptoProError('plugin_load_timeout')), timeoutMs)
        }),
      ])
    } catch (error) {
      throw mapRuntimeError(candidate, error, 'plugin_unavailable')
    } finally {
      if (timeoutId !== undefined) clearTimeout(timeoutId)
    }
  }
  return { runtime: assertRuntime(runtimeValue) }
}

const runtimeFromWindow = async (timeoutMs: number): Promise<{ runtime: ReadyCadesRuntime }> => {
  if (typeof window === 'undefined') throw new CryptoProError('plugin_script_missing')
  const runtimeValue = (window as RuntimeWindow).cadesplugin
  if (runtimeValue === undefined) throw new CryptoProError('plugin_script_missing')
  return settleRuntime(runtimeValue, timeoutMs)
}

const getStore = async (runtime: ReadyCadesRuntime): Promise<CadesObject> => {
  try {
    return asObject(await runtime.CreateObjectAsync('CAdESCOM.Store'), 'CAdESCOM.Store')
  } catch (error) {
    throw mapRuntimeError(runtime, error, 'store_unavailable')
  }
}

const openStore = async (runtime: ReadyCadesRuntime, store: CadesObject): Promise<void> => {
  try {
    await callMember(
      store,
      'Open',
      runtime.CAPICOM_CURRENT_USER_STORE,
      runtime.CAPICOM_MY_STORE,
      runtime.CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED,
    )
  } catch (error) {
    throw mapRuntimeError(runtime, error, 'store_unavailable')
  }
}

const closeStore = async (store: CadesObject): Promise<void> => {
  try {
    await callMember(store, 'Close')
  } catch {
    // Closing is best-effort and must not hide the operation's actual result.
  }
}

const findTimeValidCertificates = async (
  runtime: ReadyCadesRuntime,
  store: CadesObject,
): Promise<CadesObject> => {
  const certificates = asObject(await readMember(store, 'Certificates'), 'Certificates')
  return asObject(
    await callMember(certificates, 'Find', runtime.CAPICOM_CERTIFICATE_FIND_TIME_VALID),
    'time-valid Certificates',
  )
}

const certificateHasPrivateKey = async (certificate: CadesObject): Promise<boolean> =>
  Boolean(await callMember(certificate, 'HasPrivateKey'))

const certificateIsValid = async (certificate: CadesObject): Promise<boolean> => {
  const status = asObject(await callMember(certificate, 'IsValid'), 'CertificateStatus')
  return Boolean(await readMember(status, 'Result'))
}

const readCertificate = async (certificate: CadesObject): Promise<CryptoProCertificate> => ({
  thumbprint: normalizeThumbprint(String(await readMember(certificate, 'Thumbprint'))),
  subject: String(await readMember(certificate, 'SubjectName')),
  issuer: String(await readMember(certificate, 'IssuerName')),
  validFrom: normalizeDate(await readMember(certificate, 'ValidFromDate'), 'ValidFromDate'),
  validTo: normalizeDate(await readMember(certificate, 'ValidToDate'), 'ValidToDate'),
})

const selectedCertificate = async (
  runtime: ReadyCadesRuntime,
  store: CadesObject,
  thumbprint: string,
): Promise<CadesObject> => {
  const timeValid = await findTimeValidCertificates(runtime, store)
  const matches = asObject(
    await callMember(timeValid, 'Find', runtime.CAPICOM_CERTIFICATE_FIND_SHA1_HASH, thumbprint),
    'matching Certificates',
  )
  if (Number(await readMember(matches, 'Count')) !== 1) {
    throw new CryptoProError('certificate_not_found')
  }

  const certificate = asObject(await callMember(matches, 'Item', 1), 'Certificate')
  if (!(await certificateHasPrivateKey(certificate))) {
    throw new CryptoProError('certificate_has_no_private_key')
  }
  if (!(await certificateIsValid(certificate))) {
    throw new CryptoProError('certificate_invalid')
  }

  const actualThumbprint = normalizeThumbprint(String(await readMember(certificate, 'Thumbprint')))
  if (actualThumbprint !== thumbprint) throw new CryptoProError('certificate_not_found')
  return certificate
}

const signerForCertificate = async (
  runtime: ReadyCadesRuntime,
  certificate: CadesObject,
): Promise<CadesObject> => {
  const signer = asObject(await runtime.CreateObjectAsync('CAdESCOM.CPSigner'), 'CAdESCOM.CPSigner')
  await callMember(signer, 'propset_Certificate', certificate)
  await callMember(signer, 'propset_CheckCertificate', true)
  return signer
}

export class CryptoProCadesAdapter {
  readonly #timeoutMs: number
  readonly #testedOperatingSystem?: TestedOperatingSystem

  constructor(options: { timeoutMs?: number; testedOperatingSystem?: TestedOperatingSystem } = {}) {
    this.#timeoutMs = options.timeoutMs ?? 15_000
    this.#testedOperatingSystem = options.testedOperatingSystem
  }

  async #supportedRuntime(): Promise<{ runtime: ReadyCadesRuntime; readiness: CryptoProReadiness }> {
    const { runtime } = await runtimeFromWindow(this.#timeoutMs)
    try {
      const about = asObject(await runtime.CreateObjectAsync('CAdESCOM.About'), 'CAdESCOM.About')
      const pluginVersion = await versionToString(await readMember(about, 'PluginVersion'))
      const cspVersionObject = await callMember(
        about,
        'CSPVersion',
        CRYPTO_PRO_2012_PROVIDER,
        CRYPTO_PRO_2012_PROVIDER_TYPE,
      )
      const readiness = { pluginVersion, cspVersion: await versionToString(cspVersionObject) }
      assertRuntimeSupport(window as RuntimeWindow, readiness, this.#testedOperatingSystem)
      return { runtime, readiness }
    } catch (error) {
      throw mapRuntimeError(runtime, error, 'plugin_unavailable')
    }
  }

  async checkReadiness(): Promise<CryptoProReadiness> {
    return (await this.#supportedRuntime()).readiness
  }

  async listCertificates(): Promise<CryptoProCertificate[]> {
    const { runtime } = await this.#supportedRuntime()
    const store = await getStore(runtime)
    let opened = false
    try {
      await openStore(runtime, store)
      opened = true
      const certificates = await findTimeValidCertificates(runtime, store)
      const count = Number(await readMember(certificates, 'Count'))
      const result: CryptoProCertificate[] = []
      for (let index = 1; index <= count; index += 1) {
        const certificate = asObject(await callMember(certificates, 'Item', index), 'Certificate')
        if (await certificateHasPrivateKey(certificate)) result.push(await readCertificate(certificate))
      }
      return result
    } catch (error) {
      throw mapRuntimeError(runtime, error, opened ? 'plugin_unavailable' : 'store_unavailable')
    } finally {
      if (opened) await closeStore(store)
    }
  }

  async signDetachedDocument(input: DetachedDocumentToSign): Promise<DetachedDocumentSignature> {
    if (!isBase64(input.payloadBase64)) throw new CryptoProError('invalid_payload')
    const thumbprint = normalizeThumbprint(input.certificateThumbprint)
    if (!thumbprint) throw new CryptoProError('certificate_not_found')

    const { runtime } = await this.#supportedRuntime()
    const store = await getStore(runtime)
    let opened = false
    try {
      await openStore(runtime, store)
      opened = true
      const certificate = await selectedCertificate(runtime, store, thumbprint)
      const signer = await signerForCertificate(runtime, certificate)

      const signedData = asObject(
        await runtime.CreateObjectAsync('CAdESCOM.CadesSignedData'),
        'CAdESCOM.CadesSignedData',
      )
      // CryptoPro encodes Content as it is assigned, so this order is part of the signed-bytes contract.
      await callMember(signedData, 'propset_ContentEncoding', runtime.CADESCOM_BASE64_TO_BINARY)
      await callMember(signedData, 'propset_Content', input.payloadBase64)
      const signature = await callMember(
        signedData,
        'SignCades',
        signer,
        runtime.CADESCOM_CADES_BES,
        true,
      )

      return {
        signatureBase64: normalizeSignature(signature),
        certificateThumbprint: thumbprint,
      }
    } catch (error) {
      throw mapRuntimeError(runtime, error, 'signature_failed')
    } finally {
      if (opened) await closeStore(store)
    }
  }

  async signAttachedAuthChallenge(
    input: AttachedAuthChallengeToSign,
  ): Promise<AttachedAuthChallengeSignature> {
    if (typeof input.challengeData !== 'string' || input.challengeData.length === 0) {
      throw new CryptoProError('invalid_payload')
    }
    const thumbprint = normalizeThumbprint(input.certificateThumbprint)
    if (!thumbprint) throw new CryptoProError('certificate_not_found')

    const { runtime } = await this.#supportedRuntime()
    const store = await getStore(runtime)
    let opened = false
    try {
      await openStore(runtime, store)
      opened = true
      const certificate = await selectedCertificate(runtime, store, thumbprint)
      const signer = await signerForCertificate(runtime, certificate)
      const signedData = asObject(
        await runtime.CreateObjectAsync('CAdESCOM.CadesSignedData'),
        'CAdESCOM.CadesSignedData',
      )

      // True API Appendix 2 / @crpt/cades-pluginer 0.0.1 profile:
      // pass the exact JS string, keep the default STRING_TO_UCS2LE encoding and create attached BES.
      await callMember(signedData, 'propset_Content', input.challengeData)
      const rawSignature = await callMember(
        signedData,
        'SignCades',
        signer,
        runtime.CADESCOM_CADES_BES,
        false,
      )
      // Verify the attached CMS locally before its normalized base64 leaves the browser.
      await callMember(
        signedData,
        'VerifyCades',
        rawSignature,
        runtime.CADESCOM_CADES_BES,
        false,
      )

      return {
        signatureBase64: normalizeSignature(rawSignature),
        certificateThumbprint: thumbprint,
      }
    } catch (error) {
      throw mapRuntimeError(runtime, error, 'signature_failed')
    } finally {
      if (opened) await closeStore(store)
    }
  }
}
