import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const EXPECTED_SHA256 = '3f9e438a166336220eed1d292e8b5f07e9a7f617260e98b2aa695fe6a97d4bbb'
const EXPECTED_LICENSE_SHA256 = 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4'
const root = process.cwd()
const useDist = process.argv.includes('--dist')
const relativePath = `${useDist ? 'dist' : 'public'}/vendor/cryptopro/cadesplugin_api.js`
const filePath = resolve(root, relativePath)

const bytes = await readFile(filePath)
const actual = createHash('sha256').update(bytes).digest('hex')
if (actual !== EXPECTED_SHA256) {
  throw new Error(`${relativePath} SHA-256 mismatch: expected ${EXPECTED_SHA256}, got ${actual}`)
}

if (!useDist) {
  const [license, provenance] = await Promise.all([
    readFile(resolve(root, 'public/vendor/cryptopro/LICENSE')),
    readFile(resolve(root, 'public/vendor/cryptopro/PROVENANCE.md'), 'utf8'),
  ])
  const licenseSha256 = createHash('sha256').update(license).digest('hex')
  if (licenseSha256 !== EXPECTED_LICENSE_SHA256) {
    throw new Error(
      `public/vendor/cryptopro/LICENSE SHA-256 mismatch: expected ${EXPECTED_LICENSE_SHA256}, got ${licenseSha256}`,
    )
  }
  for (const requiredText of [
    'license: MIT',
    'Apache License 2.0',
    'WMS uses the bundled Apache License 2.0 terms',
    'contains no `NOTICE` file',
  ]) {
    if (!provenance.includes(requiredText)) {
      throw new Error(`public/vendor/cryptopro/PROVENANCE.md is missing: ${requiredText}`)
    }
  }
}

console.log(`${relativePath}: verified ${actual}`)
