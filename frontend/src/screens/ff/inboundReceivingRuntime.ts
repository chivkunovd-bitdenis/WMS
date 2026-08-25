export function applyScannedInboundLine<T extends { id: string }>(
  lines: T[],
  scannedLine: T,
): T[] {
  const exists = lines.some((line) => line.id === scannedLine.id)
  return exists
    ? lines.map((line) => (line.id === scannedLine.id ? scannedLine : line))
    : [...lines, scannedLine]
}

export function createDebouncedInboundReconciler(
  reload: () => Promise<unknown>,
  delayMs = 2500,
) {
  let timer: ReturnType<typeof setTimeout> | null = null
  return {
    schedule(): void {
      if (timer !== null) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = null
        void reload().catch(() => undefined)
      }, delayMs)
    },
    cancel(): void {
      if (timer !== null) clearTimeout(timer)
      timer = null
    },
  }
}

export function isLatestScannedInboundLine(
  lineId: string,
  lastScannedLineId: string | null,
): boolean {
  return lineId === lastScannedLineId
}

export function createSerialScanQueue() {
  let tail = Promise.resolve()
  return (scan: () => Promise<void>): Promise<void> => {
    const next = tail.then(scan, scan)
    tail = next.catch(() => undefined)
    return next
  }
}
