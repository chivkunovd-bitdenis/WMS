import { useMemo, useState } from 'react'
import type { LabelSize } from '../../utils/labelSize'
import { integerQtyError } from './inboundReceivingHelpers'
import type { FfInboundRequestActionContext } from './FfInboundRequestContexts'
import type { FfInboundDistributionActions } from './FfInboundRequestDistributionActions'
import type { FfInboundReceivingActions } from './FfInboundRequestReceivingActions'
import type { InboundBox, InboundCargoPlace, InboundDetail, InboundLine } from './FfInboundRequestViewTypes'

export type FfInboundPackageActionContext = FfInboundRequestActionContext & FfInboundDistributionActions & FfInboundReceivingActions

export function useFfInboundPackageActions(ctx: FfInboundPackageActionContext) {
  const authHeaders = ctx.authHeaders
  type InboundBoxPrintTarget =
    | { kind: 'box'; box: InboundBox }
    | { kind: 'box-all' }
    | { kind: 'cargo'; place: InboundCargoPlace }
    | { kind: 'cargo-all' }

  const [boxPrintTarget, setBoxPrintTarget] = useState<InboundBoxPrintTarget | null>(null)

  const printInboundBoxLabel = async (box: InboundBox, labelSize: LabelSize) => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const dataUrl = ctx.renderBarcodeDataUrl(box.internal_barcode)
      ctx.printBarcodeLabel({
        title: `Короб № ${box.box_number}`,
        barcode: box.internal_barcode,
        barcodeDataUrl: dataUrl,
        labelSize,
      })
      const res = await fetch(
        ctx.apiUrl(
          `/operations/inbound-intake-requests/${ctx.requestId}/boxes/${box.id}/mark-label-printed`,
        ),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setError(await ctx.readApiErrorMessage(res))
        return
      }
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетку короба.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const printAllInboundBoxLabels = async (labelSize: LabelSize) => {
    if (!ctx.detail?.boxes?.length) return
    for (const box of ctx.detail.boxes) {
      await printInboundBoxLabel(box, labelSize)
    }
  }

  const printInboundCargoPlaceLabel = async (place: InboundCargoPlace, labelSize: LabelSize) => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const dataUrl = ctx.renderBarcodeDataUrl(place.internal_barcode)
      ctx.printBarcodeLabel({
        title: `Грузоместо № ${place.place_number}`,
        barcode: place.internal_barcode,
        barcodeDataUrl: dataUrl,
        labelSize,
      })
      const res = await fetch(
        ctx.apiUrl(
          `/operations/inbound-intake-requests/${ctx.requestId}/cargo-places/${place.id}/mark-label-printed`,
        ),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setError(await ctx.readApiErrorMessage(res))
        return
      }
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось напечатать этикетку грузоместа.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const printAllInboundCargoPlaceLabels = async (labelSize: LabelSize) => {
    if (!ctx.detail?.cargo_places?.length) return
    for (const place of ctx.detail.cargo_places) {
      await printInboundCargoPlaceLabel(place, labelSize)
    }
  }

  const requestPrintInboundBox = (box: InboundBox) => {
    setBoxPrintTarget({ kind: 'box', box })
  }

  const requestPrintAllInboundBoxes = () => {
    if (!ctx.detail?.boxes?.length) return
    setBoxPrintTarget({ kind: 'box-all' })
  }

  const requestPrintInboundCargoPlace = (place: InboundCargoPlace) => {
    setBoxPrintTarget({ kind: 'cargo', place })
  }

  const requestPrintAllInboundCargoPlaces = () => {
    if (!ctx.detail?.cargo_places?.length) return
    setBoxPrintTarget({ kind: 'cargo-all' })
  }

  const confirmInboundBoxPrint = async (labelSize: LabelSize) => {
    const target = boxPrintTarget
    setBoxPrintTarget(null)
    if (!target) return
    if (target.kind === 'box') {
      await printInboundBoxLabel(target.box, labelSize)
    } else if (target.kind === 'box-all') {
      await printAllInboundBoxLabels(labelSize)
    } else if (target.kind === 'cargo') {
      await printInboundCargoPlaceLabel(target.place, labelSize)
    } else {
      await printAllInboundCargoPlaceLabels(labelSize)
    }
  }

  const scanToReceiving = async (raw?: string) => {
    const code = (raw ?? '').trim()
    if (!code) return
    ctx.setError(null)
    try {
      const productId = ctx.findInboundScanProductId(code, ctx.scanProductByBarcode)
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/receiving/scan`),
        {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ barcode: code, product_id: productId }),
        },
      )
      if (!res.ok) {
        const errorCode = await ctx.readApiErrorMessage(res)
        ctx.setScanToastError(ctx.scanErrorMessageRu(errorCode))
        ctx.setScanAddBarcode(
          errorCode === 'product_not_on_request' || errorCode === 'barcode_unknown'
            ? code
            : null,
        )
        return
      }
      ctx.setScanAddBarcode(null)
      const scannedLine = (await res.json()) as InboundLine
      ctx.setDetail((current) => {
        if (!current) return current
        return {
          ...current,
          lines: ctx.applyScannedInboundLine(current.lines, scannedLine),
        }
      })
      ctx.setLastScannedLineId(scannedLine.id)
      if (ctx.isReturnOperation && ctx.returnAutoPrint) {
        ctx.printReturnBarcodeForLine(scannedLine)
      }
      // Coalesce the expensive document reload until the operator pauses scanning.
      // The POST response already contains the authoritative changed line.
      ctx.receivingScanReconciler.schedule()
    } catch (e) {
      ctx.setScanToastError(e instanceof Error ? e.message : 'Не удалось выполнить скан.')
    }
  }

  const createInboundBox = async (): Promise<string | null> => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const res = await fetch(ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/boxes`), {
        method: 'POST',
        headers: ctx.authHeaders,
      })
      if (!res.ok) {
        ctx.setError(ctx.scanErrorMessageRu(await ctx.readApiErrorMessage(res)))
        return null
      }
      const box = (await res.json()) as { id: string }
      await ctx.loadDetail()
      ctx.setPackagesExpanded(true)
      return box.id
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось создать короб.')
      return null
    } finally {
      ctx.setBusy(false)
    }
  }

  const resolveDiscrepancyAct = async (actId: string, action: 'approve' | 'reject') => {
    ctx.setDiscrepancyActsBusy(true)
    ctx.setDiscrepancyActsError(null)
    try {
      const res = await fetch(ctx.apiUrl(`/operations/discrepancy-acts/${actId}/${action}`), {
        method: 'POST',
        headers: ctx.authHeaders,
      })
      if (!res.ok) {
        ctx.setDiscrepancyActsError(await ctx.readApiErrorMessage(res))
        return
      }
      await ctx.loadLinkedDiscrepancyActs()
      await ctx.loadDetail()
    } catch (e) {
      ctx.setDiscrepancyActsError(e instanceof Error ? e.message : 'Не удалось обработать акт.')
    } finally {
      ctx.setDiscrepancyActsBusy(false)
    }
  }

  const openBoxAddDialog = (boxId: string) => {
    ctx.setBoxAddDialogBoxId(boxId)
  }

  const handleCreateBox = async () => {
    await createInboundBox()
  }

  const createCargoPlaces = async () => {
    const count = Math.floor(Number(ctx.cargoCount))
    if (!Number.isFinite(count) || count < 1 || count > 1000) {
      ctx.setCargoError('Укажите количество грузомест от 1 до 1000.')
      return
    }
    ctx.setBusy(true)
    ctx.setCargoError(null)
    ctx.setError(null)
    try {
      const res = await fetch(ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/cargo-places`), {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity: count }),
      })
      if (!res.ok) {
        ctx.setCargoError(await ctx.readApiErrorMessage(res))
        return
      }
      ctx.setCargoDialogOpen(false)
      ctx.setCargoCount('1')
      ctx.setPackagesExpanded(true)
      await ctx.loadDetail()
    } catch (e) {
      ctx.setCargoError(e instanceof Error ? e.message : 'Не удалось создать грузоместа.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const deleteInboundBox = async (boxId: string) => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/boxes/${boxId}`),
        { method: 'DELETE', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setError(ctx.scanErrorMessageRu(await ctx.readApiErrorMessage(res)))
        return
      }
      if (ctx.boxAddDialogBoxId === boxId) {
        ctx.setBoxAddDialogBoxId(null)
      }
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось удалить короб.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const completeReceiving = async () => {
    ctx.setBusy(true)
    ctx.setError(null)
    ctx.setFinishConfirmOpen(false)
    try {
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/complete-receiving`),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setError(ctx.scanErrorMessageRu(await ctx.readApiErrorMessage(res)))
        return
      }
      ctx.setDetail((await res.json()) as InboundDetail)
      ctx.setDistOpen(true)
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось завершить приёмку.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const reopenReceiving = async () => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/reopen-receiving`),
        { method: 'POST', headers: ctx.authHeaders },
      )
      if (!res.ok) {
        ctx.setError(await ctx.readApiErrorMessage(res))
        return
      }
      ctx.setDistOpen(false)
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось открыть приёмку для редактирования.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const requestCompleteReceiving = () => {
    if (ctx.receivingTotals.hasAnyDiscrepancy) {
      ctx.setFinishConfirmOpen(true)
      return
    }
    void completeReceiving()
  }

  const setLineActual = async (lineId: string, actualQty: number) => {
    ctx.setBusy(true)
    ctx.setError(null)
    try {
      const res = await fetch(
        ctx.apiUrl(`/operations/inbound-intake-requests/${ctx.requestId}/lines/${lineId}/actual`),
        {
          method: 'PATCH',
          headers: { ...authHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ actual_qty: actualQty }),
        },
      )
      if (!res.ok) {
        const msg = await ctx.readApiErrorMessage(res)
        ctx.setError(msg === 'actual_missing' ? 'Укажите факт по всем строкам.' : msg)
        return
      }
      await ctx.loadDetail()
    } catch (e) {
      ctx.setError(e instanceof Error ? e.message : 'Не удалось сохранить факт.')
    } finally {
      ctx.setBusy(false)
    }
  }

  const saveManualLineActual = async (lineId: string, rawOverride?: string) => {
    const raw =
      rawOverride ??
      ctx.actualDraftRef.current[lineId] ??
      ctx.actualDraftByLineId[lineId]
    const validationError = integerQtyError(raw)
    if (validationError) {
      ctx.setActualDraftErrorByLineId((prev) => ({ ...prev, [lineId]: validationError }))
      ctx.setManualEditLineId(lineId)
      ctx.focusActualInput(lineId)
      return
    }
    const displayed = ctx.parseIntegerQty(raw)
    if (displayed == null) {
      return
    }
    const line = ctx.detail?.lines.find((ln) => ln.id === lineId)
    if (!line) {
      return
    }
    const boxes = ctx.detail?.boxes ?? []
    const currentEffective = ctx.effectiveActualQty(line, boxes, ctx.detail?.status)
    if (displayed === currentEffective) {
      ctx.setActualDraftErrorByLineId((prev) => ({ ...prev, [lineId]: '' }))
      ctx.setManualEditLineId(null)
      return
    }
    const loose = ctx.looseQtyFromDisplayedTotal(displayed, line, boxes)
    await setLineActual(lineId, loose)
    ctx.setActualDraftErrorByLineId((prev) => ({ ...prev, [lineId]: '' }))
    ctx.setManualEditLineId(null)
  }

  const hasUnsavedActualChange = useMemo(() => {
    if (!ctx.manualEditLineId || !ctx.detail) return false
    const line = ctx.detail.lines.find((ln) => ln.id === ctx.manualEditLineId)
    if (!line) return false
    const raw = ctx.actualDraftByLineId[ctx.manualEditLineId]
    if (raw == null) return false
    const current = String(ctx.effectiveActualQty(line, ctx.detail.boxes ?? [], ctx.detail.status))
    return raw.trim() !== current
  }, [ctx.actualDraftByLineId, ctx.detail, ctx.manualEditLineId])

  const handleSaveDocument = async () => {
    const manualEditLineId = ctx.manualEditLineId
    if (manualEditLineId) {
      const raw = ctx.actualDraftRef.current[manualEditLineId] ?? ctx.actualDraftByLineId[manualEditLineId] ?? ''
      const validationError = integerQtyError(raw)
      if (validationError) {
        ctx.setActualDraftErrorByLineId((prev) => ({ ...prev, [manualEditLineId]: validationError }))
        ctx.focusActualInput(manualEditLineId)
        return
      }
      await saveManualLineActual(manualEditLineId, raw)
    }
    ctx.setSaveSuccessMsg('Документ сохранён.')
  }

  const handleClose = () => {
    if (hasUnsavedActualChange) {
      ctx.setCloseConfirmOpen(true)
      return
    }
    ctx.onClose()
  }


  return {
    boxPrintTarget,
    setBoxPrintTarget,
    printInboundBoxLabel,
    printAllInboundBoxLabels,
    printInboundCargoPlaceLabel,
    printAllInboundCargoPlaceLabels,
    requestPrintInboundBox,
    requestPrintAllInboundBoxes,
    requestPrintInboundCargoPlace,
    requestPrintAllInboundCargoPlaces,
    confirmInboundBoxPrint,
    scanToReceiving,
    createInboundBox,
    resolveDiscrepancyAct,
    openBoxAddDialog,
    handleCreateBox,
    createCargoPlaces,
    deleteInboundBox,
    completeReceiving,
    reopenReceiving,
    requestCompleteReceiving,
    setLineActual,
    saveManualLineActual,
    hasUnsavedActualChange,
    handleSaveDocument,
    handleClose,
  }
}

export type FfInboundPackageActions = ReturnType<typeof useFfInboundPackageActions>
