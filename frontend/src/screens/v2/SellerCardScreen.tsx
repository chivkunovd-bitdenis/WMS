import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link as RouterLink, useParams } from 'react-router-dom'
import { Box, Button, IconButton, Paper, Skeleton, Stack, Typography } from '@mui/material'
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined'
import { apiUrl } from '../../api'
import { ActionGroup, EmptyState, ErrorNotice } from '../../ui-kit'
import { PageHeader } from '../../ui/PageHeader'
import { sellerWbStatusLabel } from '../../utils/sellerWbStatus'
import { FfBillingProfilesDialog } from '../ff/FfBillingProfilesDialog'
import { FfBillingInvoicesPanel, profileRows, type ProfileSnapshot } from '../ff/FfBillingInvoicesPanel'

/**
 * Карточка селлера (WMS-491). Реквизиты, выставленные ему счета и переходы
 * к его товарам и к «Расчётам» — вместо кнопки «Реквизиты», которая раньше
 * жила в строке списка «Селлеры» (список — `SellersScreen.tsx`).
 */

export type SellerCardRow = {
  id: string
  name: string
  wb_has_key?: boolean
  wb_marketplace_scope_ok?: boolean | null
  ozon_connected?: boolean | null
}

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  /** Уже загруженный в App.tsx список — обычный переход из «Селлеры» находит
      селлера в нём мгновенно, без лишнего запроса. */
  sellers: SellerCardRow[]
}

/**
 * Блок «Реквизиты» карточки: те же подписи полей, что в открытом счёте
 * («Расчёты» → «Выставленные счета» → открытый счёт), значения — без него не
 * дублируем текст подписи руками ещё в одном месте.
 */
export function SellerRequisitesBlock({ profile }: { profile: ProfileSnapshot | null | undefined }) {
  if (profile === undefined) {
    return <Skeleton height={72} data-testid="seller-card-requisites-loading" />
  }
  if (!profile) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="seller-card-requisites-empty">
        Не заполнены
      </Typography>
    )
  }
  return (
    <Stack spacing={0.5} data-testid="seller-card-requisites-filled">
      {profileRows(profile, '').map(([label, value]) => (
        <Typography key={label} variant="body2">
          {label}: {value}
        </Typography>
      ))}
    </Stack>
  )
}

/**
 * Обёртка держит страницу закреплённой за одним `sellerId`.
 *
 * Внутри одного и того же маршрута `/app/ff/sellers/:sellerId` React не
 * пересоздаёт компонент при смене только параметра — предыдущий экземпляр
 * (со всем его состоянием: окно реквизитов, загруженный профиль, панель
 * счетов) просто получает новые пропсы. Перекрёстное ревью нашло на этом
 * реальный дефект (WMS-491 F1): открыли селлера A, перешли к B, вернулись по
 * истории браузера сразу на A — открытое окно «Реквизиты» продолжало слать
 * запросы к B под заголовком A, и сохранение уходило не тому селлеру.
 *
 * `key={sellerId}` — самый прямой способ сказать React «это другая
 * страница»: при смене id всё поддерево (карточка, окно реквизитов, панель
 * счетов) размонтируется и создаётся заново с чистым состоянием, как раньше
 * была устроена строка списка со своим `key={s.id}`. Точечные защиты внутри
 * (F4/F5 ниже) остаются — этот ключ не отменяет гонку двух ответов одного и
 * того же селлера, только гонку между разными селлерами.
 */
export function SellerCardScreen(props: Props) {
  const { sellerId } = useParams<{ sellerId: string }>()
  return <SellerCardScreenForSeller key={sellerId ?? 'none'} {...props} />
}

