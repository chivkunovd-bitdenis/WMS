import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../api'
import {
  productDisplayMetaFromCatalog,
  type ProductLineDisplayMeta,
  type WbProductCatalogRow,
} from '../types/wbProductCatalog'
import { readApiErrorMessage } from '../utils/readApiErrorMessage'

async function fetchWbProductCatalogRows(
  authHeaders: Record<string, string>,
  sellerId?: string | null,
): Promise<WbProductCatalogRow[]> {
  const qs =
    sellerId && sellerId.trim()
      ? `?seller_id=${encodeURIComponent(sellerId.trim())}`
      : ''
  const res = await fetch(apiUrl(`/products/linked-wb-catalog${qs}`), { headers: authHeaders })
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res))
  }
  return (await res.json()) as WbProductCatalogRow[]
}

type MetaSourceLine = { sku_code: string; product_name?: string; name?: string }

type UseWbProductCatalogResult = {
  catalog: WbProductCatalogRow[]
  catalogById: Map<string, WbProductCatalogRow>
  /**
   * Витрина строки товара с постоянной ссылкой на объект.
   *
   * `productDisplayMetaFromCatalog` в теле рендера создаёт новый объект на каждую
   * строку и каждый рендер, из-за чего `memo` на ячейках товара не срабатывает и
   * таблица на сотни строк перерисовывается целиком. На боевой приёмке из 276
   * строк это давало 15-20 секунд на один скан.
   *
   * Кэш живёт ровно столько, сколько неизменен каталог: витрина состоит из
   * атрибутов товара и не содержит количеств и статусов.
   */
  getDisplayMeta: (productId: string, line: MetaSourceLine) => ProductLineDisplayMeta
  loading: boolean
  error: string | null
  reload: () => Promise<WbProductCatalogRow[]>
}

export function useWbProductCatalog(
  token: string | null | undefined,
  enabled = true,
  sellerId?: string | null,
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
      const next = await fetchWbProductCatalogRows(authHeaders, sellerId)
      setRows(next)
      return next
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить каталог товаров.')
      setRows([])
      return []
    } finally {
      setLoading(false)
    }
  }, [authHeaders, sellerId])

  useEffect(() => {
    if (!enabled || !authHeaders) {
      return
    }
    void reload()
  }, [enabled, authHeaders, reload])

  const catalogById = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows])

  const getDisplayMeta = useMemo(() => {
    const cache = new Map<string, ProductLineDisplayMeta>()
    return (productId: string, line: MetaSourceLine): ProductLineDisplayMeta => {
      const hit = cache.get(productId)
      if (hit) {
        return hit
      }
      const meta = productDisplayMetaFromCatalog(productId, line, catalogById)
      cache.set(productId, meta)
      return meta
    }
  }, [catalogById])

  return { catalog: rows, catalogById, getDisplayMeta, loading, error, reload }
}
