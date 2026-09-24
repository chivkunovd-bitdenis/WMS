import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'

import { CryptoProCadesAdapter, CryptoProError } from './cryptoProCades'

const CERT_THUMBPRINT = 'AABBCCDD'
const DOCUMENT_CRYPTO_FIXTURE = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      'src/integrations/fixtures/wms517WithdrawalDocumentCryptoFixture.json',
    ),
    'utf8',
  ),
) as { payload_utf8: string; payload_base64: string; payload_sha256: string }
const PAYLOAD_BASE64 = DOCUMENT_CRYPTO_FIXTURE.payload_base64

type FakeOptions = {
  hasPrivateKey?: boolean
  valid?: boolean
  signResult?: string
  signError?: Error
  verifyError?: Error
  storeOpenError?: Error
  matchingCount?: number
  pluginVersion?: string
  cspVersion?: string
}

const CHROME_120_MACOS_14 =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'

const makeVersion = (value: string) => ({ toString: vi.fn().mockResolvedValue(value) })

const makeFakeRuntime = (options: FakeOptions = {}) => {
  const calls: string[] = []
  const privateKeyRead = vi.fn()
  const certificate = {
    Thumbprint: 'AA BB CC DD',
    SubjectName: 'CN=Иван Иванов',
    IssuerName: 'CN=Тестовый УЦ',
    ValidFromDate: new Date('2026-01-01T00:00:00Z'),
    ValidToDate: new Date('2027-01-01T00:00:00Z'),
    HasPrivateKey: vi.fn().mockResolvedValue(options.hasPrivateKey ?? true),
    IsValid: vi.fn().mockResolvedValue({ Result: options.valid ?? true }),
    get PrivateKey() {
      privateKeyRead()
      throw new Error('PrivateKey must not be read')
    },
  }
  const matchingCertificates = {
    Count: options.matchingCount ?? 1,
    Item: vi.fn().mockResolvedValue(certificate),
  }
  const timeValidCertificates = {
    Count: 1,
    Item: vi.fn().mockResolvedValue(certificate),
    Find: vi.fn().mockImplementation(async (findType: number, thumbprint: string) => {
      calls.push(`find:${findType}:${thumbprint}`)
      return matchingCertificates
    }),
  }
  const certificates = {
    Find: vi.fn().mockImplementation(async (findType: number) => {
      calls.push(`find:${findType}`)
      return timeValidCertificates
    }),
  }
  const store = {
    Certificates: certificates,
    Open: vi.fn().mockImplementation(async (...args: unknown[]) => {
      calls.push(`open:${args.join(':')}`)
      if (options.storeOpenError) throw options.storeOpenError
    }),
    Close: vi.fn().mockImplementation(async () => {
      calls.push('close')
    }),
  }
  const signer = {
    propset_Certificate: vi.fn().mockImplementation(async () => {
      calls.push('signer:certificate')
    }),
    propset_CheckCertificate: vi.fn().mockImplementation(async (value: boolean) => {
      calls.push(`signer:check:${value}`)
    }),
    propset_KeyPin: vi.fn(),
  }
  const signedData = {
    propset_ContentEncoding: vi.fn().mockImplementation(async (value: number) => {
      calls.push(`contentEncoding:${value}`)
    }),
    propset_Content: vi.fn().mockImplementation(async (value: string) => {
      calls.push(`content:${value}`)
    }),
    SignCades: vi.fn().mockImplementation(async (_signer: unknown, type: number, detached: boolean) => {
      calls.push(`sign:${type}:${detached}`)
      if (options.signError) throw options.signError
      return options.signResult ?? 'QUJD\r\nRA=='
    }),
    VerifyCades: vi.fn().mockImplementation(async (signature: string, type: number, detached: boolean) => {
      calls.push(`verify:${signature}:${type}:${detached}`)
      if (options.verifyError) throw options.verifyError
    }),
  }
  const about = {
    PluginVersion: makeVersion(options.pluginVersion ?? '2.0.15003'),
    CSPVersion: vi.fn().mockResolvedValue(makeVersion(options.cspVersion ?? '5.0.13003')),
  }
  const CreateObjectAsync = vi.fn().mockImplementation(async (objectName: string) => {
    calls.push(`create:${objectName}`)
    if (objectName === 'CAdESCOM.About') return about
    if (objectName === 'CAdESCOM.Store') return store
    if (objectName === 'CAdESCOM.CPSigner') return signer
    if (objectName === 'CAdESCOM.CadesSignedData') return signedData
    throw new Error(`Unexpected object: ${objectName}`)
  })
  const runtime = {
    CreateObjectAsync,
    getLastError: vi.fn((error: unknown) => (error instanceof Error ? error.message : String(error))),
    CAPICOM_CURRENT_USER_STORE: 2,
    CAPICOM_MY_STORE: 'My',
    CAPICOM_STORE_OPEN_MAXIMUM_ALLOWED: 2,
    CAPICOM_CERTIFICATE_FIND_SHA1_HASH: 0,
    CAPICOM_CERTIFICATE_FIND_TIME_VALID: 9,
    CADESCOM_BASE64_TO_BINARY: 1,
    CADESCOM_CADES_BES: 1,
  }

  return {
    runtime,
    calls,
    certificate,
    matchingCertificates,
    timeValidCertificates,
    store,
    signer,
    signedData,
    about,
    CreateObjectAsync,
    privateKeyRead,
  }
}

