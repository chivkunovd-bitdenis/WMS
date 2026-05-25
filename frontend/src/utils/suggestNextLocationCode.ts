/**
 * Suggest next storage cell code from existing codes on the warehouse.
 *
 * 1) «A 1.21», «A 1.22» → «A 1.23» (стеллаж/сторона.номер)
 * 2) «1», «2», «3» → «4»
 * 3) иначе — count+1
 */
export function suggestNextLocationCode(existingCodes: string[]): string {
  const trimmed = existingCodes.map((c) => c.trim()).filter(Boolean)

  type Dotted = { prefix: string; pos: number; width: number }
  const dotted: Dotted[] = []
  for (const c of trimmed) {
    const m = /^(.+)\.(\d+)$/.exec(c)
    if (!m) {
      continue
    }
    dotted.push({
      prefix: m[1]!,
      pos: Number.parseInt(m[2]!, 10),
      width: m[2]!.length,
    })
  }

  if (dotted.length > 0) {
    const byPrefix = new Map<string, { maxPos: number; width: number }>()
    for (const d of dotted) {
      const cur = byPrefix.get(d.prefix) ?? { maxPos: -1, width: 1 }
      if (d.pos > cur.maxPos) {
        byPrefix.set(d.prefix, { maxPos: d.pos, width: d.width })
      } else if (d.pos === cur.maxPos) {
        byPrefix.set(d.prefix, { maxPos: d.pos, width: Math.max(cur.width, d.width) })
      }
    }
    let bestPrefix = ''
    let bestPos = -1
    let bestWidth = 1
    for (const [prefix, stat] of byPrefix) {
      if (stat.maxPos > bestPos) {
        bestPrefix = prefix
        bestPos = stat.maxPos
        bestWidth = stat.width
      }
    }
    const nextPos = String(bestPos + 1).padStart(bestWidth, '0')
    return `${bestPrefix}.${nextPos}`
  }

  let maxNum = 0
  let hasNumeric = false
  for (const c of trimmed) {
    if (/^\d+$/.test(c)) {
      hasNumeric = true
      maxNum = Math.max(maxNum, Number.parseInt(c, 10))
    }
  }
  if (hasNumeric) {
    return String(maxNum + 1)
  }
  return String(trimmed.length + 1)
}
