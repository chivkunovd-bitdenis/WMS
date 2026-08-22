const MOSCOW_OFFSET_MS = 3 * 60 * 60 * 1000

/**
 * Returns the current calendar date in Moscow timezone (UTC+3) as 'YYYY-MM-DD'.
 *
 * Between 00:00 and 02:59 Moscow time (21:00–23:59 UTC the previous day) the UTC
 * date is one day behind the Moscow date.  Using new Date().toISOString().slice(0,10)
 * in that window produces yesterday's date, causing the tariff form to default to a
 * date in the past.
 *
 * @param now - injectable for unit-testing; defaults to the current moment
 */
export function getMoscowDateString(now: Date = new Date()): string {
  const moscowDate = new Date(now.getTime() + MOSCOW_OFFSET_MS)
  const year = moscowDate.getUTCFullYear()
  const month = String(moscowDate.getUTCMonth() + 1).padStart(2, '0')
  const day = String(moscowDate.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