const installRuntime = (
  runtime: unknown,
  userAgent = CHROME_120_MACOS_14,
  userAgentData?: {
    platform?: string
    getHighEntropyValues?: (hints: string[]) => Promise<{
      platform?: string
      platformVersion?: string
    }>
  },
) => {
  vi.stubGlobal('window', { cadesplugin: runtime, navigator: { userAgent, userAgentData } })
}

const expectCryptoProCode = async (promise: Promise<unknown>, code: CryptoProError['code']) => {
  try {
    await promise
    throw new Error('Expected CryptoProError')
  } catch (error) {
    expect(error).toBeInstanceOf(CryptoProError)
    expect((error as CryptoProError).code).toBe(code)
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('CryptoPro CAdES readiness', () => {
  it('fails closed when the pinned local runtime script is absent', async () => {
    vi.stubGlobal('window', {})

    await expectCryptoProCode(new CryptoProCadesAdapter().checkReadiness(), 'plugin_script_missing')
  })

  it('reads only About versions and does not open Store or private key', async () => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime)

    await expect(new CryptoProCadesAdapter().checkReadiness()).resolves.toEqual({
      pluginVersion: '2.0.15003',
      cspVersion: '5.0.13003',
    })
    expect(fake.CreateObjectAsync).toHaveBeenCalledTimes(1)
    expect(fake.CreateObjectAsync).toHaveBeenCalledWith('CAdESCOM.About')
    expect(fake.store.Open).not.toHaveBeenCalled()
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
  })

  it('reports a runtime initialization timeout without opening Store', async () => {
    vi.useFakeTimers()
    const fake = makeFakeRuntime()
    const then = vi.fn()
    installRuntime({ ...fake.runtime, then })

    const result = new CryptoProCadesAdapter({ timeoutMs: 25 }).checkReadiness()
    const assertion = expectCryptoProCode(result, 'plugin_load_timeout')
    await vi.advanceTimersByTimeAsync(25)

    await assertion
    expect(fake.store.Open).not.toHaveBeenCalled()
  })

  it('maps the documented CSP-not-installed error separately', async () => {
    const fake = makeFakeRuntime()
    fake.about.CSPVersion.mockRejectedValue(new Error('Provider failed (0x80090019)'))
    installRuntime(fake.runtime)

    await expectCryptoProCode(new CryptoProCadesAdapter().checkReadiness(), 'csp_missing')
  })

  it.each([
    [
      'Chrome 104 on Windows 10/11',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/104.0.0.0 Safari/537.36',
    ],
    [
      'Edge 104 on Windows 10/11',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/104.0.0.0 Safari/537.36 Edg/104.0.0.0',
    ],
    [
      'Firefox 52 on macOS 11',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 11_0) Gecko/20100101 Firefox/52.0',
    ],
    [
      'Chrome on macOS 12',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 12_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    ],
    [
      'Firefox on macOS 13',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) Gecko/20100101 Firefox/120.0',
    ],
    ['Chrome on macOS 14', CHROME_120_MACOS_14],
  ])('accepts the tested runtime baseline: %s', async (_name, userAgent) => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime, userAgent)

    await expect(new CryptoProCadesAdapter().checkReadiness()).resolves.toEqual({
      pluginVersion: '2.0.15003',
      cspVersion: '5.0.13003',
    })
  })

  it.each([
    [
      'Safari',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 Version/17.6 Safari/605.1.15',
      'unsupported_browser',
    ],
    [
      'old Chrome',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/103.0.0.0 Safari/537.36',
      'unsupported_browser',
    ],
    ['unknown browser', 'UnknownBrowser/1.0 (Windows NT 10.0)', 'unsupported_browser'],
    [
      'macOS 15',
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
      'unsupported_operating_system',
    ],
  ] as const)('rejects unsupported runtime: %s', async (_name, userAgent, code) => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime, userAgent)

    await expectCryptoProCode(new CryptoProCadesAdapter().checkReadiness(), code)
  })

  it('requires a per-instance tested OS confirmation when the browser cannot identify the OS', async () => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime, 'Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36')

    await expectCryptoProCode(new CryptoProCadesAdapter().checkReadiness(), 'untested_operating_system')
    await expect(
      new CryptoProCadesAdapter({
        testedOperatingSystem: { family: 'windows', major: 11, evidenceId: 'BC14-win11-edge-2026-09-23' },
      }).checkReadiness(),
    ).resolves.toEqual({ pluginVersion: '2.0.15003', cspVersion: '5.0.13003' })
  })

  it.each([
    [{ pluginVersion: '2.0.14999' }, 'plugin_version_unsupported'],
    [{ cspVersion: '5.0.12999' }, 'csp_version_unsupported'],
  ] as const)('rejects a CryptoPro runtime below the tested baseline', async (options, code) => {
    const fake = makeFakeRuntime(options)
    installRuntime(fake.runtime)

    await expectCryptoProCode(new CryptoProCadesAdapter().checkReadiness(), code)
  })

  it('classifies 0x80090019 internally without exposing a native path, container or thumbprint', async () => {
    const secret = '/Users/seller/keys/container-HDIMAGE thumbprint=DEADBEEF PIN=1234 (0x80090019)'
    const fake = makeFakeRuntime()
    fake.about.CSPVersion.mockRejectedValue(new Error(secret))
    installRuntime(fake.runtime)

    let caught: unknown
    try {
      await new CryptoProCadesAdapter().checkReadiness()
    } catch (error) {
      caught = error
    }

    expect(caught).toBeInstanceOf(CryptoProError)
    expect((caught as CryptoProError).code).toBe('csp_missing')
    expect(String(caught)).not.toContain(secret)
    expect(JSON.stringify(caught)).not.toContain(secret)
    expect((caught as Error & { cause?: unknown }).cause).toBeUndefined()
    expect(caught).not.toHaveProperty('technicalDetail')
  })

  it('uses Chrome platformVersion and reaches Store with the default adapter on frozen macOS UA', async () => {
    const fake = makeFakeRuntime()
    const getHighEntropyValues = vi.fn().mockResolvedValue({
      platform: 'macOS',
      platformVersion: '14.6.0',
    })
    installRuntime(
      fake.runtime,
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
      { platform: 'macOS', getHighEntropyValues },
    )

    await expect(new CryptoProCadesAdapter().listCertificates()).resolves.toHaveLength(1)
    expect(getHighEntropyValues).toHaveBeenCalledWith(['platformVersion'])
    expect(fake.store.Open).toHaveBeenCalledWith(2, 'My', 2)
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
  })

  it('keeps the scoped confirmation fallback when frozen macOS client hints are unavailable', async () => {
    const fake = makeFakeRuntime()
    installRuntime(
      fake.runtime,
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    )

    await expectCryptoProCode(new CryptoProCadesAdapter().checkReadiness(), 'untested_operating_system')
    await expect(
      new CryptoProCadesAdapter({
        testedOperatingSystem: { family: 'macos', major: 14, evidenceId: 'BC14-macos14-chrome-2026-09-23' },
      }).checkReadiness(),
    ).resolves.toEqual({ pluginVersion: '2.0.15003', cspVersion: '5.0.13003' })
  })

  it('rejects a frozen macOS user-agent when Chrome reports an unsupported platformVersion', async () => {
    const fake = makeFakeRuntime()
    installRuntime(
      fake.runtime,
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
      {
        platform: 'macOS',
        getHighEntropyValues: vi.fn().mockResolvedValue({
          platform: 'macOS',
          platformVersion: '15.0.0',
        }),
      },
    )

    await expectCryptoProCode(
      new CryptoProCadesAdapter().checkReadiness(),
      'unsupported_operating_system',
    )
    expect(fake.store.Open).not.toHaveBeenCalled()
  })

  it('rejects unsupported runtime before Store access or signing', async () => {
    const fake = makeFakeRuntime()
    installRuntime(
      fake.runtime,
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 Version/17.6 Safari/605.1.15',
    )

    await expectCryptoProCode(new CryptoProCadesAdapter().listCertificates(), 'unsupported_browser')
    await expectCryptoProCode(
      new CryptoProCadesAdapter().signDetachedDocument({
        payloadBase64: PAYLOAD_BASE64,
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'unsupported_browser',
    )
    expect(fake.CreateObjectAsync).not.toHaveBeenCalledWith('CAdESCOM.Store')
    expect(fake.CreateObjectAsync).not.toHaveBeenCalledWith('CAdESCOM.CPSigner')
    expect(fake.signedData.SignCades).not.toHaveBeenCalled()
  })
})

