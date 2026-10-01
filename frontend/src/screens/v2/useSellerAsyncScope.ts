import { useCallback, useEffect, useRef } from 'react'

// Cancels only this screen's requests/observation, never the server-side job.
export function useSellerAsyncScope(token: string) {
  const active = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    active.current = controller
    return () => {
      controller.abort()
      active.current = null
    }
  }, [token])
  return useCallback(() => {
    const controller = active.current
    return {
      signal: controller?.signal,
      isCurrent: () => controller !== null && active.current === controller && !controller.signal.aborted,
    }
  }, [token])
}
