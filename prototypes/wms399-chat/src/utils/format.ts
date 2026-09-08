export function fmtTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const same = d.toDateString() === now.toDateString()
  const opts: Intl.DateTimeFormatOptions = same
    ? { hour: '2-digit', minute: '2-digit' }
    : { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }
  return d.toLocaleString('ru-RU', opts).replace(',', '')
}

export function fmtDayLabel(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const midnight = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diffDays = Math.round((startOfToday - midnight) / (24 * 3600_000))
  if (diffDays <= 0) return 'Сегодня'
  if (diffDays === 1) return 'Вчера'
  if (diffDays < 7) {
    return d.toLocaleDateString('ru-RU', { weekday: 'long' })
  }
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' })
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} Б`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} кБ`
  return `${(n / (1024 * 1024)).toFixed(1)} МБ`
}

export function fmtRelative(iso: string): string {
  const d = new Date(iso).getTime()
  const diff = Math.round((Date.now() - d) / 60_000)
  if (diff < 1) return 'только что'
  if (diff < 60) return `${diff} мин назад`
  const h = Math.round(diff / 60)
  if (h < 24) return `${h} ч назад`
  const days = Math.round(h / 24)
  return `${days} дн назад`
}