function SellerCardScreenForSeller({ token, authHeaders, sellers }: Props) {
  const { sellerId } = useParams<{ sellerId: string }>()

  const fromList = useMemo(() => sellers.find((s) => s.id === sellerId) ?? null, [sellers, sellerId])
  // Список «Селлеры» уже загружен почти всегда (переход из него) — тогда
  // селлер находится сразу. Прямое открытие адреса может опередить загрузку
  // общего списка в App.tsx: тогда список ещё пуст, и карточка спрашивает
  // тот же `GET /sellers` сама, чтобы отличить «ещё грузится» от «не найден».
  // Отдельное состояние `error` (WMS-491 F5) — сбой этого запроса не должен
  // выглядеть как «селлера не существует»: это разные сообщения пользователю.
  const [ownFetchStatus, setOwnFetchStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [ownFetchSeller, setOwnFetchSeller] = useState<SellerCardRow | null>(null)

  useEffect(() => {
    if (fromList || sellers.length > 0 || !sellerId) {
      return
    }
    let cancelled = false
    setOwnFetchStatus('loading')
    fetch(apiUrl('/sellers'), { headers: authHeaders(token) })
      .then((res) => (res.ok ? (res.json() as Promise<SellerCardRow[]>) : Promise.reject(new Error('sellers'))))
      .then((data) => {
        if (cancelled) return
        setOwnFetchSeller(data.find((s) => s.id === sellerId) ?? null)
        setOwnFetchStatus('done')
      })
      .catch(() => {
        if (!cancelled) {
          setOwnFetchStatus('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [authHeaders, fromList, sellerId, sellers.length, token])

  const seller = fromList ?? ownFetchSeller
  const isLoading = !fromList && sellers.length === 0 && (ownFetchStatus === 'idle' || ownFetchStatus === 'loading')
  const loadError = !fromList && sellers.length === 0 && ownFetchStatus === 'error'
  const notFound = !seller && !isLoading && !loadError

  const [profile, setProfile] = useState<ProfileSnapshot | null | undefined>(undefined)
  const [profileError, setProfileError] = useState(false)
  // WMS-491 F4: более старый запрос может завершиться позже нового (сразу
  // после сохранения карточка перечитывает профиль, а до этого мог висеть
  // предыдущий запрос с устаревшим снимком). Побеждает только последний
  // начатый запрос — остальные ответы, включая ошибочные, молча отбрасываются.
  // Ревью №2: `fetch` разрешается раньше, чем прочитано тело ответа —
  // проверку актуальности нужно повторить сразу перед каждым `setProfile`/
  // `setProfileError`, после `await res.json()`, а не только сразу после
  // `await fetch(...)`; иначе тело более старого ответа успевает прийти уже
  // после нового запроса и всё равно затирает актуальные данные.
  const profileRequestRef = useRef(0)

  const loadProfile = useCallback(async () => {
    if (!sellerId) return
    const requestId = ++profileRequestRef.current
    try {
      const res = await fetch(apiUrl(`/billing/profiles/sellers/${sellerId}`), {
        headers: authHeaders(token),
      })
      if (!res.ok) {
        // Сбой чтения — не то же самое, что «реквизитов нет» (F5): прежние
        // показанные данные не трогаем, просто сообщаем о сбое отдельно.
        if (requestId === profileRequestRef.current) setProfileError(true)
        return
      }
      const data = (await res.json()) as ProfileSnapshot | null
      if (requestId !== profileRequestRef.current) return
      setProfileError(false)
      setProfile(data)
    } catch {
      if (requestId === profileRequestRef.current) setProfileError(true)
    }
  }, [authHeaders, sellerId, token])

  useEffect(() => {
    if (!seller) return
    void loadProfile()
  }, [seller, loadProfile])

  if (!sellerId) {
    return null
  }

  return (
    <Stack spacing={2} data-testid="seller-card-page">
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <IconButton
          component={RouterLink}
          to="/app/ff/sellers"
          aria-label="Назад к списку"
          data-testid="seller-card-back"
          sx={{ mt: 0.5 }}
        >
          <ArrowBackOutlined />
        </IconButton>
        <Box sx={{ flex: 1, minWidth: 240 }}>
          <PageHeader title={seller?.name ?? (isLoading ? 'Загрузка…' : 'Селлер')} />
        </Box>
        {seller ? (
          <ActionGroup>
            <FfBillingProfilesDialog
              token={token}
              sellerId={seller.id}
              sellerName={seller.name}
              wbConnected={Boolean(seller.wb_has_key)}
              ozonConnected={Boolean(seller.ozon_connected)}
              onSaved={() => void loadProfile()}
            />
            <Button
              component={RouterLink}
              to={`/app/ff/products?seller_id=${seller.id}`}
              variant="outlined"
              size="small"
              data-testid="seller-card-open-products"
            >
              Товары
            </Button>
            <Button
              component={RouterLink}
              to={`/app/ff/billing?seller_id=${seller.id}`}
              variant="outlined"
              size="small"
              data-testid="seller-card-open-billing"
            >
              Выставить счёт
            </Button>
          </ActionGroup>
        ) : null}
      </Stack>

      {isLoading ? <Skeleton height={120} data-testid="seller-card-loading" /> : null}
      {loadError ? (
        <ErrorNotice testId="seller-card-load-error">
          Не удалось проверить селлера. Обновите страницу или повторите позже.
        </ErrorNotice>
      ) : null}
      {notFound ? <EmptyState title="Селлер не найден." testId="seller-card-not-found" /> : null}

      {seller ? (
        <>
          <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap' }} data-testid="seller-card-status">
            <Typography variant="body2" data-testid="seller-card-wb-status">
              WB Marketplace: {sellerWbStatusLabel(seller)}
            </Typography>
            <Typography variant="body2" data-testid="seller-card-ozon-status">
              Ozon: {seller.ozon_connected ? 'Подключён' : 'Не подключён'}
            </Typography>
          </Stack>

          <Paper variant="outlined" sx={{ p: 2 }} data-testid="seller-card-requisites">
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Реквизиты
            </Typography>
            {profileError ? (
              <ErrorNotice testId="seller-card-requisites-error">
                Не удалось загрузить реквизиты. Обновите страницу или повторите позже.
              </ErrorNotice>
            ) : (
              <SellerRequisitesBlock profile={profile} />
            )}
          </Paper>

          <Box data-testid="seller-card-invoices">
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Выставленные счета
            </Typography>
            <FfBillingInvoicesPanel token={token} fixedSellerId={seller.id} />
          </Box>
        </>
      ) : null}
    </Stack>
  )
}