describe('CryptoPro certificate access', () => {
  it('opens CurrentUser/My only after an explicit certificate request and omits no-key certificates', async () => {
    const fake = makeFakeRuntime({ hasPrivateKey: false })
    installRuntime(fake.runtime)

    await expect(new CryptoProCadesAdapter().listCertificates()).resolves.toEqual([])
    expect(fake.store.Open).toHaveBeenCalledWith(2, 'My', 2)
    expect(fake.timeValidCertificates.Item).toHaveBeenCalledWith(1)
    expect(fake.certificate.HasPrivateKey).toHaveBeenCalledTimes(1)
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
  })

  it('returns only public display fields plus the full operation identifier', async () => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime)

    await expect(new CryptoProCadesAdapter().listCertificates()).resolves.toEqual([
      {
        thumbprint: CERT_THUMBPRINT,
        subject: 'CN=Иван Иванов',
        issuer: 'CN=Тестовый УЦ',
        validFrom: '2026-01-01T00:00:00.000Z',
        validTo: '2027-01-01T00:00:00.000Z',
      },
    ])
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
  })

  it('reports Store access failure without retrying or pretending the Store was opened', async () => {
    const fake = makeFakeRuntime({ storeOpenError: new Error('access denied') })
    installRuntime(fake.runtime)

    await expectCryptoProCode(new CryptoProCadesAdapter().listCertificates(), 'store_unavailable')
    expect(fake.store.Open).toHaveBeenCalledTimes(1)
    expect(fake.store.Close).not.toHaveBeenCalled()
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
  })
})

