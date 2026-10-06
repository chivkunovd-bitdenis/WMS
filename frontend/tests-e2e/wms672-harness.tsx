// Test-only Vite entry: all React imports go through the same dependency graph.
import React from 'react'
import { createRoot } from 'react-dom/client'
import { FfInboundRequestView } from '../src/screens/ff/FfInboundRequestView'
export { renderBarcodeDataUrl } from '../src/utils/renderBarcodeDataUrl'
export { printBarcodeLabels } from '../src/utils/printBarcodeLabel'
export { DEFAULT_LABEL_SIZE } from '../src/utils/labelSize'

export function mountInbound672(host: HTMLElement) {
  const root = createRoot(host)
  root.render(<FfInboundRequestView requestId="672-document" token={`synthetic.${btoa(JSON.stringify({tenant_id: "672-tenant", sub: "672-user"}))}.synthetic`}
    isFulfillmentAdmin numberedInboundBoxLabels onClose={() => {}} />)
  return root
}
