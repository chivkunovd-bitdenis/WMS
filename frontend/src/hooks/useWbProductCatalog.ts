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
  catalog: WbProductCatalogRow[]
  catalogById: Map<string, WbProductCatalogRow>
  loading: boolean
  error: string | null
  reload: () => Promise<WbProductCatalogRow[]>
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
      return []
    }
    setLoading(true)
    setError(null)
    try {
      const next = await fetchWbProductCatalogRows(authHeaders)
      setRows(next)
      return next
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог товаров.')
      setRows([])
      return []
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

  return { catalog: rows, catalogById, loading, error, reload }
}
