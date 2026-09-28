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
  /**
   * Растёт после успешного изменения остатка (проведённый пересчёт, «Задать
   * остаток» и т. п.) — сигнал перечитать журнал с первой страницы, сбросив
   * загруженные порции (WMS-490 ревью Astra №1, F1). Диалог карточки передаёт
   * его во все вкладки; пока конкретная сборка диалога его не присылает,
   * значение не приходит вовсе и поведение вкладки не меняется.
   */
  stockVersion?: number
  /**
   * Вкладка сейчас выбрана в карточке (видна оператору). Возврат на вкладку
   * после сбоя загрузки повторяет её — иначе оператор должен был бы сам
   * найти кнопку «Повторить» на вкладке, которую до этого не видел (F1).
   * Без этого пропа поведение то же, что раньше.
   */
  active?: boolean
}

type MovementsPage = {
  rows?: MovementRow[]
  truncated?: boolean
  total?: number
  page?: number
  /**
   * Верхняя граница набора (`created_at`), зафиксированная сервером на
   * первой странице (WMS-490 ревью Astra №1, F5). Без периода OFFSET
   * неустойчив к новым движениям между запросами страниц: приёмка или
   * инвентаризация сдвигает выборку — последняя строка первой страницы
   * приходит на второй ещё раз, а действительно новая строка вообще не
   * загружается. Каждая следующая страница обязана прислать это же
   * значение назад; перечитывание с первой страницы снимает его и получает
   * новый снимок.
   */
  before?: string
}

export function ProductCardMovementsTab({
  productId,
  token,
  authHeaders,
  onNotFound,
  onOpenInbound,
  stockVersion,
  active,
}: Props) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [rows, setRows] = useState<MovementRow[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState(false)
  // Следующая страница, которую нужно запросить — не состояние: пока она
  // обновилась бы только на следующий рендер, «Загрузить ещё» могла бы
  // успеть уйти дважды с одним и тем же номером страницы.
  const nextPageRef = useRef(1)
  // Снимок верхней границы набора для текущей серии страниц (F5) — тоже не
  // состояние: нужен синхронно внутри `loadMore`, а не только на следующий рендер.
  const beforeRef = useRef<string | null>(null)
  // Единственный синхронный флаг «идёт запрос» — им же ловится двойное
  // нажатие внутри одного события, до которого React ещё не перерисовал
  // задизейбленную кнопку (R9).
  const loadingRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  // Последнее увиденное значение stockVersion — чтобы отличить «пришло
  // впервые при монтировании» (перечитывать не нужно, это уже сделает
  // эффект по productId) от «изменилось после успешной записи» (F1).
  const stockVersionRef = useRef(stockVersion)
  // Текущий статус, доступный синхронно внутри эффекта реактивации (F1) —
  // без рефа пришлось бы держать `status` в зависимостях эффекта и он бы
  // срабатывал на каждый переход в error, а не только на возврат на вкладку.
  const statusRef = useRef(status)
  statusRef.current = status

  const fetchPage = useCallback(
    async (requestedPage: number, signal: AbortSignal, before: string | null): Promise<MovementsPage> => {
      const params = new URLSearchParams({ product_id: productId, page: String(requestedPage) })
      if (before) params.set('before', before)
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
    beforeRef.current = null
    fetchPage(1, controller.signal, null)
      .then((body) => {
        if (controller.signal.aborted) return
        setRows(body.rows ?? [])
        setHasMore(Boolean(body.truncated))
        nextPageRef.current = (body.page ?? 1) + 1
        beforeRef.current = body.before ?? null
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

  // F1: остаток изменился где-то в карточке (пересчёт в «Расположении»,
  // сохранение в «Задать остаток») — журнал устарел, перечитываем его с
  // первой страницы новым снимком, даже если сейчас на вкладке не смотрят.
  useEffect(() => {
    if (stockVersion === undefined) return
    if (stockVersionRef.current === stockVersion) return
    stockVersionRef.current = stockVersion
    loadFirst()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stockVersion])

  // F1: вернулись на вкладку после сбоя загрузки — повторяем её сами, а не
  // ждём, что оператор станет искать кнопку «Повторить» на вкладке, которую
  // только что открыл заново. Срабатывает именно на переход `active`, а не
  // на сам факт ошибки — обычная активная вкладка после сбоя ждёт нажатия
  // кнопки, как и раньше.
  useEffect(() => {
    if (!active) return
    if (statusRef.current !== 'error') return
    loadFirst()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])

  const loadMore = useCallback(() => {
    if (loadingRef.current || !hasMore) return
    loadingRef.current = true
    setLoadingMore(true)
    setMoreError(false)
    const controller = new AbortController()
    const requestedPage = nextPageRef.current
    const before = beforeRef.current
    fetchPage(requestedPage, controller.signal, before)
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
