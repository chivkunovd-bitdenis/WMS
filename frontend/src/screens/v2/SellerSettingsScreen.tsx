import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { apiUrl } from '../../api'
import { useSellerAsyncScope } from './useSellerAsyncScope'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { sellerStaffError, sellerStaffRequest } from '../../utils/sellerStaffRequest'
import {
  SELLER_PERMISSION_BLOCKS,
  type SellerPermissions,
} from '../../utils/sellerPermissions'
import {
  hasAnySellerCatalogCards,
  shouldOpenCatalogSelectionAfterKeySave,
  SellerCatalogSelectionDialog,
  type SellerCatalogMarketplace,
} from './SellerCatalogSelectionDialog'
import {
  describeImportStage,
  catalogImportError,
  extractCatalogJobId,
  extractCatalogJobInitialStage,
  observeImportJob,
  parseCatalogSyncResponse,
  type ImportJobStage,
} from './sellerCatalogImportProgress'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  permissions: SellerPermissions
  me?: { display_name: string; full_name?: string | null; job_title?: string | null }
  onProfileUpdated?: (profile: { full_name: string; job_title: string }) => Promise<unknown>
  onStaffChanged?: () => void | Promise<void>
}

type MarkingCredentialsState = {
  has_cz_token: boolean
  has_suz_oms_token: boolean
  has_mp_api_key: boolean
  marketplace: string | null
  mchd_id: string | null
  mchd_valid_until: string | null
  signing_method: string
  edo_route: string
  auto_introduce: boolean
  auto_emit_limit: number | null
}

type SellerStaffAccountRow = {
  id: string
  email: string | null
  full_name?: string | null
  job_title?: string | null
  display_name: string
  role: string
  seller_id: string
  must_set_password: boolean
  is_owner: boolean
  permissions: SellerPermissions
}

type OzonAccountStatus = {
  marketplace: 'ozon'
  connected: boolean
  live_exchange_enabled?: boolean
  validation_status: 'not_configured' | 'valid' | 'invalid' | 'unavailable'
  last_validated_at: string | null
  last_validation_error: string | null
  credentials_updated_at: string | null
  last_synced_at: string | null
  last_sync_error: string | null
}

export function resolveOzonAccountDisplay(status: Pick<OzonAccountStatus, 'connected' | 'validation_status' | 'live_exchange_enabled'> | null) {
  if (!status?.connected) return { label: 'Не подключено', exchangeDisabled: false }
  if (status.validation_status !== 'valid') {
    return {
      label: status.validation_status === 'invalid' ? 'Подключение требует проверки' : 'Проверка подключения недоступна',
      exchangeDisabled: false,
    }
  }
  return {
    label: status.live_exchange_enabled === true
      ? 'Подключено, обмен включён'
      : status.live_exchange_enabled === false
        ? 'Ключ принят, обмен не включён'
        : 'Ключ принят',
    exchangeDisabled: status.live_exchange_enabled === false,
  }
}

const DEFAULT_STAFF_PERMISSIONS: SellerPermissions = {
  documents: true,
  products: true,
  honest_sign: true,
  settings: false,
  staff: false,
}

const SIGNING_OPTIONS = [
  { value: 'manual', label: 'Вручную в кабинете' },
  { value: 'ff_kep_mchd', label: 'КЭП фулфилмента + МЧД' },
  { value: 'seller_cloud', label: 'Облачная подпись селлера' },
] as const

const EDO_OPTIONS = [
  { value: 'edo_light_roaming_diadoc', label: 'ЭДО Лайт → роуминг в Диадок' },
  { value: 'diadoc_direct', label: 'Диадок напрямую' },
] as const

const MARKETPLACE_OPTIONS = [
  { value: 'wildberries', label: 'Wildberries' },
  { value: 'ozon', label: 'Ozon' },
] as const

// WMS-615 R13/R14: компактная строка под каждой карточкой площадки. Одна
// строчка статуса + кнопка «Повторить» при отказе. Намеренно без таблиц
// прогресса и процента: backend-контракт прогресс не возвращает, а показывать
// неизвестное число — ложь.
function CatalogImportProgressRow({
  marketplace,
  progress,
  onRetry,
}: {
  marketplace: SellerCatalogMarketplace
  progress: { stage: ImportJobStage; error: string | null }
  onRetry: () => void
}) {
  const testIdSuffix = marketplace === 'wildberries' ? 'wb' : 'ozon'
  if (progress.stage === 'failed') {
    return (
      <Alert
        severity="error"
        data-testid={`seller-settings-${testIdSuffix}-import-failed`}
        action={
          <Button
            color="inherit"
            size="small"
            onClick={onRetry}
            data-testid={`seller-settings-${testIdSuffix}-import-retry`}
          >
            Повторить
          </Button>
        }
      >
        {progress.error ?? describeImportStage('failed')}
      </Alert>
    )
  }
  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{ alignItems: 'center' }}
      data-testid={`seller-settings-${testIdSuffix}-import-progress`}
      data-stage={progress.stage}
    >
      <CircularProgress size={16} />
      <Typography variant="body2" color="text.secondary">
        {describeImportStage(progress.stage)}
      </Typography>
    </Stack>
  )
}

