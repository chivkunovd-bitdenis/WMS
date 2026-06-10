import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../api'
import type { WbProductCatalogRow } from '../types/wbProductCatalog'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'

async function fetchWbProductCatalogRows(
  authHeaders: Record<string, string>,
): Promise<WbProductCatalogRow[]> {
  const [productsRes, ffRes] = await Promise.all([
    fetch(apiUrl('/products'), { headers: authHeaders }),
    fetch(apiUrl('/products/ff-catalog'), { headers: authHeaders }),
  ])
  if (!productsRes.ok) {
    throw new Error(await readApiErrorMessage(productsRes))
  }
  const products = (await productsRes.json()) as {
    id: string
    name: string
    sku_code: string
    wb_nm_id?: number | null
    wb_vendor_code?: string | null
  }[]
  const ffRows = ffRes.ok ? ((await ffRes.json()) as WbProductCatalogRow[]) : []
  const ffById = new Map(ffRows.map((r) => [r.id, r]))
  return products.map((p) => {
    const ff = ffById.get(p.id)
    if (ff) {
      return ff
    }
    return {
      id: p.id,
      name: p.name,
      sku_code: p.sku_code,
      wb_nm_id: p.wb_nm_id ?? null,
      wb_vendor_code: p.wb_vendor_code ?? null,
      wb_subject_name: null,
      wb_primary_image_url: null,
      wb_barcodes: [],
      wb_primary_barcode: null,
    }
  })
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
