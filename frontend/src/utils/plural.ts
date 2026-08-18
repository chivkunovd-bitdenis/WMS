/**
 * Русское склонение существительного по числу.
 * forms — три формы: [1 короб, 2 короба, 5 коробов].
 */
export function plural(count: number, forms: [string, string, string]): string {
  const abs = Math.abs(count) % 100
  const last = abs % 10
  if (abs > 10 && abs < 20) {
    return forms[2]
  }
  if (last === 1) {
    return forms[0]
  }
  if (last >= 2 && last <= 4) {
    return forms[1]
  }
  return forms[2]
}
