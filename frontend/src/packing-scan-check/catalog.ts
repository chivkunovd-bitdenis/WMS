export const TEST_LABELS = Array.from({ length: 10 }, (_, index) => ({
  barcode: `290000000${String(index + 1).padStart(4, '0')}`,
  qr: `WMS-PRINT-TEST-${String(index + 1).padStart(2, '0')}`,
}))

export function findTestLabel(raw: string) {
  return TEST_LABELS.find((label) => label.barcode === raw.trim())
}
