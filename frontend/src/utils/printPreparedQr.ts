import { printDirectQr } from './printDirectQr'

export type PreparedQrInput = {
  imageDataUrl: string
  idempotencyKey: string
  widthMm: number
  heightMm: number
  /** Executed when the native transport dequeues this copy, after all rendering. */
  beforeDispatch?: () => Promise<void>
}

/** Direct OS queue receipt; no browser print dialog and no physical-paper claim. */
export function printPreparedQr(input: PreparedQrInput): Promise<void> {
  return printDirectQr(input)
}

export function dispatchPreparedQrForCheck(input: PreparedQrInput): Promise<void> {
  return printDirectQr(input)
}

/** Compatibility with the concurrent WMS-604 screen: this now uses the native
 * receipt too; Chrome kiosk flags are no longer involved. */
export function dispatchPreparedQrInKiosk(input: PreparedQrInput): Promise<void> {
  return printDirectQr(input)
}
