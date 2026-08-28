import { useBarcodeScanner } from '../../hooks/useBarcodeScanner'

type FfInboundRequestScannerProps = {
  receivingEnabled: boolean
  draftEnabled: boolean
  onReceivingScan: (code: string) => void
  onDraftScan: (code: string) => void
}

export function useFfInboundRequestScanner({
  receivingEnabled,
  draftEnabled,
  onReceivingScan,
  onDraftScan,
}: FfInboundRequestScannerProps) {
  useBarcodeScanner({
    enabled: receivingEnabled,
    onScan: onReceivingScan,
  })
  useBarcodeScanner({
    enabled: draftEnabled,
    onScan: onDraftScan,
  })
}
