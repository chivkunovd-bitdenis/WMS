import { randomId } from '../../../utils/randomId'

export type ScanBody = { inbound_request_id: string; operation_id: string; barcode: string; cell_id: string; to_id: string | null }

export function pendingScan(storage: Storage, key: string): ScanBody | null {
  const raw = storage.getItem(key)
  return raw ? JSON.parse(raw) as ScanBody : null
}

export function rememberScan(storage: Storage, key: string, body: Omit<ScanBody, 'operation_id'>): ScanBody {
  if (pendingScan(storage, key)) throw new Error('Предыдущий скан ещё ожидает ответа. Обновите документ для проверки результата; затем повторите неотправленные сканы.')
  const confirmed = { ...body, operation_id: randomId() }
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
