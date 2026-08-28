import { apiUrl } from '../../api'
import { printBarcodeLabel } from '../../utils/printBarcodeLabel'
import { printInboundReceivingSheet } from '../../utils/printInboundReceivingSheet'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { renderBarcodeDataUrl } from '../../utils/renderBarcodeDataUrl'
import { resolveProductIdByBarcode } from '../../utils/resolveProductByBarcode'
import { suggestNextLocationCode } from '../../utils/suggestNextLocationCode'
import { formatHumanDocumentNumber } from './documentDisplay'
import { findInboundScanProductId } from './inboundScanLookup'
import {
  effectiveActualQty,
  inboundStatusRu,
  looseQtyFromDisplayedTotal,
  parseIntegerQty,
  scanErrorMessageRu,
} from './inboundReceivingHelpers'
import { applyScannedInboundLine } from './inboundReceivingRuntime'
import type { FfInboundRequestData, FfInboundRequestDataContext } from './useFfInboundRequestData'

export type FfInboundRequestActionContext = FfInboundRequestDataContext & FfInboundRequestData & {
  apiUrl: typeof apiUrl
  readApiErrorMessage: typeof readApiErrorMessage
  parseIntegerQty: typeof parseIntegerQty
  looseQtyFromDisplayedTotal: typeof looseQtyFromDisplayedTotal
  suggestNextLocationCode: typeof suggestNextLocationCode
  resolveProductIdByBarcode: typeof resolveProductIdByBarcode
  printBarcodeLabel: typeof printBarcodeLabel
  renderBarcodeDataUrl: typeof renderBarcodeDataUrl
  printInboundReceivingSheet: typeof printInboundReceivingSheet
  inboundStatusRu: typeof inboundStatusRu
  effectiveActualQty: typeof effectiveActualQty
  scanErrorMessageRu: typeof scanErrorMessageRu
  findInboundScanProductId: typeof findInboundScanProductId
  applyScannedInboundLine: typeof applyScannedInboundLine
  formatHumanDocumentNumber: typeof formatHumanDocumentNumber
}
