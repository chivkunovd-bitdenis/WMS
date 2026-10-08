import { fetchFbsPrintBatch, fetchFbsWorkspace, type FbsWorkspace } from './fbsApi'

export type FbsStickerPrefetchResult = {
  workspace: FbsWorkspace
  errorMessage: string | null
}

// Share a pending batch request between entry preparation and an immediate print.
const pending = new Map<string, {
  promise: Promise<FbsStickerPrefetchResult>
  orderIds: Set<string>
}>()

export function ensureFbsStickers(
  token: string,
  authHeaders: (token: string) => Record<string, string>,
  snapshot: FbsWorkspace,
  requestedOrderIds?: readonly string[],
): Promise<FbsStickerPrefetchResult> {
  if (snapshot.supply.marketplace !== 'wb') {
    return Promise.resolve({ workspace: snapshot, errorMessage: null })
  }
  const requested = requestedOrderIds ? new Set(requestedOrderIds) : null
  const missing = snapshot.orders.filter(
    (order) => !order.sticker.code && order.status !== 'cancelled'
      && (!requested || requested.has(order.id)),
  )
  if (!missing.length) return Promise.resolve({ workspace: snapshot, errorMessage: null })

  const key = `${token}:${snapshot.supply.id}`
  const active = pending.get(key)
  if (active) {
    const uncovered = missing.filter((order) => !active.orderIds.has(order.id)).map((order) => order.id)
    if (!uncovered.length) return active.promise
    // A request already in flight for A cannot stand in for a newly added B.
    // Wait for A, then request only the uncovered IDs using its fresh response.
    return active.promise.then(
      (result) => {
        const refreshedIds = new Set(result.workspace.orders.map((order) => order.id))
        const carryForward = snapshot.orders.filter((order) =>
          uncovered.includes(order.id) && !refreshedIds.has(order.id),
        )
        const nextSnapshot = carryForward.length
          ? { ...result.workspace, orders: [...result.workspace.orders, ...carryForward] }
          : result.workspace
        return ensureFbsStickers(token, authHeaders, nextSnapshot, uncovered)
      },
      () => ensureFbsStickers(token, authHeaders, snapshot, uncovered),
    )
  }

  const request = (async (): Promise<FbsStickerPrefetchResult> => {
    const batch = await fetchFbsPrintBatch(token, authHeaders, snapshot.supply.id, {
      kind: 'order_sticker',
      order_ids: missing.map((order) => order.id),
      retry_missing: true,
    })
    const workspace = await fetchFbsWorkspace(token, authHeaders, snapshot.supply.id)
    return {
      workspace,
      errorMessage: batch.order_errors.length
        ? batch.order_errors.map((item) => item.message).join(' ')
        : null,
    }
  })()
  const entry = { promise: request, orderIds: new Set(missing.map((order) => order.id)) }
  pending.set(key, entry)
  void request.finally(() => {
    if (pending.get(key) === entry) pending.delete(key)
  }).catch(() => undefined)
  return request
}
