import { randomId } from '../../../utils/randomId'

export type PlacementBody = {
  kind: string; id: string; cell_id: string | null; to_id: string | null; qty: number
  inbound_request_id?: string; operation_id: string
}

// Store the confirmed HTTP body, never a second inventory balance. User identity
// survives token refresh; another employee/document/server cannot replay it.
export function placementStorageKey(token: string, endpoint: string, documentId: string): string {
  const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) as { sub?: string }
  if (!payload.sub) throw new Error('Не удалось определить сотрудника')
  return `wms:sorting-placement:${new URL(endpoint, location.origin).href}:${payload.sub}:${documentId}`
}

/** Only loose document stock has the server receipt used for automatic replay. */
export function canRememberSortingPlacement(payload: {
  kind: string
  cellId: string | null
  sourceHolder: string | null
}): boolean {
  return payload.kind === 'product' && payload.cellId !== null && payload.sourceHolder === null
}

export function pendingPlacement(storage: Storage, key: string): PlacementBody | null {
  const raw = storage.getItem(key)
  return raw ? JSON.parse(raw) as PlacementBody : null
}

export function rememberPlacement(storage: Storage, key: string, body: Omit<PlacementBody, 'operation_id'>): PlacementBody {
  if (pendingPlacement(storage, key)) throw new Error('Предыдущее размещение ещё ожидает ответа. Обновите документ для проверки результата.')
  const pending = { ...body, operation_id: randomId() }
  storage.setItem(key, JSON.stringify(pending))
  return pending
}

export async function sendPlacement(storage: Storage, key: string | null, body: PlacementBody, send: (body: PlacementBody) => Promise<Response>): Promise<Response> {
  const response = await send(body)
  // 401/403/408/429 and network/5xx may follow a committed first attempt.
  // Keep its identity until a conclusive response; replay is idempotent.
  if (key && (response.ok || [400, 404, 409, 422].includes(response.status))) {
    const pending = pendingPlacement(storage, key)
    if (pending?.operation_id === body.operation_id) storage.removeItem(key)
  }
  return response
}

/** A network failure says nothing about whether a durable placement reached the server. */
export function placementFailureMessage(error: unknown): string {
  if (!(error instanceof Error) || error.message === 'Failed to fetch') {
    return 'Не удалось получить ответ от сервера. Результат размещения пока неизвестен.'
  }
  return error.message
}