export function SellerSettingsScreen({
  token,
  authHeaders,
  permissions,
  me,
  onProfileUpdated,
  onStaffChanged,
}: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // QA-дефект 1 (WMS-615, 01.10): invalid_wb_token приходил только в верхний
  // Alert «seller-settings-error», который перекрыт модалкой — селлер видел
  // только спиннер и не понимал, что ключ отклонён. Дублируем сообщение
  // внутрь самого диалога, не очищая введённое значение (сохранность для
  // повтора после опечатки).
  const [dialogError, setDialogError] = useState<string | null>(null)
  const [okMsg, setOkMsg] = useState<string | null>(null)
  const [contentKey, setContentKey] = useState('')
  const [hasContentKey, setHasContentKey] = useState<boolean | null>(null)
  const [wbCardsCount, setWbCardsCount] = useState<number | null>(null)
  const [ozonStatus, setOzonStatus] = useState<OzonAccountStatus | null>(null)
  const [ozonClientId, setOzonClientId] = useState('')
  const [ozonApiKey, setOzonApiKey] = useState('')
  const [ozonBusy, setOzonBusy] = useState(false)
  const [ozonEditing, setOzonEditing] = useState(false)
  const [ozonDisconnectConfirm, setOzonDisconnectConfirm] = useState(false)
  const [ozonError, setOzonError] = useState<string | null>(null)
  const [ozonOk, setOzonOk] = useState<string | null>(null)

  const [czCreds, setCzCreds] = useState<MarkingCredentialsState | null>(null)
  const [czDialogOpen, setCzDialogOpen] = useState(false)
  const [czToken, setCzToken] = useState('')
  const [suzToken, setSuzToken] = useState('')
  const [mpKey, setMpKey] = useState('')
  const [mchdId, setMchdId] = useState('')
  const [mchdUntil, setMchdUntil] = useState('')
  const [signingMethod, setSigningMethod] = useState('manual')
  const [edoRoute, setEdoRoute] = useState('edo_light_roaming_diadoc')
  const [marketplace, setMarketplace] = useState('wildberries')
  const [autoIntroduce, setAutoIntroduce] = useState(false)
  const [autoEmitLimit, setAutoEmitLimit] = useState('')
  const [staffRows, setStaffRows] = useState<SellerStaffAccountRow[]>([])
  const [staffBusy, setStaffBusy] = useState(false)
  const [staffPermBusyId, setStaffPermBusyId] = useState<string | null>(null)
  const [staffInviteBusyId, setStaffInviteBusyId] = useState<string | null>(null)
  const [staffError, setStaffError] = useState<string | null>(null)
  const [staffOk, setStaffOk] = useState<string | null>(null)
  const [staffCreatePerms, setStaffCreatePerms] = useState<SellerPermissions>(
    DEFAULT_STAFF_PERMISSIONS,
  )
  const [profileFullName, setProfileFullName] = useState(me?.full_name ?? '')
  const [profileJobTitle, setProfileJobTitle] = useState(me?.job_title ?? '')
  const [profileBusy, setProfileBusy] = useState(false)
  const [editingStaff, setEditingStaff] = useState<SellerStaffAccountRow | null>(null)
  const [editingStaffName, setEditingStaffName] = useState('')
  const [editingStaffTitle, setEditingStaffTitle] = useState('')
  const [editingStaffEmail, setEditingStaffEmail] = useState('')
  const [editingStaffBusy, setEditingStaffBusy] = useState(false)

  // WMS-548 R1: окно выбора товаров после первого ключа площадки — не при замене.
  const [catalogSelectionMarketplace, setCatalogSelectionMarketplace] =
    useState<SellerCatalogMarketplace | null>(null)

  // WMS-615 R13/R14: фоновая загрузка каталога после сохранения реквизитов.
  // Экран остаётся в контексте «Настройки», показывает компактный статус и
  // открывает окно выбора только когда импорт действительно завершился
  // (ImportJobStage === 'succeeded'). Отказ оставляет кнопку «Повторить».
  //
  // Пара объектов (WB/Ozon) — чтобы отказ одной площадки не мешал другой
  // (R7). Активная задача хранится вместе с marketplace: один и тот же
  // job id может прийти и к WB, и к Ozon, если backend-агент выберет общий
  // пул.
  type ImportProgressState = {
    jobId: string
    stage: ImportJobStage
    error: string | null
  }
  const [wbImportProgress, setWbImportProgress] = useState<ImportProgressState | null>(null)
  const [ozonImportProgress, setOzonImportProgress] = useState<ImportProgressState | null>(null)
  const importAbortRef = useRef<Map<SellerCatalogMarketplace, AbortController>>(new Map())
  const captureScope = useSellerAsyncScope(token)

  useEffect(() => {
    setWbImportProgress(null)
    setOzonImportProgress(null)
    setCatalogSelectionMarketplace(null)
    setHasContentKey(null)
    setWbCardsCount(null)
    setOzonStatus(null)
    setBusy(false)
    setOzonBusy(false)
    setContentKey('')
    setOzonClientId('')
    setOzonApiKey('')
    setOpen(false)
    setDialogError(null)
    setError(null)
    setOzonError(null)
    setOkMsg(null)
    setOzonOk(null)
  }, [token])

  useEffect(() => {
    setProfileFullName(me?.full_name ?? '')
    setProfileJobTitle(me?.job_title ?? '')
  }, [me?.full_name, me?.job_title])

  useEffect(() => {
    if (!permissions.settings) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(apiUrl('/integrations/wildberries/self/tokens'), {
          headers: { ...authHeaders(token) },
        })
        if (!res.ok) {
          return
        }
        const j = (await res.json()) as { has_content_token: boolean }
        if (!cancelled) {
          setHasContentKey(Boolean(j.has_content_token))
        }
      } catch {
        // ignore
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authHeaders, permissions.settings, token])

  async function loadOzonStatus(): Promise<void> {
    const scope = captureScope()
    try {
      const res = await fetch(apiUrl('/integrations/ozon/self/account'), {
        headers: { ...authHeaders(token) },
        signal: scope.signal,
      })
      if (res.ok) {
        const status = (await res.json()) as OzonAccountStatus
        if (!scope.isCurrent()) return
        setOzonStatus(status)
        // Astra P2: при перезагрузке страницы persisted last_sync_error был
        // в API, но не на экране — селлер не знал, что импорт упал, и у него
        // не было «Повторить». Если фоновая задача не наблюдается прямо
        // сейчас (нет jobId в прогрессе), показываем persisted failure.
        setOzonImportProgress((current) => {
          if (current && current.jobId) return current
          if (status.connected && status.last_sync_error) {
            return { jobId: '', stage: 'failed', error: catalogImportError(status.last_sync_error) }
          }
          return current
        })
      }
    } catch {
      // Status remains unavailable until the user explicitly performs an action.
    }
  }

  useEffect(() => {
    if (!permissions.settings) {
      return
    }
    void loadOzonStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when token changes
  }, [permissions.settings, token])

  function ozonErrorText(code: string): string {
    if (code.includes('client_id_required')) return 'Введите Client-Id.'
    if (code.includes('api_key_required')) return 'Введите Api-Key.'
    if (code.includes('ozon_credentials_invalid')) {
      return 'Ozon не подтвердил Client-Id и Api-Key. Проверьте оба значения.'
    }
    if (code.includes('ozon_validation_unavailable')) {
      return 'Не удалось проверить подключение Ozon. Сохранённые данные не изменены; попробуйте ещё раз.'
    }
    if (code.includes('ozon_validation_failed')) {
      return 'Ozon вернул неожиданный ответ. Сохранённые данные не изменены; попробуйте позже.'
    }
    if (code.includes('ozon_not_connected')) return 'Сначала подключите Ozon.'
    return 'Не удалось сохранить подключение Ozon. Повторите попытку.'
  }

  async function saveOzon(): Promise<void> {
    const scope = captureScope()
    setOzonError(null)
    setOzonOk(null)
    const clientId = ozonClientId.trim()
    const apiKey = ozonApiKey.trim()
    if (!clientId || !apiKey) {
      setOzonError(`${!clientId ? 'Введите Client-Id.' : ''}${!clientId && !apiKey ? ' ' : ''}${!apiKey ? 'Введите Api-Key.' : ''}`)
      return
    }
    const hadOzonBefore = ozonStatus?.connected === true
    setOzonBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/ozon/self/account'), {
        method: 'PUT',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, api_key: apiKey }),
        signal: scope.signal,
      })
      if (!res.ok) {
        const message = ozonErrorText(await readApiErrorMessage(res))
        if (scope.isCurrent()) setOzonError(message)
        return
      }
      const status = (await res.json()) as OzonAccountStatus
      if (!scope.isCurrent()) return
      setOzonStatus(status)
      setOzonClientId('')
      setOzonApiKey('')
      setOzonEditing(false)
      // Astra P1: watcher запускаем ВСЕГДА, если backend дал catalog_job.
      // Open-selection — отдельно: только первое подключение + право.
      const jobId = extractCatalogJobId(status)
      const openSelectionOnSuccess = shouldOpenCatalogSelectionAfterKeySave({
        hadKeyBefore: hadOzonBefore,
        validationOk: status.validation_status === 'valid',
        canManageProducts: permissions.products,
      })
      if (jobId) {
        setOzonImportProgress({ jobId, stage: extractCatalogJobInitialStage(status), error: null })
        void watchCatalogImportJob('ozon', jobId, { openSelectionOnSuccess })
      } else if (openSelectionOnSuccess) {
        await maybeOpenCatalogSelection('ozon')
      }
    } catch {
      if (scope.isCurrent()) setOzonError('Не удалось сохранить подключение Ozon. Повторите попытку.')
    } finally {
      if (scope.isCurrent()) setOzonBusy(false)
    }
  }

  // «Повторить загрузку товаров». Backend-ручки /integrations/{wb,ozon}/self/
  // sync-products возвращают 202 + CatalogSyncJobOut, экран подхватывает их
  // тем же watchCatalogImportJob.
  async function retryCatalogImport(marketplaceToRetry: SellerCatalogMarketplace): Promise<void> {
    const scope = captureScope()
    const url =
      marketplaceToRetry === 'wildberries'
        ? '/integrations/wildberries/self/sync-products'
        : '/integrations/ozon/self/sync-products'
    const setProgress = (next: ImportProgressState | null) =>
      setMarketplaceProgress(marketplaceToRetry, next)
    setProgress({ jobId: '', stage: 'queued', error: null })
    try {
      const res = await fetch(apiUrl(url), {
        method: 'POST',
        headers: { ...authHeaders(token) },
        signal: scope.signal,
      })
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        if (scope.isCurrent()) setProgress({ jobId: '', stage: 'failed', error: message })
        return
      }
      const parsed = parseCatalogSyncResponse(await res.json())
      if (!scope.isCurrent()) return
      if (!parsed) {
        setProgress({ jobId: '', stage: 'failed', error: describeImportStage('failed') })
        return
      }
      setProgress({ jobId: parsed.jobId, stage: parsed.stage, error: null })
      void watchCatalogImportJob(marketplaceToRetry, parsed.jobId, { openSelectionOnSuccess: false })
    } catch (e) {
      if (!scope.isCurrent()) return
      setProgress({
        jobId: '',
        stage: 'failed',
        error: e instanceof Error ? e.message : describeImportStage('failed'),
      })
    }
  }

  async function testOzon(): Promise<void> {
    setOzonError(null)
    setOzonOk(null)
    setOzonBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/ozon/self/account/test-connection'), {
        method: 'POST', headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        setOzonError(ozonErrorText(await readApiErrorMessage(res)))
        await loadOzonStatus()
        return
      }
      setOzonStatus((await res.json()) as OzonAccountStatus)
    } catch {
      setOzonError('Не удалось проверить подключение Ozon. Сохранённые данные не изменены; попробуйте ещё раз.')
    } finally {
      setOzonBusy(false)
    }
  }

  async function disconnectOzon(): Promise<void> {
    setOzonError(null)
    setOzonBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/ozon/self/account'), {
        method: 'DELETE', headers: { ...authHeaders(token) },
      })
      if (!res.ok && res.status !== 204) {
        setOzonError('Не удалось сохранить подключение Ozon. Повторите попытку.')
        return
      }
      setOzonStatus({ marketplace: 'ozon', connected: false, validation_status: 'not_configured', last_validated_at: null, last_validation_error: null, credentials_updated_at: null, last_synced_at: null, last_sync_error: null })
      setOzonDisconnectConfirm(false)
      setOzonEditing(false)
      setOzonOk('Ozon отключён.')
    } catch {
      setOzonError('Не удалось сохранить подключение Ozon. Повторите попытку.')
    } finally {
      setOzonBusy(false)
    }
  }

  async function loadMarkingCredentials(): Promise<void> {
    try {
      const res = await fetch(apiUrl('/operations/marking-codes/self/credentials'), {
        headers: { ...authHeaders(token) },
      })
      if (!res.ok) {
        return
      }
      const j = (await res.json()) as MarkingCredentialsState
      setCzCreds(j)
      setMchdId(j.mchd_id ?? '')
      setMchdUntil(j.mchd_valid_until ?? '')
      setSigningMethod(j.signing_method)
      setEdoRoute(j.edo_route)
      setMarketplace(j.marketplace ?? 'wildberries')
      setAutoIntroduce(j.auto_introduce)
      setAutoEmitLimit(j.auto_emit_limit != null ? String(j.auto_emit_limit) : '')
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!permissions.settings) {
      return
    }
    void loadMarkingCredentials()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when token changes
  }, [permissions.settings, token])

  async function loadStaffRows(): Promise<void> {
    if (!permissions.staff) {
      return
    }
    const res = await sellerStaffRequest(apiUrl('/auth/seller-staff-accounts'), {
      headers: { ...authHeaders(token) },
    }, 'load')
    setStaffRows((await res.json()) as SellerStaffAccountRow[])
  }

  useEffect(() => {
    if (!permissions.staff) {
      setStaffRows([])
      return
    }
    void loadStaffRows().catch((e: unknown) => {
      setStaffError(sellerStaffError(e, 'load'))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when permission or token changes
  }, [permissions.staff, token])

  async function refreshWbCardsCount(): Promise<void> {
    const scope = captureScope()
    // Astra P2: прежний /products/wb-catalog возвращал ВЕСЬ seller-каталог
    // (WB+Ozon) и грузил весь массив ради .length. Теперь запрашиваем ровно
    // WB-срез, limit=1 — читаем только scope_total (количество WB-карточек
    // в тенанте/селлере), без загрузки каталога в браузер.
    if (hasContentKey !== true) {
      setWbCardsCount(null)
      return
    }
    try {
      const params = new URLSearchParams({
        marketplace: 'wildberries',
        on_fulfillment: 'all',
        limit: '1',
        offset: '0',
      })
      const res = await fetch(apiUrl(`/seller-catalog/page?${params.toString()}`), {
        headers: { ...authHeaders(token) },
        signal: scope.signal,
      })
      if (!res.ok) {
        return
      }
      const body = (await res.json()) as { scope_total?: number }
      if (!scope.isCurrent()) return
      setWbCardsCount(typeof body.scope_total === 'number' ? body.scope_total : null)
    } catch {
      // ignore
    }
  }

  function setMarketplaceProgress(
    marketplaceToUpdate: SellerCatalogMarketplace,
    next: ImportProgressState | null,
  ): void {
    if (marketplaceToUpdate === 'wildberries') {
      setWbImportProgress(next)
    } else {
      setOzonImportProgress(next)
    }
  }

  // Astra P1: наблюдение job'а ВСЕГДА запускается, когда backend выдал job id.
  // Опция `openSelectionOnSuccess` решает, открывать ли окно выбора товаров
  // после успеха: только для первого ключа площадки + с правом «Товары»
  // (shouldOpenCatalogSelectionAfterKeySave). Замена ключа или
  // settings-only-пользователь не открывают окно, но ПРОГРЕСС и честный
  // «Повторить» при отказе должны быть видны — иначе экран обманывает:
  // «ключ сохранён», а импорт тихо проваливается.
  async function watchCatalogImportJob(
    marketplaceToPoll: SellerCatalogMarketplace,
    jobId: string,
    options: { openSelectionOnSuccess: boolean } = { openSelectionOnSuccess: false },
  ): Promise<void> {
    const scope = captureScope()
    if (!scope.isCurrent()) return
    importAbortRef.current.get(marketplaceToPoll)?.abort()
    const controller = new AbortController()
    importAbortRef.current.set(marketplaceToPoll, controller)
    await observeImportJob(
      fetch,
      jobId,
      { ...authHeaders(token) },
      {
        onStage: (stage) =>
          setMarketplaceProgress(marketplaceToPoll, { jobId, stage, error: null }),
        onSucceeded: async () => {
          // Окно выбора снимается всегда при succeeded; открывать его —
          // отдельная развилка R1: не при замене, не без права «Товары».
          setMarketplaceProgress(marketplaceToPoll, null)
          if (marketplaceToPoll === 'wildberries') {
            // Astra P1: WB-счётчик правдив только после фактического конца
            // импорта — раньше onSyncNow рисовал «карточек: 0» на 202.
            await refreshWbCardsCount()
          }
          if (!scope.isCurrent()) return
          if (options.openSelectionOnSuccess) {
            await maybeOpenCatalogSelection(marketplaceToPoll)
          }
        },
        onFailed: (message) =>
          setMarketplaceProgress(marketplaceToPoll, { jobId, stage: 'failed', error: message }),
      },
      controller.signal,
    )
  }

  // Смена сессии и уход со страницы прекращают только наблюдение:
  // уже принятое сервером задание продолжает выполняться.
  useEffect(() => {
    const trackedAborts = importAbortRef.current
    return () => {
      for (const controller of trackedAborts.values()) {
        controller.abort()
      }
      trackedAborts.clear()
    }
  }, [token])

  // WMS-548 R1: сама проверка «первый ли это ключ, прошла ли проверка, есть ли
  // право «Товары»» — в shouldOpenCatalogSelectionAfterKeySave (чистая функция,
  // вызывается на местах сохранения ключа WB и Ozon). Здесь — только сетевой
  // гейт «нашлась ли хоть одна карточка» (А9), которым нельзя пренебречь: без
  // него окно открылось бы пустым, если карточек в кабинете вообще нет.
  async function maybeOpenCatalogSelection(marketplaceToOpen: SellerCatalogMarketplace): Promise<void> {
    const scope = captureScope()
    const params = new URLSearchParams({
      marketplace: marketplaceToOpen,
      on_fulfillment: 'all',
      limit: '1',
      offset: '0',
    })
    const has = await hasAnySellerCatalogCards(
      fetch,
      apiUrl(`/seller-catalog/page?${params.toString()}`),
      { ...authHeaders(token) },
    )
    if (has && scope.isCurrent()) {
      setCatalogSelectionMarketplace(marketplaceToOpen)
    }
  }

  async function onSave() {
    const scope = captureScope()
    setError(null)
    setDialogError(null)
    setOkMsg(null)
    const trimmed = contentKey.trim()
    if (!trimmed) {
      setDialogError('Введите API ключ.')
      return
    }
    const hadKeyBefore = hasContentKey === true
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/wildberries/self/content-token'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content_api_token: trimmed }),
        signal: scope.signal,
      })
      if (!res.ok) {
        const msg = await readApiErrorMessage(res)
        if (!scope.isCurrent()) return
        // QA-дефект 1 (01.10): сообщение показываем внутри самого диалога —
        // верхний Alert при открытой модалке не виден. Введённый ключ не
        // чистим: селлер поправит опечатку и повторит без ввода заново.
        setDialogError(
          msg.includes('invalid_wb_token')
            ? 'Этот API ключ не подходит (проверка WB не прошла).'
            : msg,
        )
        return
      }
      const j = (await res.json()) as {
        validation_ok?: boolean
        validation_error?: string | null
        cards_received?: number
        cards_saved?: number
      }
      if (!scope.isCurrent()) return
      setOpen(false)
      setDialogError(null)
      setContentKey('')
      setHasContentKey(true)
      await refreshWbCardsCount()
      if (!scope.isCurrent()) return
      if (j.validation_ok === false) {
        if (j.validation_error === 'missing_marketplace_scope') {
          setOkMsg(
            'Ключ сохранён только для карточек WB. В ключе нет прав на «Маркетплейс»: включите эту категорию в кабинете WB и сохраните ключ заново.',
          )
        } else {
          setOkMsg(
            `Ключ сохранён. Проверка WB сейчас не прошла (${j.validation_error ?? 'transport_error'}).`,
          )
        }
      } else {
        setOkMsg(
          `Ключ сохранён. Проверка WB прошла (карточек получено: ${j.cards_received ?? 0}, сохранено: ${j.cards_saved ?? 0}).`,
        )
      }
      // Astra P1: наблюдение импорта запускаем ВСЕГДА, когда backend выдал
      // catalog_job — и при первом ключе, и при замене, и у settings-only
      // пользователя. Open-selection — отдельная развилка R1 (первый ключ
      // + право «Товары»).
      const jobId = extractCatalogJobId(j)
      const openSelectionOnSuccess = shouldOpenCatalogSelectionAfterKeySave({
        hadKeyBefore,
        validationOk: j.validation_ok,
        canManageProducts: permissions.products,
      })
      if (jobId) {
        setWbImportProgress({ jobId, stage: extractCatalogJobInitialStage(j), error: null })
        void watchCatalogImportJob('wildberries', jobId, { openSelectionOnSuccess })
      } else if (openSelectionOnSuccess) {
        // Fallback: backend старой версии без catalog_job — открываем окно
        // сразу (etalon). В проде backend-контракт уже с catalog_job.
        await maybeOpenCatalogSelection('wildberries')
      }
    } catch (e) {
      // Astra P2: сетевой или JSON-сбой WB-save не должен уходить в верхний
      // Alert за диалогом — покажем внутри самого диалога, введённый ключ
      // не стираем для повтора.
      if (scope.isCurrent()) setDialogError(e instanceof Error ? e.message : 'Не удалось сохранить ключ.')
    } finally {
      if (scope.isCurrent()) setBusy(false)
    }
  }

  // Astra P1: ручная «Синхронизировать товары» теперь не возвращает готовый
  // каталог сразу — backend отвечает 202 + CatalogSyncJobOut, импорт идёт
  // в фоне. Экран обязан дожидаться job'а и перечитывать WB-счётчик только
  // после подтверждённого успеха, а не сразу после 202 (это и было источником
  // ложного «WB карточек: 0»).
  async function onSyncNow() {
    const scope = captureScope()
    setError(null)
    setOkMsg(null)
    setBusy(true)
    try {
      const res = await fetch(apiUrl('/integrations/wildberries/self/sync-products'), {
        method: 'POST',
        headers: { ...authHeaders(token) },
        signal: scope.signal,
      })
      if (!res.ok) {
        const message = await readApiErrorMessage(res)
        if (scope.isCurrent()) setError(message)
        return
      }
      const parsed = parseCatalogSyncResponse(await res.json())
      if (!scope.isCurrent()) return
      if (!parsed) {
        setError(describeImportStage('failed'))
        return
      }
      setWbImportProgress({ jobId: parsed.jobId, stage: parsed.stage, error: null })
      void watchCatalogImportJob('wildberries', parsed.jobId, { openSelectionOnSuccess: false })
    } catch (e) {
      if (scope.isCurrent()) setError(e instanceof Error ? e.message : 'Не удалось запустить синхронизацию.')
    } finally {
      if (scope.isCurrent()) setBusy(false)
    }
  }

  async function onSaveMarkingCredentials() {
    setError(null)
    setOkMsg(null)
    setBusy(true)
    try {
      const body: Record<string, unknown> = {
        mchd_id: mchdId.trim() || null,
        mchd_valid_until: mchdUntil.trim() || null,
        signing_method: signingMethod,
        edo_route: edoRoute,
        marketplace,
        auto_introduce: autoIntroduce,
        auto_emit_limit: autoEmitLimit.trim() ? Number(autoEmitLimit) : null,
      }
      if (czToken.trim()) {
        body.cz_token = czToken.trim()
      }
      if (suzToken.trim()) {
        body.suz_oms_token = suzToken.trim()
      }
      if (mpKey.trim()) {
        body.mp_api_key = mpKey.trim()
      }
      const res = await fetch(apiUrl('/operations/marking-codes/self/credentials'), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setCzDialogOpen(false)
      setCzToken('')
      setSuzToken('')
      setMpKey('')
      await loadMarkingCredentials()
      setOkMsg('Настройки Честного Знака сохранены.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить настройки.')
    } finally {
      setBusy(false)
    }
  }

  async function onCreateStaff(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    const form = e.currentTarget
    const fd = new FormData(form)
    const fullName = String(fd.get('seller_staff_full_name') ?? '').trim()
    const jobTitle = String(fd.get('seller_staff_job_title') ?? '').trim()
    const email = String(fd.get('seller_staff_email') ?? '').trim()
    if (!fullName || !email || !form.checkValidity()) {
      setStaffError('Укажите ФИО и корректный email сотрудника.')
      form.reportValidity()
      return
    }
    setStaffBusy(true)
    setStaffError(null)
    setStaffOk(null)
    try {
      await sellerStaffRequest(apiUrl('/auth/seller-staff-accounts'), {
        method: 'POST',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ full_name: fullName, job_title: jobTitle || null, email, permissions: staffCreatePerms }),
      }, 'create')
      form.reset()
      setStaffCreatePerms(DEFAULT_STAFF_PERMISSIONS)
      await loadStaffRows()
      await onStaffChanged?.()
      setStaffOk(`Сотрудник добавлен: ${fullName}. Приглашение на ${email} передано на отправку.`)
    } catch (e) {
      setStaffError(sellerStaffError(e, 'create'))
    } finally {
      setStaffBusy(false)
    }
  }

  async function resendStaffInvite(row: SellerStaffAccountRow): Promise<void> {
    setStaffInviteBusyId(row.id)
    setStaffError(null)
    setStaffOk(null)
    try {
      await sellerStaffRequest(apiUrl(`/auth/seller-staff-accounts/${row.id}/invite`), {
        method: 'POST', headers: authHeaders(token),
      }, 'invite')
      setStaffOk(`Приглашение на ${row.email} передано на отправку.`)
    } catch (error) {
      setStaffError(sellerStaffError(error, 'invite'))
    } finally {
      setStaffInviteBusyId(null)
    }
  }

  async function onToggleStaffPermission(
    row: SellerStaffAccountRow,
    key: keyof SellerPermissions,
    checked: boolean,
  ): Promise<void> {
    if (row.is_owner) {
      return
    }
    const next: SellerPermissions = { ...row.permissions, [key]: checked }
    setStaffPermBusyId(row.id)
    setStaffError(null)
    setStaffOk(null)
    try {
      const res = await sellerStaffRequest(apiUrl(`/auth/seller-staff-accounts/${row.id}/permissions`), {
        method: 'PATCH',
        headers: {
          ...authHeaders(token),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(next),
      }, 'permissions')
      const updated = (await res.json()) as SellerStaffAccountRow
      setStaffRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
      await onStaffChanged?.()
      setStaffOk('Права сохранены')
    } catch (e) {
      setStaffError(sellerStaffError(e, 'permissions'))
    } finally {
      setStaffPermBusyId(null)
    }
  }

  async function saveOwnProfile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!onProfileUpdated) return
    const fullName = profileFullName.trim()
    if (!fullName) {
      setError('Укажите ФИО.')
      return
    }
    setProfileBusy(true)
    setError(null)
    try {
      await onProfileUpdated({ full_name: fullName, job_title: profileJobTitle.trim() })
      setOkMsg('Профиль сохранён')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить профиль.')
    } finally {
      setProfileBusy(false)
    }
  }

  function openStaffProfile(row: SellerStaffAccountRow) {
    setEditingStaff(row)
    setEditingStaffName(row.full_name ?? '')
    setEditingStaffTitle(row.job_title ?? '')
    setEditingStaffEmail('')
    setStaffError(null)
    setStaffOk(null)
  }

  async function saveStaffProfile() {
    if (!editingStaff) return
    const fullName = editingStaffName.trim()
    if (!fullName) {
      setStaffError('Укажите ФИО сотрудника.')
      return
    }
    const email = editingStaffEmail.trim()
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setStaffError('Укажите корректный email сотрудника.')
      return
    }
    setStaffError(null)
    setEditingStaffBusy(true)
    try {
      const res = await sellerStaffRequest(apiUrl(`/auth/seller-staff-accounts/${editingStaff.id}/profile`), {
        method: 'PATCH',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName, job_title: editingStaffTitle.trim() || null,
          ...(!editingStaff.email && !editingStaff.is_owner && email ? { email } : {}),
        }),
      }, 'profile')
      const updated = (await res.json()) as SellerStaffAccountRow
      setStaffRows((previous) => previous.map((row) => row.id === updated.id ? updated : row))
      setEditingStaff(null)
      setStaffOk(email ? `Данные сотрудника сохранены. Приглашение на ${email} передано на отправку.` : 'Данные сотрудника сохранены')
    } catch (err) {
      setStaffError(sellerStaffError(err, 'profile'))
    } finally {
      setEditingStaffBusy(false)
    }
  }

  const signingLabel =
    SIGNING_OPTIONS.find((o) => o.value === czCreds?.signing_method)?.label ?? '—'

  return (
    <Box data-testid="seller-settings-root">
      <Typography variant="h5" gutterBottom>
        Настройки
      </Typography>

      {okMsg ? (
        <Alert severity="success" sx={{ mb: 2 }} data-testid="seller-settings-ok">
          {okMsg}
        </Alert>
      ) : null}
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }} data-testid="seller-settings-error">
          {error}
        </Alert>
      ) : null}

      {me ? (
        <Paper variant="outlined" component="form" onSubmit={(e) => void saveOwnProfile(e)} sx={{ p: 2, maxWidth: 920, mb: 2 }} data-testid="seller-own-profile-panel">
          <Typography variant="h6" gutterBottom>Мой профиль</Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <TextField label="ФИО" required size="small" fullWidth value={profileFullName} onChange={(e) => setProfileFullName(e.target.value)} />
            <TextField label="Должность" size="small" fullWidth value={profileJobTitle} onChange={(e) => setProfileJobTitle(e.target.value)} />
            <Button type="submit" variant="contained" disabled={profileBusy}>{profileBusy ? 'Сохранение…' : 'Сохранить'}</Button>
          </Stack>
        </Paper>
      ) : null}

      {permissions.staff ? (
        <Paper
          variant="outlined"
          sx={{ p: 2, maxWidth: 920, mb: 2 }}
          data-testid="seller-staff-panel"
        >
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6">Сотрудники селлера</Typography>
              <Typography variant="body2" color="text.secondary">
                Пользователи этого селлера и доступ к разделам личного кабинета.
              </Typography>
            </Box>
            {staffError ? (
              <Alert severity="error" data-testid="seller-staff-error">
                {staffError}
              </Alert>
            ) : null}
            {staffOk ? (
              <Alert severity="success" data-testid="seller-staff-ok">
                {staffOk}
              </Alert>
            ) : null}
            <TableContainer
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                overflowX: 'auto',
              }}
              data-testid="seller-staff-table-wrap"
            >
              <Table size="small" data-testid="seller-staff-table">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ minWidth: 220 }}>Сотрудник</TableCell>
                    {SELLER_PERMISSION_BLOCKS.map((block) => (
                      <TableCell key={block.key} align="center" sx={{ minWidth: 104 }}>
                        {block.label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {staffRows.map((row) => (
                    <TableRow
                      key={row.id}
                      hover
                      data-testid="seller-staff-row"
                      data-staff-id={row.id}
                    >
                      <TableCell>
                        <Stack spacing={0.5} sx={{ overflowWrap: 'anywhere', maxWidth: 320 }}>
                        <Typography variant="body2">{row.display_name}</Typography>
                        {row.email ? <Typography variant="caption" color="text.secondary">{row.email}</Typography> : null}
                        {row.job_title ? <Typography variant="caption" color="text.secondary">{row.job_title}</Typography> : null}
                        <Button size="small" variant="text" onClick={() => openStaffProfile(row)} sx={{ px: 0, minWidth: 0 }}>Изменить</Button>
                        <Typography
                          variant="caption"
                          color={row.is_owner ? 'text.secondary' : 'warning.main'}
                        >
                          {row.is_owner
                            ? 'владелец селлера'
                            : row.must_set_password
                              ? 'ожидает активации'
                              : 'сотрудник'}
                        </Typography>
                        {!row.is_owner && row.email && row.must_set_password ? (
                          <Button size="small" variant="text" disabled={staffInviteBusyId !== null}
                            onClick={() => void resendStaffInvite(row)}
                            data-testid={`seller-staff-invite-${row.id}`}
                            sx={{ px: 0, justifyContent: 'flex-start', textAlign: 'left' }}>
                            {staffInviteBusyId === row.id ? 'Отправка…' : 'Отправить приглашение ещё раз'}
                          </Button>
                        ) : null}
                        </Stack>
                      </TableCell>
                      {SELLER_PERMISSION_BLOCKS.map((block) => (
                        <TableCell key={block.key} align="center" padding="checkbox">
                          <Checkbox
                            size="small"
                            checked={row.permissions[block.key]}
                            disabled={row.is_owner || staffPermBusyId === row.id}
                            slotProps={{
                              root: {
                                'data-testid': `seller-staff-perm-${row.id}-${block.key}`,
                              } as React.HTMLAttributes<HTMLSpanElement>,
                              input: {
                                'aria-label': `${block.label} для ${row.display_name}`,
                              } as React.InputHTMLAttributes<HTMLInputElement>,
                            }}
                            onChange={(e) =>
                              void onToggleStaffPermission(row, block.key, e.target.checked)
                            }
                          />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                  {staffRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={SELLER_PERMISSION_BLOCKS.length + 1}>
                        <Typography variant="body2" color="text.secondary">
                          Пока нет сотрудников.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>

            <Box
              component="form"
              noValidate
              onSubmit={(e) => void onCreateStaff(e)}
              data-testid="seller-staff-create-form"
              sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 2 }}
            >
              <Stack spacing={1.5}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  Добавить сотрудника
                </Typography>
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1.5}
                  sx={{ alignItems: { xs: 'stretch', sm: 'flex-start' } }}
                >
                  <TextField
                    name="seller_staff_full_name"
                    label="ФИО"
                    required
                    fullWidth
                    size="small"
                    autoComplete="off"
                    slotProps={{ htmlInput: { 'data-testid': 'seller-staff-name' } }}
                    sx={{ flex: 1 }}
                  />
                  <TextField name="seller_staff_job_title" label="Должность" fullWidth size="small" sx={{ flex: 1 }} />
                  <TextField name="seller_staff_email" label="Email" type="email" required fullWidth size="small" autoComplete="email" sx={{ flex: 1 }} slotProps={{ htmlInput: { 'data-testid': 'seller-staff-email' } }} />
                  <Button
                    type="submit"
                    variant="contained"
                    disabled={staffBusy}
                    data-testid="seller-staff-submit"
                    startIcon={staffBusy ? <CircularProgress size={16} color="inherit" /> : null}
                    sx={{ minWidth: { sm: 140 }, mt: { xs: 0, sm: 0.5 } }}
                  >
                    {staffBusy ? 'Сохранение…' : 'Добавить'}
                  </Button>
                </Stack>
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
                  {SELLER_PERMISSION_BLOCKS.map((block) => (
                    <FormControlLabel
                      key={block.key}
                      control={
                        <Checkbox
                          size="small"
                          checked={staffCreatePerms[block.key]}
                          onChange={(e) =>
                            setStaffCreatePerms((prev) => ({
                              ...prev,
                              [block.key]: e.target.checked,
                            }))
                          }
                          data-testid={`seller-staff-create-perm-${block.key}`}
                        />
                      }
                      label={block.label}
                    />
                  ))}
                </Stack>
              </Stack>
            </Box>
          </Stack>
        </Paper>
      ) : null}

      {permissions.settings ? (
        <>
      <Paper variant="outlined" sx={{ p: 2, maxWidth: 720, mb: 2 }} data-testid="seller-settings-wb-card">
        <Stack spacing={1.5}>
          <Typography variant="h6">Wildberries</Typography>
          <Typography variant="body2" color="text.secondary">
            Добавь API ключ WB, чтобы подтягивать карточки товаров и ШК (баркоды).
          </Typography>
          <Divider />
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary">
              Ключ:
            </Typography>
            <Typography
              variant="body2"
              sx={{ color: hasContentKey ? 'text.secondary' : 'text.disabled' }}
              data-testid="seller-settings-key-status"
            >
              {hasContentKey ? 'добавлен' : hasContentKey === false ? 'не добавлен' : '—'}
            </Typography>
            <Box sx={{ flexGrow: 1 }} />
            {/* QA-дефект 3 (WMS-615, 01.10): /products/wb-catalog возвращает
                весь каталог селлера (товары обеих площадок). У Ozon-only
                селлера её строка «1 товар» показывалась как «WB товары: 1»,
                хотя WB-ключа нет. Пока у backend нет отдельного WB-счётчика,
                честно показываем число только когда WB-ключ подключён. */}
            {hasContentKey ? (
              <Typography variant="body2" color="text.secondary" data-testid="seller-settings-wb-count">
                WB товары: {wbCardsCount ?? '—'}
              </Typography>
            ) : null}
          </Stack>
          <Box>
            <Button
              variant="contained"
              onClick={() => {
                setDialogError(null)
                setOpen(true)
              }}
              disabled={busy}
              data-testid="seller-settings-add-key"
            >
              {hasContentKey ? 'Заменить ключ' : 'Добавить ключ'}
            </Button>
            <Button
              sx={{ ml: 1 }}
              variant="outlined"
              onClick={() => void onSyncNow()}
              disabled={busy || !hasContentKey}
              data-testid="seller-settings-sync-products"
            >
              Синхронизировать товары
            </Button>
          </Box>
          {wbImportProgress ? (
            <CatalogImportProgressRow
              marketplace="wildberries"
              progress={wbImportProgress}
              onRetry={() => void retryCatalogImport('wildberries')}
            />
          ) : null}
        </Stack>
      </Paper>

      <Paper
        variant="outlined"
        sx={{ p: 2, maxWidth: 720, mb: 2 }}
        data-testid="seller-settings-ozon-card"
      >
        <Stack spacing={1.5}>
          <Typography variant="h6">Ozon</Typography>
          <Typography variant="body2" color="text.secondary">
            Подключение кабинета Ozon для этого селлера.
          </Typography>
          <Divider />
          {ozonError ? (
            <Alert severity="error" data-testid="seller-settings-ozon-error">
              {ozonError}
            </Alert>
          ) : null}
          {!ozonError && ozonStatus?.validation_status === 'invalid' ? (
            <Alert severity="error" data-testid="seller-settings-ozon-error">
              Ozon не подтвердил Client-Id и Api-Key. Проверьте оба значения.
            </Alert>
          ) : null}
          {!ozonError && ozonStatus?.validation_status === 'unavailable' ? (
            <Alert severity="warning" data-testid="seller-settings-ozon-error">
              Не удалось проверить подключение Ozon. Сохранённые данные не изменены; попробуйте ещё раз.
            </Alert>
          ) : null}
          {ozonOk ? <Alert severity="success">{ozonOk}</Alert> : null}
          {!ozonError && resolveOzonAccountDisplay(ozonStatus).exchangeDisabled ? (
            <Alert severity="info" data-testid="seller-settings-ozon-not-live">
              Ozon подтвердил Client-Id и Api-Key — ключ рабочий. Но обмен с Ozon мы ещё не
              включили: заказы, статусы и остатки не передаются. Заказы Ozon в системе пока не
              появятся.
            </Alert>
          ) : null}
          {ozonImportProgress ? (
            <CatalogImportProgressRow
              marketplace="ozon"
              progress={ozonImportProgress}
              onRetry={() => void retryCatalogImport('ozon')}
            />
          ) : null}
          {ozonStatus?.connected && !ozonEditing ? (
            <>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography data-testid="seller-settings-ozon-status" variant="body2">
                  {resolveOzonAccountDisplay(ozonStatus).label}
                </Typography>
                {ozonStatus.last_validated_at ? (
                  <Typography variant="body2" color="text.secondary">
                    Последняя проверка: {new Date(ozonStatus.last_validated_at).toLocaleString('ru-RU')}
                  </Typography>
                ) : null}
              </Stack>
              {ozonDisconnectConfirm ? (
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }} data-testid="seller-settings-ozon-disconnect-confirm">
                  <Typography variant="body2">Отключить Ozon от этого селлера?</Typography>
                  <Button variant="contained" color="error" disabled={ozonBusy} onClick={() => void disconnectOzon()}>
                    Отключить
                  </Button>
                  <Button disabled={ozonBusy} onClick={() => setOzonDisconnectConfirm(false)}>Отмена</Button>
                </Stack>
              ) : (
                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                  <Button variant="outlined" disabled={ozonBusy} onClick={() => void testOzon()} data-testid="seller-settings-ozon-test">
                    {ozonBusy ? 'Проверяем…' : 'Проверить подключение'}
                  </Button>
                  <Button disabled={ozonBusy} onClick={() => { setOzonEditing(true); setOzonError(null); setOzonOk(null) }} data-testid="seller-settings-ozon-edit">
                    Заменить данные
                  </Button>
                  <Button color="error" disabled={ozonBusy} onClick={() => setOzonDisconnectConfirm(true)} data-testid="seller-settings-ozon-disconnect">
                    Отключить
                  </Button>
                </Stack>
              )}
            </>
          ) : (
            <Stack spacing={1.5} component="form" onSubmit={(e) => { e.preventDefault(); void saveOzon() }} noValidate>
              <TextField
                label="Client-Id"
                value={ozonClientId}
                onChange={(e) => setOzonClientId(e.target.value)}
                disabled={ozonBusy}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'seller-settings-ozon-client-id' } }}
              />
              <TextField
                label="Api-Key"
                type="password"
                value={ozonApiKey}
                onChange={(e) => setOzonApiKey(e.target.value)}
                disabled={ozonBusy}
                fullWidth
                slotProps={{ htmlInput: { 'data-testid': 'seller-settings-ozon-api-key' } }}
              />
              <Stack direction="row" spacing={1}>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={ozonBusy}
                  data-testid="seller-settings-ozon-connect"
                >
                  {ozonBusy ? 'Проверяем…' : ozonEditing ? 'Сохранить новые данные' : 'Подключить'}
                </Button>
                {ozonEditing ? (
                  <Button disabled={ozonBusy} onClick={() => { setOzonEditing(false); setOzonError(null); setOzonClientId(''); setOzonApiKey('') }}>
                    Отмена
                  </Button>
                ) : null}
              </Stack>
            </Stack>
          )}
        </Stack>
      </Paper>

      <Paper
        variant="outlined"
        sx={{ p: 2, maxWidth: 720 }}
        data-testid="seller-settings-marking-card"
      >
        <Stack spacing={1.5}>
          <Typography variant="h6">Честный Знак — интеграция</Typography>
          <Typography variant="body2" color="text.secondary">
            Токены ГИС МТ/СУЗ, способ подписи, МЧД и маршрут ЭДО для авто-ввода в оборот и передачи
            кодов на маркетплейс.
          </Typography>
          <Divider />
          <Stack spacing={0.5}>
            <Typography variant="body2" data-testid="seller-settings-cz-signing">
              Подпись: {signingLabel}
            </Typography>
            <Typography variant="body2" data-testid="seller-settings-cz-tokens">
              Токены: ЧЗ {czCreds?.has_cz_token ? '✓' : '—'} · СУЗ {czCreds?.has_suz_oms_token ? '✓' : '—'} ·
              МП {czCreds?.has_mp_api_key ? '✓' : '—'}
            </Typography>
            <Typography variant="body2" color="text.secondary" data-testid="seller-settings-cz-auto">
              Авто-ввод: {czCreds?.auto_introduce ? 'вкл' : 'выкл'}
              {czCreds?.auto_emit_limit != null ? ` · лимит эмиссии: ${czCreds.auto_emit_limit}` : ''}
            </Typography>
          </Stack>
          <Box>
            <Button
              variant="contained"
              onClick={() => setCzDialogOpen(true)}
              disabled={busy}
              data-testid="seller-settings-cz-edit"
            >
              Настроить интеграцию
            </Button>
          </Box>
        </Stack>
      </Paper>

      <Dialog
        open={open}
        onClose={() => {
          if (busy) return
          setOpen(false)
          setDialogError(null)
        }}
        fullWidth
        maxWidth="sm"
        data-testid="seller-settings-key-dialog"
      >
        <DialogTitle>WB API ключ</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {dialogError ? (
              <Alert severity="error" data-testid="seller-settings-key-dialog-error">
                {dialogError}
              </Alert>
            ) : null}
            <TextField
              label="WB API ключ"
              value={contentKey}
              onChange={(e) => setContentKey(e.target.value)}
              fullWidth
              disabled={busy}
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-key-input' } }}
              placeholder={hasContentKey ? 'ключ уже добавлен (вставь новый, чтобы заменить)' : undefined}
            />
            <Typography variant="body2" color="text.secondary">
              При сохранении мы проверим ключ запросом к WB и попробуем получить список карточек.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setOpen(false)
              setDialogError(null)
            }}
            disabled={busy}
            data-testid="seller-settings-cancel"
          >
            Отмена
          </Button>
          <Button variant="contained" onClick={() => void onSave()} disabled={busy} data-testid="seller-settings-save">
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={czDialogOpen}
        onClose={() => (busy ? undefined : setCzDialogOpen(false))}
        fullWidth
        maxWidth="sm"
        data-testid="seller-settings-cz-dialog"
      >
        <DialogTitle>Интеграция Честного Знака</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControl fullWidth data-testid="seller-settings-cz-signing-control">
              <InputLabel id="cz-signing-label">Способ подписи</InputLabel>
              <Select
                labelId="cz-signing-label"
                label="Способ подписи"
                value={signingMethod}
                onChange={(e) => setSigningMethod(e.target.value)}
                disabled={busy}
                data-testid="seller-settings-cz-signing-select"
              >
                {SIGNING_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="cz-edo-label">Маршрут ЭДО</InputLabel>
              <Select
                labelId="cz-edo-label"
                label="Маршрут ЭДО"
                value={edoRoute}
                onChange={(e) => setEdoRoute(e.target.value)}
                disabled={busy}
                data-testid="seller-settings-cz-edo-select"
              >
                {EDO_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel id="cz-mp-label">Маркетплейс</InputLabel>
              <Select
                labelId="cz-mp-label"
                label="Маркетплейс"
                value={marketplace}
                onChange={(e) => setMarketplace(e.target.value)}
                disabled={busy}
              >
                {MARKETPLACE_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Номер МЧД"
              value={mchdId}
              onChange={(e) => setMchdId(e.target.value)}
              fullWidth
              disabled={busy}
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-cz-mchd-id' } }}
            />
            <TextField
              label="МЧД действует до"
              type="date"
              value={mchdUntil}
              onChange={(e) => setMchdUntil(e.target.value)}
              fullWidth
              disabled={busy}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="Токен ГИС МТ (ЧЗ)"
              value={czToken}
              onChange={(e) => setCzToken(e.target.value)}
              fullWidth
              disabled={busy}
              type="password"
              placeholder={czCreds?.has_cz_token ? 'уже сохранён — вставьте новый для замены' : undefined}
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-cz-token' } }}
            />
            <TextField
              label="Токен СУЗ (эмиссия)"
              value={suzToken}
              onChange={(e) => setSuzToken(e.target.value)}
              fullWidth
              disabled={busy}
              type="password"
              placeholder={czCreds?.has_suz_oms_token ? 'уже сохранён' : undefined}
            />
            <TextField
              label="API ключ маркетплейса"
              value={mpKey}
              onChange={(e) => setMpKey(e.target.value)}
              fullWidth
              disabled={busy}
              type="password"
              placeholder={czCreds?.has_mp_api_key ? 'уже сохранён' : undefined}
            />
            <TextField
              label="Лимит авто-эмиссии (кодов)"
              value={autoEmitLimit}
              onChange={(e) => setAutoEmitLimit(e.target.value)}
              fullWidth
              disabled={busy}
              type="number"
              slotProps={{ htmlInput: { 'data-testid': 'seller-settings-cz-emit-limit' } }}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={autoIntroduce}
                  onChange={(e) => setAutoIntroduce(e.target.checked)}
                  disabled={busy}
                />
              }
              label="Автоматический ввод в оборот"
              data-testid="seller-settings-cz-auto-introduce"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setCzDialogOpen(false)}
            disabled={busy}
            data-testid="seller-settings-cz-cancel"
          >
            Отмена
          </Button>
          <Button
            variant="contained"
            onClick={() => void onSaveMarkingCredentials()}
            disabled={busy}
            data-testid="seller-settings-cz-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>
        </>
      ) : null}
      <Dialog open={editingStaff !== null} onClose={() => !editingStaffBusy && setEditingStaff(null)} fullWidth maxWidth="xs">
        <DialogTitle>Данные сотрудника</DialogTitle>
        <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
          <TextField autoFocus label="ФИО" required value={editingStaffName} onChange={(e) => setEditingStaffName(e.target.value)} />
          <TextField label="Должность" value={editingStaffTitle} onChange={(e) => setEditingStaffTitle(e.target.value)} />
          {editingStaff && !editingStaff.is_owner && !editingStaff.email ? (
            <TextField label="Email" type="email" value={editingStaffEmail} onChange={(e) => setEditingStaffEmail(e.target.value)}
              helperText="После добавления email сотрудник получит приглашение и задаст новый пароль. Старый пароль перестанет действовать, в том числе на ТСД." />
          ) : null}
          {staffError ? <Alert severity="error">{staffError}</Alert> : null}
        </Stack></DialogContent>
        <DialogActions><Button onClick={() => setEditingStaff(null)} disabled={editingStaffBusy}>Отмена</Button><Button variant="contained" onClick={() => void saveStaffProfile()} disabled={editingStaffBusy}>Сохранить</Button></DialogActions>
      </Dialog>
      {catalogSelectionMarketplace ? (
        <SellerCatalogSelectionDialog
          marketplace={catalogSelectionMarketplace}
          token={token}
          authHeaders={authHeaders}
          onClose={() => setCatalogSelectionMarketplace(null)}
          onAdded={() => refreshWbCardsCount()}
        />
      ) : null}
    </Box>
  )
}
