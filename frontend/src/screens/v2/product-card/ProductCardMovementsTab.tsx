import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Stack } from '@mui/material'
import { apiUrl } from '../../../api'
import { readApiErrorMessage } from '../../../utils/readApiErrorMessage'
import { ErrorNotice, SecondaryAction } from '../../../ui-kit'
import { ProductMovementsTable } from '../../../components/ProductMovementsTable'
import type { MovementRow } from '../../../components/ProductMovementsTable'

// Кусок D4 (WMS-490): вкладка «Движения» — та же таблица и та же серверная
// функция, что у отчёта «Остатки и движения» (WMS-531), но без периода — вся
// история одного товара (`GET /reports/inventory/product-movements`, кусок
// D2). «Загрузить ещё» догружает страницы по MOVEMENT_PAGE_LIMIT (R9);
// пока идёт загрузка, повторное нажатие ничего не делает — иначе страница
// уехала бы вперёд и часть движений пропала бы или задвоилась.
type Props = {
  productId: string
  token: string
  authHeaders: (t: string) => Record<string, string>
  /** Товара с таким id больше нет — вкладка должна уметь сообщить об этом наверх (R16). */
  onNotFound: () => void
  /** Открыть документ приёмки по ссылке в строке движения — как у отчёта «Остатки и движения». */
  onOpenInbound?: (id: string) => void
}

type MovementsPage = {
  rows?: MovementRow[]
  truncated?: boolean
  total?: number
  page?: number
}

export function ProductCardMovementsTab({ productId, token, authHeaders, onNotFound, onOpenInbound }: Props) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [rows, setRows] = useState<MovementRow[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState(false)
  // Следующая страница, которую нужно запросить — не состояние: пока она
  // обновилась бы только на следующий рендер, «Загрузить ещё» могла бы
  // успеть уйти дважды с одним и тем же номером страницы.
  const nextPageRef = useRef(1)
  // Единственный синхронный флаг «идёт запрос» — им же ловится двойное
  // нажатие внутри одного события, до которого React ещё не перерисовал
  // задизейбленную кнопку (R9).
  const loadingRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)

  const fetchPage = useCallback(
    async (requestedPage: number, signal: AbortSignal): Promise<MovementsPage> => {
      const params = new URLSearchParams({ product_id: productId, page: String(requestedPage) })
      const res = await fetch(apiUrl(`/reports/inventory/product-movements?${params.toString()}`), {
        headers: { ...authHeaders(token) },
        signal,
      })
      if (res.status === 404) {
        if (!signal.aborted) onNotFound()
        throw new DOMException('product not found', 'AbortError')
      }
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      return (await res.json()) as MovementsPage
    },
    [authHeaders, onNotFound, productId, token],
  )

  const loadFirst = useCallback(() => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    loadingRef.current = true
    setStatus('loading')
    setRows([])
    setHasMore(false)
    setMoreError(false)
    nextPageRef.current = 1
    fetchPage(1, controller.signal)
      .then((body) => {
        if (controller.signal.aborted) return
        setRows(body.rows ?? [])
        setHasMore(Boolean(body.truncated))
        nextPageRef.current = (body.page ?? 1) + 1
        setStatus('ready')
      })
      .catch((e) => {
        if (controller.signal.aborted || (e as { name?: string }).name === 'AbortError') return
        setStatus('error')
      })
      .finally(() => {
        if (abortRef.current === controller) loadingRef.current = false
      })
  }, [fetchPage])

  useEffect(() => {
    loadFirst()
    return () => {
      abortRef.current?.abort()
      loadingRef.current = false
    }
    // Товар сменился (другая карточка) — перечитать с первой страницы.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId])

  const loadMore = useCallback(() => {
    if (loadingRef.current || !hasMore) return
    loadingRef.current = true
    setLoadingMore(true)
    setMoreError(false)
    const controller = new AbortController()
    const requestedPage = nextPageRef.current
    fetchPage(requestedPage, controller.signal)
      .then((body) => {
        setRows((current) => [...current, ...(body.rows ?? [])])
        setHasMore(Boolean(body.truncated))
        nextPageRef.current = (body.page ?? requestedPage) + 1
      })
      .catch((e) => {
        if ((e as { name?: string }).name === 'AbortError') return
        setMoreError(true)
      })
      .finally(() => {
        loadingRef.current = false
        setLoadingMore(false)
      })
  }, [fetchPage, hasMore])

  if (status === 'error') {
    return (
      <ErrorNotice testId="product-card-movements-error">
        Не удалось загрузить движения.{' '}
        <Button size="small" onClick={loadFirst} data-testid="product-card-movements-retry">
          Повторить
        </Button>
      </ErrorNotice>
    )
  }

  return (
    <Stack spacing={1} data-testid="product-card-movements-tab">
      <ProductMovementsTable
        rows={rows}
        loading={status === 'loading'}
        onOpenInbound={onOpenInbound}
        emptyTitle="Движений нет"
        testId="product-card-movements"
      />
      {moreError ? (
        <ErrorNotice testId="product-card-movements-more-error">Не удалось загрузить ещё движения.</ErrorNotice>
      ) : null}
      {hasMore ? (
        <SecondaryAction
          disabledReason={loadingMore ? 'Загрузка движений' : undefined}
          onClick={loadMore}
          data-testid="product-card-movements-load-more"
        >
          Загрузить ещё
        </SecondaryAction>
      ) : null}
    </Stack>
  )
}
