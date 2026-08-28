// Скорость доставки FBS: от прихода заказа к нам до передачи в Wildberries.
//
// ДАННЫЕ НАСТОЯЩИЕ. Взяты с боевой базы 28.08.2026 по ИП Чжоу за последние семь
// дней: медиана, среднее и максимум по (supply.delivered_at − order.created_at_wb),
// сгруппировано по дню передачи в московском поясе.
//
// 23 августа в выборке нет — в этот день ни одна поставка не передавалась.

export type DayPoint = {
  /** ISO-дата дня. */
  date: string
  /** Как подписан день на экране. */
  label: string
  orders: number
  /** Медиана в часах — по ней судят о типичном дне. */
  median: number
  /** Среднее в часах — ловит хвост из нескольких застрявших заказов. */
  average: number
  /** Самый долгий заказ дня, часы. */
  worst: number
  /** Сколько уложилось в норматив. */
  inTime: number
}

/** Норматив, с которым сравниваем. Ниже — хорошо. */
export const TARGET_HOURS = 8

export const SELLER = 'ИП Чжоу'

export const WEEK: DayPoint[] = [
  { date: '2026-08-22', label: 'Сб 22.08', orders: 16, median: 15.69, average: 13.1, worst: 23.07, inTime: 6 },
  { date: '2026-08-24', label: 'Пн 24.08', orders: 12, median: 20.43, average: 22.84, worst: 41.05, inTime: 3 },
  { date: '2026-08-25', label: 'Вт 25.08', orders: 5, median: 6.2, average: 9.26, worst: 16.82, inTime: 3 },
  { date: '2026-08-26', label: 'Ср 26.08', orders: 16, median: 3.6, average: 7.09, worst: 23.06, inTime: 13 },
  { date: '2026-08-27', label: 'Чт 27.08', orders: 58, median: 8.51, average: 31.03, worst: 170.29, inTime: 14 },
  { date: '2026-08-28', label: 'Пт 28.08', orders: 177, median: 18.91, average: 22.41, worst: 48.87, inTime: 7 },
]

export function totals(days: DayPoint[]) {
  const orders = days.reduce((sum, day) => sum + day.orders, 0)
  const inTime = days.reduce((sum, day) => sum + day.inTime, 0)
  // Медиана недели — не среднее из дневных медиан, а медиана по заказам:
  // день с восемнадцатью заказами не должен весить столько же, сколько день
  // с девяноста двумя.
  const weighted = days.flatMap((day) => Array.from({ length: day.orders }, () => day.median))
  const sorted = [...weighted].sort((left, right) => left - right)
  const middle = sorted.length === 0 ? 0 : sorted[Math.floor(sorted.length / 2)]!
  const average =
    orders === 0 ? 0 : days.reduce((sum, day) => sum + day.average * day.orders, 0) / orders
  const worst = days.reduce((max, day) => Math.max(max, day.worst), 0)
  return { orders, inTime, median: middle, average, worst }
}

export function hours(value: number): string {
  const whole = Math.floor(value)
  const minutes = Math.round((value - whole) * 60)
  if (whole === 0) return `${minutes} мин`
  return minutes === 0 ? `${whole} ч` : `${whole} ч ${minutes} мин`
}
