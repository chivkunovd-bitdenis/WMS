import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../api'
import type { WbProductCatalogRow } from '../types/wbProductCatalog'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'

async function fetchWbProductCatalogRows(
  authHeaders: Record<string, string>,
): Promise<WbProductCatalogRow[]> {
  const res = await fetch(apiUrl('/products/linked-wb-catalog'), { headers: authHeaders })
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  return (await res.json()) as WbProductCatalogRow[]
}

type UseWbProductCatalogResult = {
  catalogById: Map<string, WbProductCatalogRow>
  loading: boolean
  error: string | null
  reload: () => Promise<void>
}

export function useWbProductCatalog(
  token: string | null | undefined,
  enabled = true,
): UseWbProductCatalogResult {
  const [rows, setRows] = useState<WbProductCatalogRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const authHeaders = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : null),
    [token],
  )

  const reload = useCallback(async () => {
    if (!authHeaders) {
      setRows([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      setRows(await fetchWbProductCatalogRows(authHeaders))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог товаров.')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [authHeaders])

  useEffect(() => {
    if (!enabled || !authHeaders) {
      return
    }
    void reload()
  }, [enabled, authHeaders, reload])

  const catalogById = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows])

  return { catalogById, loading, error, reload }
}
