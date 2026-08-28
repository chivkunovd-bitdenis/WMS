import { useCallback, useEffect, useMemo } from 'react'
import { apiUrl } from '../../api'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { buildInboundScanProductMap } from './inboundScanLookup'
import { effectiveActualQty, isSortingStatus } from './inboundReceivingHelpers'
import { suggestNextLocationCode } from '../../utils/suggestNextLocationCode'
import { useOzonReturnWorkflow } from './useOzonReturnWorkflow'
import { createDebouncedInboundReconciler } from './inboundReceivingRuntime'
import type { FfInboundRequestState } from './useFfInboundRequestState'
import { type CellLocationHint, type DiscrepancyActDetail, type DistributionLineOut, type FfInboundRequestViewProps, type InboundDetail, type LocationRow, type WarehouseRow, type WbCatalogRow } from './FfInboundRequestViewTypes'

export type FfInboundRequestDataContext = FfInboundRequestViewProps & FfInboundRequestState

export function useFfInboundRequestData(ctx: FfInboundRequestDataContext) {
  const authHeaders = ctx.authHeaders
  const focusActualInput = (lineId: string) => {
    window.setTimeout(() => {
      ctx.actualInputRefs.current[lineId]?.focus()
      ctx.actualInputRefs.current[lineId]?.select()
    }, 0)
  }

  const loadDetail = useCallback(async (): Promise<InboundDetail> => {
    const seq = ++ctx.loadDetailSeq.current
    const res = await fetch(apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}`), {
      headers: ctx.authHeaders,
    })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    const data = (await res.json()) as InboundDetail
    if (seq === ctx.loadDetailSeq.current) {
      ctx.setDetail(data)
    }
    return data
  }, [ctx.authHeaders, ctx.requestId])

  const receivingScanReconciler = useMemo(
    () => createDebouncedInboundReconciler(loadDetail),
    [loadDetail],
  )

  useEffect(
    () => () => {
      receivingScanReconciler.cancel()
    },
    [receivingScanReconciler],
  )

  const loadLinkedDiscrepancyActs = useCallback(async (): Promise<void> => {
    if (!ctx.isFulfillmentAdmin) {
      ctx.setLinkedDiscrepancyActs([])
      ctx.setDiscrepancyActsError(null)
      return
    }
    ctx.setDiscrepancyActsBusy(true)
    ctx.setDiscrepancyActsError(null)
    try {
      const listRes = await fetch(apiUrl('/operations/discrepancy-acts'), {
        headers: ctx.authHeaders,
      })
      if (!listRes.ok) {
        ctx.setDiscrepancyActsError(await readApiErrorMessage(listRes))
        ctx.setLinkedDiscrepancyActs([])
        return
      }
      const summaries = (await listRes.json()) as {
        id: string
        inbound_intake_request_id: string | null
      }[]
      const linked = summaries.filter((row) => row.inbound_intake_request_id === ctx.requestId)
      const details = await Promise.all(
        linked.map(async (row) => {
          const detailRes = await fetch(apiUrl(`/operations/discrepancy-acts/${row.id}`), {
            headers: ctx.authHeaders,
          })
          if (!detailRes.ok) {
            throw new Error(await readApiErrorMessage(detailRes))
          }
          return (await detailRes.json()) as DiscrepancyActDetail
        }),
      )
      ctx.setLinkedDiscrepancyActs(details)
    } catch (e) {
      ctx.setDiscrepancyActsError(e instanceof Error ? e.message : 'Не удалось загрузить акты расхождения.')
      ctx.setLinkedDiscrepancyActs([])
    } finally {
      ctx.setDiscrepancyActsBusy(false)
    }
  }, [ctx.authHeaders, ctx.isFulfillmentAdmin, ctx.requestId])

  const fetchCatalogRows = useCallback(async (): Promise<WbCatalogRow[]> => {
    const query = ctx.detail?.seller_id ? `?seller_id=${ctx.detail.seller_id}` : ''
    const res = await fetch(apiUrl(`/products/linked-wb-catalog${query}`), { headers: ctx.authHeaders })
    if (!res.ok) {
      throw new Error(await readApiErrorMessage(res))
    }
    return (await res.json()) as WbCatalogRow[]
  }, [ctx.authHeaders, ctx.detail?.seller_id])

  const loadCatalog = useCallback(async () => {
    ctx.setCatalog(await fetchCatalogRows())
  }, [fetchCatalogRows])

  const loadLocations = useCallback(
    async (warehouseId: string) => {
      const res = await fetch(
        apiUrl(`/warehouses/${warehouseId}/locations?exclude_sorting_zone=true`),
        { headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setLocations([])
        ctx.setDistError('Не удалось загрузить список ячеек склада.')
        return
      }
      const rows = (await res.json()) as LocationRow[]
      ctx.setLocations(rows)
      if (rows.length === 0) {
        ctx.setDistError(null)
        ctx.setNewLocationCode(suggestNextLocationCode([]))
      }
    },
    [ctx.authHeaders],
  )

  const createWarehouseLocation = async () => {
    const code = ctx.newLocationCode.trim()
    const detail = ctx.detail
    if (!detail?.warehouse_id || !code) {
      ctx.setDistError('Укажите код ячейки (например A-01).')
      return
    }
    ctx.setDistBusy(true)
    ctx.setDistError(null)
    try {
      const res = await fetch(apiUrl(`/warehouses/${detail.warehouse_id}/locations`), {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (!res.ok) {
        ctx.setDistError(await readApiErrorMessage(res))
        return
      }
      const created = (await res.json()) as LocationRow
      await loadLocations(detail.warehouse_id)
      ctx.setNewLocationCode(suggestNextLocationCode(ctx.locations.map((l) => l.code).concat(created.code)))
    } catch (e) {
      ctx.setDistError(e instanceof Error ? e.message : 'Не удалось создать ячейку.')
    } finally {
      ctx.setDistBusy(false)
    }
  }

  const loadCellHints = useCallback(
    async (productId: string) => {
      if (!ctx.detail?.warehouse_id || !productId) return
      try {
        const params = new URLSearchParams({
          product_id: productId,
          warehouse_id: ctx.detail.warehouse_id,
        })
        const res = await fetch(
          apiUrl(`/operations/inventory-balances/locations-by-product?${params}`),
          { headers: ctx.authHeaders },
        )
        if (!res.ok) return
        const rows = (await res.json()) as CellLocationHint[]
        ctx.setCellHintsByProductId((prev) => {
          if (prev[productId] !== undefined) return prev
          return { ...prev, [productId]: rows }
        })
      } catch {
        ctx.setCellHintsByProductId((prev) => {
          if (prev[productId] !== undefined) return prev
          return { ...prev, [productId]: [] }
        })
      }
    },
    [ctx.authHeaders, ctx.detail?.warehouse_id],
  )

  const loadDistribution = useCallback(async () => {
    if (!ctx.detail) return
    ctx.setDistError(null)
    try {
      const res = await fetch(
        apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/distribution-lines`),
        { headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setDistLines([])
        return
      }
      const rows = (await res.json()) as DistributionLineOut[]
      ctx.setDistLines(
        rows.map((r) => ({
          box_id: (r as { box_id?: string | null }).box_id ?? ctx.defaultPutawayBoxId,
          product_id: r.product_id,
          storage_location_id: r.storage_location_id,
          quantity: String(r.quantity),
        })),
      )
    } catch (e) {
      ctx.setDistLines([])
      ctx.setDistError(e instanceof Error ? e.message : 'Не удалось загрузить распределение.')
    }
  }, [ctx.authHeaders, ctx.defaultPutawayBoxId, ctx.detail, ctx.requestId])

  useEffect(() => {
    let cancelled = false
    ctx.setBusy(true)
    ctx.setError(null)
    void (async () => {
      try {
        await loadDetail()
        if (!cancelled) {
          ctx.setBusy(false)
        }
      } catch (e) {
        if (!cancelled) {
          ctx.setBusy(false)
          ctx.setError(e instanceof Error ? e.message : 'Не удалось загрузить заявку.')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadDetail])

  useEffect(() => {
    void loadLinkedDiscrepancyActs()
  }, [loadLinkedDiscrepancyActs])

  const catalogDetailLoaded = ctx.detail !== null
  const catalogSellerId = ctx.detail?.seller_id
  useEffect(() => {
    if (!catalogDetailLoaded) {
      return
    }
    void loadCatalog()
  }, [catalogDetailLoaded, catalogSellerId, loadCatalog])

  useEffect(() => {
    ctx.setPlannedDateDraft(ctx.detail?.planned_delivery_date ?? '')
  }, [ctx.detail?.planned_delivery_date])

  useEffect(() => {
    const detail = ctx.detail
    if (!detail) {
      ctx.setActualDraftByLineId({})
      return
    }
    const boxes = detail.boxes ?? []
    ctx.setActualDraftByLineId((prev) => {
      const next: Record<string, string> = {}
      for (const ln of detail.lines) {
        const existing = prev[ln.id]
        if (existing !== undefined && ctx.manualEditLineId === ln.id) {
          next[ln.id] = existing
          continue
        }
        next[ln.id] = String(effectiveActualQty(ln, boxes, detail.status))
      }
      return next
    })
    ctx.setActualDraftErrorByLineId((prev) => {
      const next: Record<string, string> = {}
      for (const ln of detail.lines) {
        if (ctx.manualEditLineId === ln.id && prev[ln.id]) {
          next[ln.id] = prev[ln.id]!
        }
      }
      return next
    })
  }, [ctx.detail, ctx.manualEditLineId])

  useEffect(() => {
    ctx.actualDraftRef.current = ctx.actualDraftByLineId
  }, [ctx.actualDraftByLineId])

  useEffect(() => {
    const warehouseId = ctx.detail?.warehouse_id
    if (!warehouseId) {
      ctx.setLocations([])
      ctx.setRequestWarehouse(null)
      return
    }
    void loadLocations(warehouseId)
    void (async () => {
      const res = await fetch(apiUrl('/warehouses'), { headers: ctx.authHeaders })
      if (!res.ok) {
        ctx.setRequestWarehouse(null)
        return
      }
      const rows = (await res.json()) as WarehouseRow[]
      ctx.setRequestWarehouse(rows.find((w) => w.id === warehouseId) ?? null)
    })()
  }, [ctx.authHeaders, ctx.detail?.warehouse_id, loadLocations])

  useEffect(() => {
    if (!ctx.detail) {
      ctx.setDistOpen(false)
      ctx.setDistLines([])
      return
    }
    if (!ctx.isFulfillmentAdmin) {
      ctx.setDistOpen(false)
      ctx.setDistLines([])
      return
    }
    if (!isSortingStatus(ctx.detail.status)) {
      ctx.setDistOpen(false)
      ctx.setDistLines([])
      return
    }
    if (ctx.workspace === 'reception') {
      ctx.setDistOpen(false)
      ctx.setDistLines([])
      return
    }
    if (ctx.workspace === 'sorting') {
      ctx.setDistOpen(false)
      return
    }
    void loadDistribution()
  }, [ctx.detail, ctx.isFulfillmentAdmin, loadDistribution, ctx.workspace])

  useEffect(() => {
    if (!ctx.distOpen || !isSortingStatus(ctx.detail?.status ?? '')) return
    for (const row of ctx.distLines) {
      if (row.product_id) void loadCellHints(row.product_id)
    }
  }, [ctx.distOpen, ctx.detail?.status, ctx.distLines, loadCellHints])

  useEffect(() => {
    if (!ctx.error) return
    document
      .querySelector('[data-testid="ff-inbound-doc-error"]')
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [ctx.error])

  const catalogById = useMemo(() => {
    const m = new Map<string, WbCatalogRow>()
    if (ctx.catalog) {
      for (const r of ctx.catalog) {
        m.set(r.id, r)
      }
    }
    return m
  }, [ctx.catalog])
  const ozonReturn = useOzonReturnWorkflow({ requestId: ctx.requestId, authHeaders: ctx.authHeaders, isOzonReturn: ctx.isOzonReturn, catalogById,
    documentNumber: ctx.displayDocumentNumber, sellerName: ctx.detail?.seller_name ?? null, loadDetail,
    setBusy: ctx.setBusy, setError: ctx.setError, setSuccessMessage: ctx.setImportSuccessMsg })

  const scanProductByBarcode = useMemo(
    () => buildInboundScanProductMap(ctx.detail?.lines ?? [], catalogById),
    [catalogById, ctx.detail?.lines],
  )

  // Витрина строки считается один раз на состав заявки. Если пересчитывать её
  // в рендере, meta каждый раз новый объект и memo у ячейки товара не работает.
  const displayMetaByProductId = useMemo(() => {
    const m = new Map<string, ReturnType<typeof productDisplayMetaFromCatalog>>()
    for (const ln of ctx.detail?.lines ?? []) {
      m.set(ln.product_id, productDisplayMetaFromCatalog(ln.product_id, ln, catalogById))
    }
    for (const b of ctx.detail?.boxes ?? []) {
      for (const ln of b.lines ?? []) {
        if (!m.has(ln.product_id)) {
          m.set(ln.product_id, productDisplayMetaFromCatalog(ln.product_id, ln, catalogById))
        }
      }
    }
    return m
  }, [catalogById, ctx.detail?.lines, ctx.detail?.boxes])

  const lineProductIds = useMemo(
    () => new Set(ctx.detail?.lines.map((l) => l.product_id) ?? []),
    [ctx.detail],
  )

  const pickerDisabledProductIds = useMemo(() => {
    if (ctx.detail?.status !== 'draft') {
      return new Set<string>()
    }
    return lineProductIds
  }, [ctx.detail?.status, lineProductIds])

  const draftLocked = ctx.detail != null && ctx.detail.status !== 'draft'

  const acceptedQtyByProductId = useMemo(() => {
    const m = new Map<string, number>()
    if (!ctx.detail) return m
    const boxes = ctx.detail.boxes ?? []
    for (const ln of ctx.detail.lines) {
      m.set(ln.product_id, effectiveActualQty(ln, boxes, ctx.detail.status))
    }
    return m
  }, [ctx.detail])


  const distributableProducts = useMemo(() => {
    const detail = ctx.detail
    if (!detail) return []
    const boxes = detail.boxes ?? []
    const rows = detail.lines
      .map((ln) => ({
        product_id: ln.product_id,
        sku_code: ln.sku_code,
        product_name: ln.product_name,
        accepted_qty: effectiveActualQty(ln, boxes, detail.status),
      }))
      .filter((x) => x.accepted_qty > 0)
    const seen = new Set<string>()
    const uniq: typeof rows = []
    for (const r of rows) {
      if (seen.has(r.product_id)) continue
      seen.add(r.product_id)
      uniq.push(r)
    }
    return uniq.sort((a, b) => a.sku_code.localeCompare(b.sku_code))
  }, [ctx.detail])

  const distSumByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const r of ctx.distLines) {
      const pid = r.product_id
      if (!pid) continue
      const q = Math.floor(Number(r.quantity))
      if (!Number.isFinite(q) || q <= 0) continue
      m.set(pid, (m.get(pid) ?? 0) + q)
    }
    return m
  }, [ctx.distLines])

  const distRemainingByProductId = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of distributableProducts) {
      const accepted = p.accepted_qty
      const used = distSumByProductId.get(p.product_id) ?? 0
      m.set(p.product_id, Math.max(accepted - used, 0))
    }
    return m
  }, [distributableProducts, distSumByProductId])

  const noCellRemainingLines = useMemo(
    () =>
      distributableProducts
        .map((p) => ({
          ...p,
          remaining: distRemainingByProductId.get(p.product_id) ?? p.accepted_qty,
        }))
        .filter((p) => p.remaining > 0),
    [distributableProducts, distRemainingByProductId],
  )

  const hasNoCellPending = noCellRemainingLines.length > 0

  const distributionCompleted = Boolean(ctx.detail?.distribution_completed_at)
  const distributionEditable = ctx.isFulfillmentAdmin && !distributionCompleted
  const canReopenDistribution =
    Boolean(ctx.detail) &&
    distributionCompleted &&
    isSortingStatus(ctx.detail!.status) &&
    ctx.detail!.lines.every((ln) => ln.posted_qty === 0)


  return {
    focusActualInput,
    loadDetail,
    receivingScanReconciler,
    loadLinkedDiscrepancyActs,
    fetchCatalogRows,
    loadCatalog,
    loadLocations,
    createWarehouseLocation,
    loadCellHints,
    loadDistribution,
    catalogDetailLoaded,
    catalogSellerId,
    catalogById,
    ozonReturn,
    scanProductByBarcode,
    displayMetaByProductId,
    lineProductIds,
    pickerDisabledProductIds,
    draftLocked,
    acceptedQtyByProductId,
    distributableProducts,
    distSumByProductId,
    distRemainingByProductId,
    noCellRemainingLines,
    hasNoCellPending,
    distributionCompleted,
    distributionEditable,
    canReopenDistribution,
  }
}

export type FfInboundRequestData = ReturnType<typeof useFfInboundRequestData>
