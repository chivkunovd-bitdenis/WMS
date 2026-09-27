import { randomId } from '../../../utils/randomId'

export type ScanBody = { inbound_request_id: string; operation_id: string; barcode: string; cell_id: string; to_id: string | null }

export function pendingScan(storage: Storage, key: string): ScanBody | null {
  const raw = storage.getItem(key)
  return raw ? JSON.parse(raw) as ScanBody : null
}

export function rememberScan(storage: Storage, key: string, body: Omit<ScanBody, 'operation_id'>, operationId = randomId()): ScanBody {
  const previous = pendingScan(storage, key)
  if (previous?.operation_id === operationId) return previous
  if (previous) throw new Error('Предыдущий скан ещё ожидает ответа. Обновите документ для проверки результата; затем повторите неотправленные сканы.')
  const confirmed = { ...body, operation_id: operationId }
  storage.setItem(key, JSON.stringify(confirmed))
  return confirmed
}

export async function sendScan(storage: Storage, key: string, body: ScanBody, send: (body: ScanBody) => Promise<Response>): Promise<Response> {
  const response = await send(body)
  if (response.ok || [400, 404, 409, 422].includes(response.status)) {
    if (pendingScan(storage, key)?.operation_id === body.operation_id) storage.removeItem(key)
  }
  return response
}
