import { printDirectQr } from './printDirectQr'

export type PreparedQrInput = {
  imageDataUrl: string
  idempotencyKey: string
  widthMm: number
  heightMm: number
}

/** Direct OS queue receipt; no browser print dialog and no physical-paper claim. */
export function printPreparedQr(input: PreparedQrInput): Promise<void> {
  return printDirectQr(input)
}

export function dispatchPreparedQrForCheck(input: PreparedQrInput): Promise<void> {
  return printDirectQr(input)
}
