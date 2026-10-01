// WMS-615 R13/R14: сохранение реквизитов WB/Ozon не держит HTTP до конца
// полного импорта каталога. Если backend вернул `catalog_job_id`, экран
// переходит в режим наблюдения за фоновой задачей и открывает окно выбора
// товаров только после подтверждённого полного успеха. При отказе остаётся
// в контексте настроек с кнопкой «Повторить», секретов нигде не показываем.
//
// Этот модуль — только чистая логика статуса и опроса. Он намеренно не
// держит React-состояние и не рисует MUI: разметка собирается в
// SellerSettingsScreen, где лежит общий Alert/Stack. Отдельный модуль нужен,
// чтобы та же логика (контракт /operations/background-jobs/{id}) переиспользовалась
// WB и Ozon и могла быть точечно проверена без DOM.

import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

// Контракт backend (backend/app/schemas/catalog_sync.py): CatalogSyncState
// уже сопоставлен сервером к «queued|running|succeeded|failed». Экран берёт
// поле `state` ответа как есть; поле `status` (сырой BackgroundJob-статус,
// pending/running/done/failed) остаётся запасным путём, если старый клиент
// попадёт на новый backend без поля `state`, и наоборот.
export type ImportJobStage = 'queued' | 'running' | 'succeeded' | 'failed'

export function catalogImportError(message: string): string {
  if (message === 'ozon_catalog_unavailable') {
    return 'Не удалось загрузить каталог Ozon. Повторите загрузку позже.'
  }
  if (message === 'wb_validation_unavailable') {
    return 'Не удалось проверить ключ Wildberries. Попробуйте ещё раз позже.'
  }
  return message
}

const RAW_TO_STAGE: Record<string, ImportJobStage> = {
  queued: 'queued',
  pending: 'queued',
  running: 'running',
  succeeded: 'succeeded',
  done: 'succeeded',
  failed: 'failed',
}

export function mapBackgroundJobStatus(
  status: string | null | undefined,
): ImportJobStage {
  if (!status) return 'running'
  return RAW_TO_STAGE[status] ?? 'running'
}

/**
 * Текст статуса под кнопкой «Сохранить» — компактно, одной строкой.
 * Намеренно короткий: экран не должен превращаться в повествовательную
 * подсказку (правило UI проекта).
 */
export function describeImportStage(stage: ImportJobStage): string {
  switch (stage) {
    case 'queued':
      return 'Загрузка товаров поставлена в очередь.'
    case 'running':
      return 'Загружаем товары из кабинета…'
    case 'succeeded':
      return 'Товары загружены.'
    case 'failed':
      return 'Загрузка товаров не удалась.'
  }
}

export type ImportJobObservation =
  | { outcome: 'in_progress'; stage: 'queued' | 'running' }
  | { outcome: 'succeeded' }
  | { outcome: 'failed'; message: string }

/**
 * Один опрос `/operations/background-jobs/{id}`. Текст ошибки берётся из
 * `error_message` ответа. Backend уже заменяет внутренний текст на
 * «Не удалось выполнить задачу» для сторонних причин (seller-роль, см.
 * backend/app/api/background_jobs.py), поэтому секрета в поле быть не может
 * по контракту API; экран дополнительно не раскрывает client_id/api-key
 * сам, потому что их здесь просто нет.
 */
export async function pollImportJob(
  fetchImpl: typeof fetch,
  jobId: string,
  headers: Record<string, string>,
  signal?: AbortSignal,
): Promise<ImportJobObservation> {
  const res = await fetchImpl(apiUrl(`/operations/background-jobs/${jobId}`), { headers, signal })
  if (!res.ok) {
    // 404 после смены сессии — тоже отказ наблюдения, но тогда вызов идёт
    // через isCurrentSession() в SellerSettingsScreen и его результат
    // отбрасывается без Alert. Здесь — просто повторяем сообщение сервера.
    return { outcome: 'failed', message: await readApiErrorMessage(res) }
  }
  const body = (await res.json()) as {
    state?: string
    status?: string
    error_message?: string | null
  }
  const stage = mapBackgroundJobStatus(body.state ?? body.status)
  if (stage === 'succeeded') {
    return { outcome: 'succeeded' }
  }
  if (stage === 'failed') {
    return {
      outcome: 'failed',
      message: catalogImportError(body.error_message ?? describeImportStage('failed')),
    }
  }
  return { outcome: 'in_progress', stage }
}

