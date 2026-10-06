/** Matches backend catalog_service: rack name uppercased and only active coordinates included. */

export function normalizeRackName(name: string): string {
  return name.trim().toUpperCase()
}

export function formatLocationCode(
  rackName: string,
  side: 1 | 2 | null,
  tier: number | null,
  position: number,
): string {
  return `${normalizeRackName(rackName)} ${[side, tier, position].filter((value) => value !== null).join('.')}`
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Next free position for the active address context from existing cell codes. */
export function suggestNextLocationForRack(
  rackName: string,
  side: 1 | 2 | null,
  tier: number | null,
  existingCodes: string[],
): { position: number; code: string } {
  const rack = normalizeRackName(rackName)
  const prefix = [side, tier].filter((value) => value !== null).join('\\.')
  const re = new RegExp(`^${escapeRegExp(rack)} ${prefix ? `${prefix}\\.` : ''}(\\d+)$`, 'i')
  let maxPos = 0
  for (const raw of existingCodes) {
    const m = re.exec(raw.trim())
    if (m) {
      maxPos = Math.max(maxPos, Number.parseInt(m[1]!, 10))
    }
  }
  let position = maxPos + 1
  const occupied = new Set(existingCodes.map((code) => code.trim().toLocaleUpperCase('ru-RU')))
  let code = formatLocationCode(rack, side, tier, position)
  while (occupied.has(code.toLocaleUpperCase('ru-RU'))) {
    position += 1
    code = formatLocationCode(rack, side, tier, position)
  }
  return { position, code }
}
