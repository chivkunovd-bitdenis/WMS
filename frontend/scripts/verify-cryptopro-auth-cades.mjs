import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const CHALLENGE = 'Честный\u00a0знак\r\nchallenge: Ω 😀'
const EXPECTED_UCS2LE_HEX =
  '27043504410442043d044b043904a00037043d0430043a040d000a006300680061006c006c0065006e00670065003a002000a90320003dd800de'
const documentFixture = JSON.parse(
  await readFile(
    resolve(
      process.cwd(),
      'src/integrations/fixtures/wms517WithdrawalDocumentCryptoFixture.json',
    ),
    'utf8',
  ),
)

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
  const documentPayloadPath = join(workDir, 'withdrawal-document.json')
  const documentCmsPath = join(workDir, 'withdrawal-document.p7s')
  const verifiedDocumentPath = join(workDir, 'verified-withdrawal-document.json')
  const tamperedDocumentPath = join(workDir, 'tampered-withdrawal-document.json')

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

  // This is the same payload_base64 fixture passed unchanged to
  // CryptoProCadesAdapter.signDetachedDocument in cryptoProCades.test.ts.
  // The browser contract is BASE64_TO_BINARY, so the bytes below—not parsed JSON—are signed.
  const expectedDocumentBytes = Buffer.from(documentFixture.payload_utf8, 'utf8')
  const documentBytes = Buffer.from(documentFixture.payload_base64, 'base64')
  if (!documentBytes.equals(expectedDocumentBytes)) {
    throw new Error('Document payload_base64 does not decode to the pinned exact UTF-8 payload bytes')
  }
  if (
    createHash('sha256').update(documentBytes).digest('hex') !==
    documentFixture.payload_sha256
  ) {
    throw new Error('Document payload SHA-256 does not match the pinned API contract')
  }
  await writeFile(documentPayloadPath, documentBytes)

  requireSuccess(
    openssl,
    [
      'cms',
      '-sign',
      '-binary',
      '-cades',
      '-md',
      'sha256',
      '-in',
      documentPayloadPath,
      '-signer',
      certificatePath,
      '-inkey',
      keyPath,
      '-outform',
      'DER',
      '-out',
      documentCmsPath,
    ],
    'detached document CAdES-BES signing',
  )

  const documentCmsPrint = requireSuccess(
    openssl,
    ['cms', '-cmsout', '-inform', 'DER', '-in', documentCmsPath, '-print', '-noout'],
    'detached document CMS structure inspection',
  ).stdout
  if (
    !documentCmsPrint.includes('pkcs7-signedData') ||
    !documentCmsPrint.includes('id-smime-aa-signingCertificateV2') ||
    !documentCmsPrint.includes('eContent: <ABSENT>')
  ) {
    throw new Error('Document CMS is not detached CAdES-BES with SigningCertificateV2')
  }

  const documentCmsBytes = await readFile(documentCmsPath)
  if (documentCmsBytes.indexOf(documentBytes) >= 0) {
    throw new Error('Detached document CMS unexpectedly embeds the exact payload bytes')
  }
  if (!Buffer.from(documentCmsBytes.toString('base64'), 'base64').equals(documentCmsBytes)) {
    throw new Error('Detached CMS signature does not round-trip through the API base64 contract')
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
      documentCmsPath,
      '-content',
      documentPayloadPath,
      '-CAfile',
      certificatePath,
      '-purpose',
      'any',
      '-out',
      verifiedDocumentPath,
    ],
    'independent detached document CAdES-BES verification',
  )
  if (!(await readFile(verifiedDocumentPath)).equals(documentBytes)) {
    throw new Error('Verified detached document content differs from the exact API payload bytes')
  }

  const tamperedDocument = Buffer.from(documentBytes)
  tamperedDocument[10] ^= 0x01
  await writeFile(tamperedDocumentPath, tamperedDocument)
  const tamperedDocumentVerification = invoke(openssl, [
    'cms',
    '-verify',
    '-binary',
    '-cades',
    '-verify_retcode',
    '-inform',
    'DER',
    '-in',
    documentCmsPath,
    '-content',
    tamperedDocumentPath,
    '-CAfile',
    certificatePath,
    '-purpose',
    'any',
    '-out',
    join(workDir, 'tampered-verified-document.json'),
  ])
  if (tamperedDocumentVerification.status === 0) {
    throw new Error('One-byte-tampered document payload unexpectedly passed detached verification')
  }

  const version = requireSuccess(openssl, ['version'], 'OpenSSL version check').stdout.trim()
  console.log(`WMS-517 CAdES profiles runner: PASS (${version})`)
  console.log('AUTH profile:')
  console.log(`- exact JS challenge: ${JSON.stringify(CHALLENGE)}`)
  console.log(`- embedded content: ${challengeBytes.length} bytes, UCS-2LE, no BOM`)
  console.log('- profile: attached CMS SignedData, CAdES-BES SigningCertificateV2, SHA-256')
  console.log('- independent verification: valid CMS accepted; one-byte content tamper rejected')
  console.log('DOCUMENT profile:')
  console.log(
    `- exact payload: ${documentBytes.length} UTF-8 bytes → payload_base64 → SHA-256 ${documentFixture.payload_sha256}`,
  )
  console.log('- profile: detached CMS SignedData, CAdES-BES SigningCertificateV2, SHA-256')
  console.log('- independent verification: exact payload accepted; one-byte payload tamper rejected')
  console.log('- certificate: ephemeral RSA test certificate; no production key, token, or cabinet used')
} finally {
  await rm(workDir, { force: true, recursive: true })
}
