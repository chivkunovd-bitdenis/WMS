/** Internal tenant slug (Latin, kebab-case) — generated on registration, not user-edited. */

const CYRILLIC_TO_LATIN: Record<string, string> = {
  а: 'a',
  б: 'b',
  в: 'v',
  г: 'g',
  д: 'd',
  е: 'e',
  ё: 'e',
  ж: 'zh',
  з: 'z',
  и: 'i',
  й: 'y',
  к: 'k',
  л: 'l',
  м: 'm',
  н: 'n',
  о: 'o',
  п: 'p',
  р: 'r',
  с: 's',
  т: 't',
  у: 'u',
  ф: 'f',
  х: 'h',
  ц: 'ts',
  ч: 'ch',
  ш: 'sh',
  щ: 'sch',
  ъ: '',
  ы: 'y',
  ь: '',
  э: 'e',
  ю: 'yu',
  я: 'ya',
  і: 'i',
  ї: 'yi',
  є: 'ye',
  '\u0491': 'g',
}

function randomSuffix(length: number): string {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789'
  const bytes = new Uint8Array(length)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => alphabet[b! % alphabet.length]).join('')
}

function transliterateChar(ch: string): string {
  return CYRILLIC_TO_LATIN[ch.toLowerCase()] ?? ''
}

/**
 * Builds a unique-enough slug: readable part from organization name + random suffix.
 * Matches backend `^[a-z0-9-]+$`, max length 64.
 */
export function buildAutoTenantSlug(organizationName: string): string {
  const raw = organizationName.trim()
  let out = ''
  for (const ch of raw) {
    if (/[a-z]/.test(ch)) {
      out += ch
      continue
    }
    if (/[A-Z]/.test(ch)) {
      out += ch.toLowerCase()
      continue
    }
    if (/\d/.test(ch)) {
      out += ch
      continue
    }
    if (ch === ' ' || ch === '-' || ch === '_' || ch === '.') {
      out += '-'
      continue
    }
    const t = transliterateChar(ch)
    if (t) {
      out += t
    }
  }
  out = out.replace(/-+/g, '-').replace(/^-|-$/g, '')
  if (out.length < 2) {
    out = `ff-${randomSuffix(8)}`
  }
  const suffix = randomSuffix(5)
  let combined = `${out}-${suffix}`.replace(/-+/g, '-').replace(/^-|-$/g, '')
  if (combined.length > 64) {
    combined = combined.slice(0, 64).replace(/-+$/g, '')
  }
  if (combined.length < 2) {
    combined = `ff-${randomSuffix(10)}`
  }
  return combined
}
