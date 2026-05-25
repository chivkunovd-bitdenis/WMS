/** Matches backend catalog_service: rack name uppercased, code `{RACK} {side}.{position}`. */

export function normalizeRackName(name: string): string {
  return name.trim().toUpperCase()
}

export function formatLocationCode(
  rackName: string,
  side: 1 | 2,
  position: number,
): string {
  return `${normalizeRackName(rackName)} ${side}.${position}`
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Next free position for rack+side from existing cell codes on the warehouse. */
export function suggestNextLocationForRack(
  rackName: string,
  side: 1 | 2,
  existingCodes: string[],
): { position: number; code: string } {
  const rack = normalizeRackName(rackName)
  const re = new RegExp(`^${escapeRegExp(rack)} ${side}\\.(\\d+)$`, 'i')
  let maxPos = 0
  for (const raw of existingCodes) {
    const m = re.exec(raw.trim())
    if (m) {
      maxPos = Math.max(maxPos, Number.parseInt(m[1]!, 10))
    }
  }
  const position = maxPos + 1
  return { position, code: formatLocationCode(rack, side, position) }
}
