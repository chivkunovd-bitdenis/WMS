export type LatestRequestSequence = {
  next: () => number
  invalidate: () => void
  isLatest: (requestId: number) => boolean
}

export function createLatestRequestSequence(): LatestRequestSequence {
  let current = 0
  return {
    next: () => {
      current += 1
      return current
    },
    invalidate: () => {
      current += 1
    },
    isLatest: (requestId: number) => requestId === current,
  }
}
