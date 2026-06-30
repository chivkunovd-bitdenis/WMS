/** GS group separator (ASCII 29) in GS1 DataMatrix payloads. */
const GS1_GROUP_SEPARATOR = '\x1d'

export type ParsedGs1Cis = {
  gtin14: string
  gtinDisplay: string
  serial: string
  displayCode: string
}

export function formatGtinDisplay(gtin14: string): string {
  const trimmed = gtin14.trim()
  if (trimmed.length === 14 && trimmed.startsWith('0')) {
    return trimmed.slice(1)
  }
  return trimmed
}

function extractSerial(cis: string, gtinMatch: RegExpMatchArray | null): string {
  if (!gtinMatch) {
    const fallback = cis.match(/21([^\x1d]+)/)
    return fallback?.[1]?.trim() ?? ''
  }
  const afterGtinIndex = (gtinMatch.index ?? 0) + gtinMatch[0].length
  const afterGtin = cis.slice(afterGtinIndex)
  const serialMatch = afterGtin.match(/^21([^\x1d]+)/)
  return serialMatch?.[1]?.trim() ?? ''
}

export function maskCisTail(cis: string): string {
  const trimmed = cis.trim()
  if (trimmed.length <= 12) {
    return trimmed
  }
  return `…${trimmed.slice(-12)}`
}

/** Parse GS1 CIS fields used on the CZ thermal label right panel. */
export function parseGs1Cis(cis: string): ParsedGs1Cis {
  const normalized = cis.trim().replace(/\s+/g, '')
  const gtinMatch = normalized.match(new RegExp(`(?:^|${GS1_GROUP_SEPARATOR})01(\\d{14})`))
  const gtin14 = gtinMatch?.[1] ?? ''
  const serial = extractSerial(normalized, gtinMatch)
  return {
    gtin14,
    gtinDisplay: gtin14 ? formatGtinDisplay(gtin14) : '',
    serial,
    displayCode: maskCisTail(normalized),
  }
}
