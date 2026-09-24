import { spawnSync } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHALLENGE = 'Честный\u00a0знак\r\nchallenge: Ω 😀'
const EXPECTED_UCS2LE_HEX =
  '27043504410442043d044b043904a00037043d0430043a040d000a006300680061006c006c0065006e00670065003a002000a90320003dd800de'

function invoke(binary, args, options = {}) {
  const result = spawnSync(binary, args, {
    encoding: 'utf8',
    maxBuffer: 4 * 1024 * 1024,
    ...options,
  })
  if (result.error) throw result.error
  return result
}

function requireSuccess(binary, args, label) {
  const result = invoke(binary, args)
  if (result.status !== 0) {
    throw new Error(
      `${label} failed (${result.status ?? 'no exit code'}): ${result.stderr || result.stdout}`,
    )
  }
  return result
}

function supportsCades(binary) {
  const version = invoke(binary, ['version'])
  if (version.status !== 0 || !/^OpenSSL 3\./.test(version.stdout)) return false

  const cmsHelp = invoke(binary, ['cms', '-help'])
  return `${cmsHelp.stdout}\n${cmsHelp.stderr}`.includes('-cades')
}

function resolveOpenSsl() {
  const candidates = [
    process.env.OPENSSL_BIN,
    '/opt/homebrew/opt/openssl@3/bin/openssl',
    '/usr/local/opt/openssl@3/bin/openssl',
    'openssl',
  ].filter(Boolean)

  for (const candidate of candidates) {
    try {
      if (supportsCades(candidate)) return candidate
    } catch {
      // Try the next explicit/local/CI candidate.
    }
  }

  throw new Error(
    'OpenSSL 3 with `openssl cms -cades` is required. Set OPENSSL_BIN to a compatible binary.',
  )
}

const openssl = resolveOpenSsl()
const workDir = await mkdtemp(join(tmpdir(), 'wms517-cades-runner-'))

try {
  const challengePath = join(workDir, 'challenge.ucs2le')
  const keyPath = join(workDir, 'test-key.pem')
  const certificatePath = join(workDir, 'test-certificate.pem')
  const cmsPath = join(workDir, 'auth-challenge.p7s')
  const verifiedContentPath = join(workDir, 'verified-content.bin')
  const tamperedCmsPath = join(workDir, 'tampered-auth-challenge.p7s')

  const challengeBytes = Buffer.from(CHALLENGE, 'utf16le')
  if (challengeBytes.toString('hex') !== EXPECTED_UCS2LE_HEX) {
    throw new Error('The JS challenge no longer matches the pinned UCS-2LE byte fixture')
  }
  if (challengeBytes.subarray(0, 2).equals(Buffer.from([0xff, 0xfe]))) {
    throw new Error('Unexpected BOM: CryptoPro default UCS-2LE profile signs the string bytes directly')
  }
  await writeFile(challengePath, challengeBytes)

  requireSuccess(
    openssl,
    [
      'req',
      '-x509',
      '-newkey',
      'rsa:2048',
      '-sha256',
      '-nodes',
      '-keyout',
      keyPath,
      '-out',
      certificatePath,
      '-days',
      '1',
      '-set_serial',
      '517',
      '-subj',
      '/CN=WMS-517 CAdES runner/O=WMS test only/C=RU',
      '-addext',
      'basicConstraints=critical,CA:FALSE',
      '-addext',
      'keyUsage=critical,digitalSignature',
      '-addext',
      'extendedKeyUsage=emailProtection',
    ],
    'ephemeral certificate generation',
  )

  requireSuccess(
    openssl,
    [
      'cms',
      '-sign',
      '-binary',
      '-cades',
      '-nodetach',
      '-md',
      'sha256',
      '-in',
      challengePath,
      '-signer',
      certificatePath,
      '-inkey',
      keyPath,
      '-outform',
      'DER',
      '-out',
      cmsPath,
    ],
    'attached CAdES-BES signing',
  )

  const cmsPrint = requireSuccess(
    openssl,
    ['cms', '-cmsout', '-inform', 'DER', '-in', cmsPath, '-print', '-noout'],
    'CMS structure inspection',
  ).stdout
  if (!cmsPrint.includes('pkcs7-signedData') || !cmsPrint.includes('id-smime-aa-signingCertificateV2')) {
    throw new Error('CMS is missing the SignedData or SigningCertificateV2 CAdES-BES structure')
  }

  requireSuccess(
    openssl,
    [
      'cms',
      '-verify',
      '-binary',
      '-cades',
      '-verify_retcode',
      '-inform',
      'DER',
      '-in',
      cmsPath,
      '-CAfile',
      certificatePath,
      '-purpose',
      'any',
      '-out',
      verifiedContentPath,
    ],
    'independent attached CAdES-BES verification',
  )

  const verifiedContent = await readFile(verifiedContentPath)
  if (!verifiedContent.equals(challengeBytes)) {
    throw new Error('Verified embedded CMS content is not the exact pinned UCS-2LE challenge bytes')
  }
  if (verifiedContent.toString('utf16le') !== CHALLENGE) {
    throw new Error('Verified embedded CMS content does not round-trip to the exact JS challenge')
  }

  const cmsBytes = await readFile(cmsPath)
  const embeddedOffset = cmsBytes.indexOf(challengeBytes)
  if (embeddedOffset < 0) {
    throw new Error('Attached CMS does not contain the expected embedded UCS-2LE challenge bytes')
  }
  const tamperedCms = Buffer.from(cmsBytes)
  tamperedCms[embeddedOffset + 4] ^= 0x01
  await writeFile(tamperedCmsPath, tamperedCms)

  const tamperedVerification = invoke(openssl, [
    'cms',
    '-verify',
    '-binary',
    '-cades',
    '-verify_retcode',
    '-inform',
    'DER',
    '-in',
    tamperedCmsPath,
    '-CAfile',
    certificatePath,
    '-purpose',
    'any',
    '-out',
    join(workDir, 'tampered-content.bin'),
  ])
  if (tamperedVerification.status === 0) {
    throw new Error('Tampered embedded challenge unexpectedly passed CAdES verification')
  }

  const version = requireSuccess(openssl, ['version'], 'OpenSSL version check').stdout.trim()
  console.log(`WMS-517 auth CAdES runner: PASS (${version})`)
  console.log(`- exact JS challenge: ${JSON.stringify(CHALLENGE)}`)
  console.log(`- embedded content: ${challengeBytes.length} bytes, UCS-2LE, no BOM`)
  console.log('- profile: attached CMS SignedData, CAdES-BES SigningCertificateV2, SHA-256')
  console.log('- independent verification: valid CMS accepted; one-byte content tamper rejected')
  console.log('- certificate: ephemeral RSA test certificate; no production key, token, or cabinet used')
} finally {
  await rm(workDir, { force: true, recursive: true })
}