describe('CryptoPro exact detached document signing', () => {
  it('passes the original base64 unchanged after ContentEncoding and creates CAdES-BES detached', async () => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime)

    await expect(
      new CryptoProCadesAdapter().signDetachedDocument({
        payloadBase64: PAYLOAD_BASE64,
        certificateThumbprint: 'aa bb cc dd',
      }),
    ).resolves.toEqual({
      signatureBase64: 'QUJDRA==',
      certificateThumbprint: CERT_THUMBPRINT,
    })

    expect(fake.signedData.propset_Content).toHaveBeenCalledWith(PAYLOAD_BASE64)
    expect(fake.signedData.SignCades).toHaveBeenCalledWith(fake.signer, 1, true)
    expect(fake.calls.indexOf('contentEncoding:1')).toBeLessThan(fake.calls.indexOf(`content:${PAYLOAD_BASE64}`))
    expect(fake.calls.indexOf(`content:${PAYLOAD_BASE64}`)).toBeLessThan(fake.calls.indexOf('sign:1:true'))
    expect(fake.signer.propset_CheckCertificate).toHaveBeenCalledWith(true)
    expect(fake.signer.propset_KeyPin).not.toHaveBeenCalled()
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
    expect(Buffer.from(PAYLOAD_BASE64, 'base64').toString('utf8')).toBe(
      DOCUMENT_CRYPTO_FIXTURE.payload_utf8,
    )
  })

  it('fails before signer creation when certificate chain validation fails', async () => {
    const fake = makeFakeRuntime({ valid: false })
    installRuntime(fake.runtime)

    await expectCryptoProCode(
      new CryptoProCadesAdapter().signDetachedDocument({
        payloadBase64: PAYLOAD_BASE64,
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'certificate_invalid',
    )
    expect(fake.CreateObjectAsync).not.toHaveBeenCalledWith('CAdESCOM.CPSigner')
    expect(fake.signedData.SignCades).not.toHaveBeenCalled()
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
  })

  it('does not sign when the selected certificate disappeared', async () => {
    const fake = makeFakeRuntime({ matchingCount: 0 })
    installRuntime(fake.runtime)

    await expectCryptoProCode(
      new CryptoProCadesAdapter().signDetachedDocument({
        payloadBase64: PAYLOAD_BASE64,
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'certificate_not_found',
    )
    expect(fake.CreateObjectAsync).not.toHaveBeenCalledWith('CAdESCOM.CPSigner')
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
  })

  it('does not retry a rejected CSP/PIN signing prompt or read PIN itself', async () => {
    const fake = makeFakeRuntime({ signError: new Error('User cancelled CSP prompt') })
    installRuntime(fake.runtime)

    await expectCryptoProCode(
      new CryptoProCadesAdapter().signDetachedDocument({
        payloadBase64: PAYLOAD_BASE64,
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'signature_failed',
    )
    expect(fake.signedData.SignCades).toHaveBeenCalledTimes(1)
    expect(fake.signer.propset_KeyPin).not.toHaveBeenCalled()
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
  })

  it('rejects malformed payload without opening the plugin or reserializing anything', async () => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime)

    await expectCryptoProCode(
      new CryptoProCadesAdapter().signDetachedDocument({
        payloadBase64: '{"not":"base64"}',
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'invalid_payload',
    )
    expect(fake.CreateObjectAsync).not.toHaveBeenCalled()
  })

  it('signs the exact raw True API challenge as attached CAdES-BES and verifies it locally', async () => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime)
    const challenge = 'UUID:\u00a0АБВ\r\nexact challenge'

    await expect(new CryptoProCadesAdapter().signAttachedAuthChallenge({
      challengeData: challenge,
      certificateThumbprint: 'aa bb cc dd',
    })).resolves.toEqual({
      signatureBase64: 'QUJDRA==',
      certificateThumbprint: CERT_THUMBPRINT,
    })

    expect(fake.signedData.propset_ContentEncoding).not.toHaveBeenCalled()
    expect(fake.signedData.propset_Content).toHaveBeenCalledWith(challenge)
    expect(fake.signedData.SignCades).toHaveBeenCalledWith(fake.signer, 1, false)
    expect(fake.signedData.VerifyCades).toHaveBeenCalledWith('QUJD\r\nRA==', 1, false)
    expect(fake.calls.indexOf(`content:${challenge}`)).toBeLessThan(fake.calls.indexOf('sign:1:false'))
    expect(fake.calls.indexOf('sign:1:false')).toBeLessThan(
      fake.calls.indexOf('verify:QUJD\r\nRA==:1:false'),
    )
    expect(fake.signer.propset_CheckCertificate).toHaveBeenCalledWith(true)
    expect(fake.signer.propset_KeyPin).not.toHaveBeenCalled()
    expect(fake.privateKeyRead).not.toHaveBeenCalled()
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
  })

  it('fails closed when local VerifyCades rejects the attached signature', async () => {
    const fake = makeFakeRuntime({ verifyError: new Error('attached content was tampered') })
    installRuntime(fake.runtime)

    await expectCryptoProCode(
      new CryptoProCadesAdapter().signAttachedAuthChallenge({
        challengeData: 'challenge-before-tamper',
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'signature_failed',
    )

    expect(fake.signedData.SignCades).toHaveBeenCalledTimes(1)
    expect(fake.signedData.VerifyCades).toHaveBeenCalledTimes(1)
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
  })

  it('does not return an attached signature that is not valid base64', async () => {
    const fake = makeFakeRuntime({ signResult: 'not-a-cms-signature' })
    installRuntime(fake.runtime)

    await expectCryptoProCode(
      new CryptoProCadesAdapter().signAttachedAuthChallenge({
        challengeData: 'exact challenge',
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'signature_failed',
    )

    expect(fake.signedData.VerifyCades).toHaveBeenCalledWith('not-a-cms-signature', 1, false)
    expect(fake.store.Close).toHaveBeenCalledTimes(1)
  })

  it('rejects an empty auth challenge before opening the plugin', async () => {
    const fake = makeFakeRuntime()
    installRuntime(fake.runtime)

    await expectCryptoProCode(
      new CryptoProCadesAdapter().signAttachedAuthChallenge({
        challengeData: '',
        certificateThumbprint: CERT_THUMBPRINT,
      }),
      'invalid_payload',
    )
    expect(fake.CreateObjectAsync).not.toHaveBeenCalled()
  })
})
