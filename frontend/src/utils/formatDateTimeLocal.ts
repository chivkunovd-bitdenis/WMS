export function formatDateTimeLocal(iso: string): string {
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) {
    return iso
  }
  const fmt = new Intl.DateTimeFormat('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  // ru-RU normally returns "dd.mm.yyyy, hh:mm:ss"
  return fmt.format(d).replace(', ', ' ')
}

