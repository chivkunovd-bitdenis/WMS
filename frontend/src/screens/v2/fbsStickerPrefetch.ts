import { fetchFbsPrintBatch, fetchFbsWorkspace, type FbsWorkspace } from './fbsApi'

// Share an in-flight request between tab entry and an immediate print click.
const pending = new Map<string, Promise<FbsWorkspace>>()
export function ensureFbsStickers(
  token: string, authHeaders: (token: string) => Record<string, string>, snapshot: FbsWorkspace,
): Promise<FbsWorkspace> {
  if (snapshot.supply.marketplace !== 'wb') return Promise.resolve(snapshot)
  const key = `${token}:${snapshot.supply.id}`
  const active = pending.get(key)
  if (active) return active
  const missing = snapshot.orders.filter(order => !order.sticker.code && order.status !== 'cancelled')
  if (!missing.length) return Promise.resolve(snapshot)
  const request = (async () => {
    const batch = await fetchFbsPrintBatch(token, authHeaders, snapshot.supply.id, {
      kind: 'order_sticker', order_ids: missing.map(order => order.id), retry_missing: true,
    })
    if (batch.order_errors.length) throw new Error(batch.order_errors.map(item => item.message).join(' '))
    return fetchFbsWorkspace(token, authHeaders, snapshot.supply.id)
  })()
  pending.set(key, request)
  void request.finally(() => { if (pending.get(key) === request) pending.delete(key) }).catch(() => undefined)
  return request
}
