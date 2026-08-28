import type { FfInboundRequestActionContext } from './FfInboundRequestContexts'
import type { FfInboundDistributionActions } from './FfInboundRequestDistributionActions'
import type { InboundDetail, InboundLine } from './FfInboundRequestViewTypes'

export type FfInboundReceivingActionContext = FfInboundRequestActionContext & FfInboundDistributionActions

export function useFfInboundReceivingActions(ctx: FfInboundReceivingActionContext) {
  const authHeaders = ctx.authHeaders
  const formatLineDimensions = (line: InboundLine): string => {
    const parts: string[] = []
    if (line.length_mm != null && line.width_mm != null && line.height_mm != null) {
      parts.push(`${line.length_mm}×${line.width_mm}×${line.height_mm} мм`)
      if (line.volume_liters != null) {
        parts.push(`${line.volume_liters.toFixed(2)} л`)
      }
    }
    if (line.weight_g != null) {
      parts.push(`${(line.weight_g / 1000).toFixed(2)} кг`)
    }
    return parts.length > 0 ? parts.join(' · ') : '—'
  }

  const openDimensionsEditor = (line: InboundLine) => {
    ctx.setDimensionsLine(line)
    ctx.setDimensionDraft({
      length: line.length_mm != null ? String(line.length_mm) : '',
      width: line.width_mm != null ? String(line.width_mm) : '',
      height: line.height_mm != null ? String(line.height_mm) : '',
      weight: line.weight_g != null ? String(line.weight_g) : '',
    })
    ctx.setDimensionError(null)
  }

  const printReturnBarcodeForLine = (line: InboundLine) => {
    const barcode = line.wb_barcode?.trim()
    if (!barcode) {
      ctx.setScanToastError('У товара нет ШК WB для печати.')
      return
    }
    const captureWindow = window as unknown as {
      __WMS_CAPTURE_PRINT_HTML__?: boolean
      __WMS_LAST_PRINT_HTML__?: string
    }
    if (captureWindow.__WMS_CAPTURE_PRINT_HTML__) {
      captureWindow.__WMS_LAST_PRINT_HTML__ = `${line.product_name}\n${barcode}`
      return
    }
    ctx.printBarcodeLabel({
      title: line.product_name,
      barcode,
      barcodeDataUrl: ctx.renderBarcodeDataUrl(barcode),
    })
  }

  const addReceivedProductFact = async (
    productId: string,
    qty: number,
  ): Promise<InboundLine | null> => {
    const res = await fetch(ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/receiving/lines`), {
      method: 'POST',
      headers: { ...authHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, actual_qty: qty, source: 'seller_catalog' }),
    })
    if (!res.ok) {
      ctx.setError(ctx.scanErrorMessageRu(await ctx.readApiErrorMessage(res)))
      return null
    }
    return (await res.json()) as InboundLine
  }

  const saveDimensions = async () => {
    if (!ctx.dimensionsLine) return
    const dimRaw = [ctx.dimensionDraft.length, ctx.dimensionDraft.width, ctx.dimensionDraft.height]
    const hasAnyDimension = dimRaw.some((v) => v.trim() !== '')
    const hasAllDimensions = dimRaw.every((v) => v.trim() !== '')
    if (hasAnyDimension && !hasAllDimensions) {
      ctx.setDimensionError('Для габаритов укажите длину, ширину и высоту вместе.')
      return
    }
    const length = hasAllDimensions ? Math.floor(Number(ctx.dimensionDraft.length)) : null
    const width = hasAllDimensions ? Math.floor(Number(ctx.dimensionDraft.width)) : null
    const height = hasAllDimensions ? Math.floor(Number(ctx.dimensionDraft.height)) : null
    if (
      hasAllDimensions &&
      (length == null || width == null || height == null || length < 1 || width < 1 || height < 1)
    ) {
      ctx.setDimensionError('Габариты должны быть больше нуля.')
      return
    }
    const weight = ctx.dimensionDraft.weight.trim() === '' ? null : Math.floor(Number(ctx.dimensionDraft.weight))
    if (weight != null && (!Number.isFinite(weight) || weight < 1)) {
      ctx.setDimensionError('Вес должен быть больше нуля.')
      return
    }
    const payload: Record<string, number | null> = {}
    if (hasAllDimensions) {
      payload.length_mm = length
      payload.width_mm = width
      payload.height_mm = height
    }
    if (ctx.dimensionDraft.weight.trim() !== '') {
      payload.weight_g = weight
    }
    if (Object.keys(payload).length === 0) {
      ctx.setDimensionsLine(null)
      return
    }
    ctx.setBusy(true)
    ctx.setDimensionError(null)
    try {
      const res = await fetch(ctx.apiUrl(`/products/${ctx.dimensionsLine.product_id}/dimensions`), {
        method: 'PATCH',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        ctx.setDimensionError(await ctx.readApiErrorMessage(res))
        return
      }
      ctx.setDimensionsLine(null)
      await ctx.loadDetail()
      await ctx.loadCatalog()
    } catch (e) {
      ctx.setDimensionError(e instanceof Error ? e.message : 'Не удалось сохранить габариты.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const patchPlannedDate = async (isoDate: string) => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const res = await fetch(ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}`), {
        method: 'PATCH',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ planned_delivery_date: isoDate }),
      })
      if (!res.ok) {
        ctx.setError(await ctx.readApiErrorMessage(res))
        return
      }
      ctx.setDetail((await res.json()) as InboundDetail)
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось сохранить дату.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const openPicker = async (initialSearch = '') => {
    ctx.setError(null)
    ctx.setPickerInitialSearch(initialSearch)
    try {
      if (ctx.catalog == null) {
        await ctx.loadCatalog()
      }
      ctx.setPickerOpen(true)
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог.')
    }
  }

  const addLineByBarcode = async (rawInput?: string) => {
    if (!ctx.detail) return
    const code = (rawInput ?? '').trim()
    if (!code) return
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      let cat = ctx.catalog
      if (cat == null) {
        cat = await ctx.fetchCatalogRows()
        ctx.setCatalog(cat)
      }
      const productId = ctx.resolveProductIdByBarcode(cat, code)
      if (!productId) {
        ctx.setPickerInitialSearch(code)
        ctx.setError('Товар не найден в каталоге селлера. Добавление нового товара будет отдельной задачей.')
        return
      }
      const existing = ctx.detail.lines.find((ln) => ln.product_id === productId)
      if (existing) {
        const res = await fetch(
          ctx.apiUrl(
            `/operations/inbound-intake-requests/${ctx.requestId}/lines/${existing.id}/expected`,
          ),
          {
            method: 'PATCH',
            headers: { ...authHeaders, 'Content-Type': 'application/json' },
            body: JSON.stringify({ expected_qty: existing.expected_qty + 1 }),
          },
        )
        if (!res.ok) {
          ctx.setError(await ctx.readApiErrorMessage(res))
          return
        }
      } else {
        const res = await fetch(ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/lines`), {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ product_id: productId, expected_qty: 1 }),
        })
        if (!res.ok) {
          ctx.setError(await ctx.readApiErrorMessage(res))
          return
        }
      }
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось добавить строку по штрихкоду.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const applyPicker = async (pickerQtyByProduct: Record<string, number>) => {
    if (!ctx.detail) return
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const lineByProduct = new Map(ctx.detail.lines.map((ln) => [ln.product_id, ln]))
      const receivingMode = ctx.detail.status !== 'draft' && ctx.receivingActive
      for (const [productId, rawQty] of Object.entries(pickerQtyByProduct)) {
        const addQty = Number.isFinite(rawQty) ? Math.floor(rawQty) : 0
        if (addQty <= 0) continue
        if (receivingMode) {
          const added = await addReceivedProductFact(productId, addQty)
          if (!added) {
            return
          }
          continue
        }
        const existing = lineByProduct.get(productId)
        if (existing) {
          const next = existing.expected_qty + addQty
          const res = await fetch(
            ctx.apiUrl(
              `/operations/inbound-intake-requests/${ctx.requestId}/lines/${existing.id}/expected`,
            ),
            {
              method: 'PATCH',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ expected_qty: next }),
            },
          )
          if (!res.ok) {
            ctx.setError(await ctx.readApiErrorMessage(res))
            return
          }
        } else {
          const res = await fetch(
            ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/lines`),
            {
              method: 'POST',
              headers: { ...authHeaders, 'Content-Type': 'application/json' },
              body: JSON.stringify({ product_id: productId, expected_qty: addQty }),
            },
          )
          if (!res.ok) {
            ctx.setError(await ctx.readApiErrorMessage(res))
            return
          }
        }
      }
      ctx.setPickerOpen(false)
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось добавить товары.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const submitToWarehouse = async () => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/submit`),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setError(await ctx.readApiErrorMessage(res))
        return
      }
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось передать на склад.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const beginReceiving = async () => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/begin-receiving`),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setError(await ctx.readApiErrorMessage(res))
        return
      }
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось начать приёмку.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const printDistributionLocationLabel = (locationId: string) => {
    const loc = ctx.locations.find((l) => l.id === locationId)
    if (!loc) return
    const dataUrl = ctx.renderBarcodeDataUrl(loc.barcode)
    ctx.printBarcodeLabel({
      title: `Ячейка № ${loc.code}`,
      barcode: loc.barcode,
      barcodeDataUrl: dataUrl,
    })
  }


  return {
    formatLineDimensions,
    openDimensionsEditor,
    printReturnBarcodeForLine,
    addReceivedProductFact,
    saveDimensions,
    patchPlannedDate,
    openPicker,
    addLineByBarcode,
    applyPicker,
    submitToWarehouse,
    beginReceiving,
    printDistributionLocationLabel,
  }
}

export type FfInboundReceivingActions = ReturnType<typeof useFfInboundReceivingActions>
