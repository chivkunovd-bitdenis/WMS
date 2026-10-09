/**
 * Скан товара с неизвестным исходом: ответ на добавление штуки или на выдачу ЧЗ потерялся даже после
 * автоматического повтора. Операция живёт до первого определённого ответа сервера (2xx с телом или 4xx):
 * ручной повтор того же кода в тот же короб идёт с прежними ключами, поэтому штука и код ЧЗ не задваиваются.
 */
export type PendingScan = {
  productId: string | null
  mutationId: string
  issueMutationId: string | null
  unresolved: boolean
}

/**
 * Хранилище вне жизненного цикла компонента: уход на другую вкладку документа и возврат
 * (компонент создаётся заново) не теряют прежние ключи. Внешний ключ — id отгрузки,
 * внутренний — короб и исходный код.
 */
const pendingByShipment = new Map<string, Map<string, PendingScan>>()

export function pendingScanKey(boxId: string, raw: string): string {
  return `${boxId}\u0000${raw}`
}

/** Забирает незавершённую операцию; вернуть её в хранилище нужно, только если исход снова неизвестен. */
export function takePendingScan(shipmentId: string, key: string): PendingScan | undefined {
  const scans = pendingByShipment.get(shipmentId)
  if (!scans) return undefined
  const scan = scans.get(key)
  scans.delete(key)
  if (scans.size === 0) pendingByShipment.delete(shipmentId)
  return scan
}

export function keepPendingScan(shipmentId: string, key: string, scan: PendingScan): void {
  const scans = pendingByShipment.get(shipmentId) ?? new Map<string, PendingScan>()
  scans.set(key, scan)
  pendingByShipment.set(shipmentId, scans)
}

/** Для тестов: сбросить все незавершённые операции. */
export function clearPendingScans(): void {
  pendingByShipment.clear()
}