/**
 * Контракт тела ответа после сохранения реквизитов (R13):
 *   `catalog_job: {id: str, marketplace: "wildberries"|"ozon", state: ...}`.
 * См. backend/app/schemas/catalog_sync.py и
 * backend/app/api/{wildberries_integration,ozon_integration}.py. Для устойчивости
 * к старому коду также читается плоский `catalog_job_id` (не обязательный).
 */
export function extractCatalogJobId(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null
  const catalogJob = (body as { catalog_job?: unknown }).catalog_job
  if (catalogJob && typeof catalogJob === 'object') {
    const raw = (catalogJob as { id?: unknown }).id
    if (typeof raw === 'string' && raw.trim().length > 0) {
      return raw.trim()
    }
  }
  const flat = (body as { catalog_job_id?: unknown }).catalog_job_id
  if (typeof flat === 'string' && flat.trim().length > 0) {
    return flat.trim()
  }
  return null
}

/**
 * Этап, который backend уже вычислил и прислал в теле сохранения (R13: экран
 * показывает ход ожидания сразу после «Сохранить», ещё до первого опроса).
 * Если поля нет — считаем, что импорт только поставлен в очередь (queued).
 */
export function extractCatalogJobInitialStage(body: unknown): ImportJobStage {
  if (!body || typeof body !== 'object') return 'queued'
  const catalogJob = (body as { catalog_job?: unknown }).catalog_job
  if (catalogJob && typeof catalogJob === 'object') {
    const rawState = (catalogJob as { state?: unknown }).state
    if (typeof rawState === 'string') {
      return mapBackgroundJobStatus(rawState)
    }
  }
  return 'queued'
}

/**
 * Разбор ответа `POST /integrations/{wb,ozon}/self/sync-products` — backend
 * вернёт 202 + CatalogSyncJobOut {id, marketplace, state} (плоско, без
 * обёртки `catalog_job`). Этот хелпер даёт id и начальный этап, не считая
 * тело завершением (Astra P1: мы не имеем права перечитывать каталог сразу
 * после 202 — импорт ещё не отработал).
 */
export function parseCatalogSyncResponse(body: unknown): { jobId: string; stage: ImportJobStage } | null {
  if (!body || typeof body !== 'object') return null
  const raw = (body as { id?: unknown }).id
  if (typeof raw !== 'string' || raw.trim().length === 0) return null
  const stateRaw = (body as { state?: unknown }).state
  const stage = typeof stateRaw === 'string' ? mapBackgroundJobStatus(stateRaw) : 'queued'
  return { jobId: raw.trim(), stage }
}

export type ImportJobObserverCallbacks = {
  onStage: (stage: 'queued' | 'running') => void
  onSucceeded: () => void | Promise<void>
  onFailed: (message: string) => void
}

/**
 * Наблюдатель фоновой задачи импорта: опрашивает статус до «succeeded» или
 * «failed» (или отмены по сигналу). Вынесен из SellerSettingsScreen, чтобы
 * тем же циклом пользовался экран «Товары» (кнопка «Синхронизировать по API»)
 * и регрессионные тесты.
 *
 * Контракт поведения:
 * - при 'in_progress' → onStage(queued|running), пауза, следующий опрос;
 * - при 'succeeded' → onSucceeded() один раз, цикл завершается;
 * - при 'failed' или падении запроса → onFailed(message), цикл завершается;
 * - при controller.signal.aborted — выход без вызова колбэков (это уже
 *   прежняя сессия, её ответ больше никого не интересует).
 */
export async function observeImportJob(
  fetchImpl: typeof fetch,
  jobId: string,
  headers: Record<string, string>,
  callbacks: ImportJobObserverCallbacks,
  signal: AbortSignal,
  pollIntervalMs = 2000,
): Promise<void> {
  while (!signal.aborted) {
    let observation: ImportJobObservation
    try {
      observation = await pollImportJob(fetchImpl, jobId, headers, signal)
    } catch (e) {
      if (signal.aborted) return
      callbacks.onFailed(e instanceof Error ? e.message : describeImportStage('failed'))
      return
    }
    if (signal.aborted) return
    if (observation.outcome === 'in_progress') {
      callbacks.onStage(observation.stage)
      await delay(pollIntervalMs, signal)
      continue
    }
    if (observation.outcome === 'succeeded') {
      await callbacks.onSucceeded()
      return
    }
    callbacks.onFailed(observation.message)
    return
  }
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      clearTimeout(timer)
      resolve()
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}
