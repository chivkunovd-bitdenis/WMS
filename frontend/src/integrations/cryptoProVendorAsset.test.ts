import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const EXPECTED_SHA256 = '3f9e438a166336220eed1d292e8b5f07e9a7f617260e98b2aa695fe6a97d4bbb'
const EXPECTED_LICENSE_SHA256 = 'c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4'
const vendorPath = (fileName: string) => resolve(process.cwd(), 'public/vendor/cryptopro', fileName)

describe('pinned CryptoPro browser runtime', () => {
  it('keeps the exact @crpt/cades-pluginer 0.0.1 browser source bytes', async () => {
    const bytes = await readFile(vendorPath('cadesplugin_api.js'))
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(EXPECTED_SHA256)
  })

  it('ships the upstream license and explicit registry provenance', async () => {
    const [license, provenance] = await Promise.all([
      readFile(vendorPath('LICENSE'), 'utf8'),
      readFile(vendorPath('PROVENANCE.md'), 'utf8'),
    ])
    expect(createHash('sha256').update(license).digest('hex')).toBe(EXPECTED_LICENSE_SHA256)
    expect(license).toContain('Apache License')
    expect(provenance).toContain('@crpt/cades-pluginer')
    expect(provenance).toContain('0.0.1')
    expect(provenance).toContain(EXPECTED_SHA256)
    expect(provenance).toContain('07520a6ae601ef509434ca4fa8188d6ddc0b2b8ee035e8bd3cc57623eef3ce5b')
    expect(provenance).toContain('license: MIT')
    expect(provenance).toContain('WMS uses the bundled Apache License 2.0 terms')
    expect(provenance).toContain('contains no `NOTICE` file')
  })
})
