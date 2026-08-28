import { createElement } from 'react'
import { apiUrl } from '../../api'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { findInboundScanProductId } from './inboundScanLookup'
import { effectiveActualQty, looseQtyFromDisplayedTotal, parseIntegerQty, scanErrorMessageRu, inboundStatusRu } from './inboundReceivingHelpers'
import { printInboundReceivingSheet } from '../../utils/printInboundReceivingSheet'
import { suggestNextLocationCode } from '../../utils/suggestNextLocationCode'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'
import { resolveProductIdByBarcode } from '../../utils/resolveProductByBarcode'
import { formatHumanDocumentNumber } from './documentDisplay'
import { applyScannedInboundLine } from './inboundReceivingRuntime'
import { FfInboundRequestViewBody } from './FfInboundRequestViewBody'
import { useFfInboundDistributionActions } from './FfInboundRequestDistributionActions'
import { useFfInboundReceivingActions } from './FfInboundRequestReceivingActions'
import { useFfInboundPackageActions } from './FfInboundRequestPackageActions'
import { type FfInboundRequestViewProps } from './FfInboundRequestViewTypes'

import { useFfInboundRequestState } from './useFfInboundRequestState'
import { useFfInboundRequestData } from './useFfInboundRequestData'
import { useFfInboundRequestScanner } from './useFfInboundRequestScanner'

// data-testid="ff-inbound-doc-error" remains part of the document scroll contract;
// its query lives in useFfInboundRequestData.ts after the mechanical split.

export function useFfInboundRequestController(props: FfInboundRequestViewProps) {
  const normalizedProps = {
    ...props,
    workspace: props.workspace ?? 'full',
    addressStorageEnabled: props.addressStorageEnabled ?? true,
  }
  const state = useFfInboundRequestState(normalizedProps)
  let scanToReceiving: ((code?: string) => Promise<void>) | null = null
  let addLineByBarcode: ((code?: string) => Promise<void>) | null = null
  useFfInboundRequestScanner({
    receivingEnabled:
      normalizedProps.isFulfillmentAdmin &&
      !state.sortingView &&
      state.receivingActive &&
      state.boxAddDialogBoxId == null &&
      !state.pickerOpen &&
      state.dimensionsLine == null,
    draftEnabled:
      normalizedProps.isFulfillmentAdmin &&
      !state.sortingView &&
      state.detail?.status === 'draft' &&
      state.boxAddDialogBoxId == null &&
      !state.pickerOpen &&
      state.dimensionsLine == null,
    onReceivingScan: (code) => {
      const handler = scanToReceiving
      if (handler) {
        void state.receivingScanQueue(() => handler(code))
      }
    },
    onDraftScan: (code) => {
      const handler = addLineByBarcode
      if (handler) {
        void handler(code)
      }
    },
  })
  const data = useFfInboundRequestData({ ...normalizedProps, ...state })
  const actionContext = { ...normalizedProps, ...state, ...data, apiUrl, readApiErrorMessage, parseIntegerQty, looseQtyFromDisplayedTotal, suggestNextLocationCode, resolveProductIdByBarcode, printBarcodeLabel, renderBarcodeDataUrl, printInboundReceivingSheet, inboundStatusRu, effectiveActualQty, scanErrorMessageRu, findInboundScanProductId, applyScannedInboundLine, formatHumanDocumentNumber }
  const distribution = useFfInboundDistributionActions(actionContext)
  const receiving = useFfInboundReceivingActions({ ...actionContext, ...distribution })
  const packages = useFfInboundPackageActions({ ...actionContext, ...distribution, ...receiving })
  scanToReceiving = packages.scanToReceiving
  addLineByBarcode = receiving.addLineByBarcode
  const boxes = [...(state.detail?.boxes ?? [])].sort((a, b) => a.box_number - b.box_number)
  const cargoPlaces = [...(state.detail?.cargo_places ?? [])].sort((a, b) => a.place_number - b.place_number)
  const boxAddDialogBox = boxes.find((box) => box.id === state.boxAddDialogBoxId) ?? null
  const actualEditable = normalizedProps.isFulfillmentAdmin && state.receivingActive
  const hasPostedPartial = (state.detail?.lines ?? []).some((line) => (line.posted_qty ?? 0) > 0)
  const canReopenReceiving = normalizedProps.isFulfillmentAdmin && !state.sortingView && state.detail != null && state.receptionClosed && !hasPostedPartial
  return { ...normalizedProps, ...state, ...data, ...distribution, ...receiving, ...packages, boxes, cargoPlaces, boxAddDialogBox, actualEditable, hasPostedPartial, canReopenReceiving }
}

export type FfInboundRequestController = ReturnType<typeof useFfInboundRequestController>

export function FfInboundRequestView(props: FfInboundRequestViewProps) {
  const controller = useFfInboundRequestController(props)
  return createElement(FfInboundRequestViewBody, { controller })
}
