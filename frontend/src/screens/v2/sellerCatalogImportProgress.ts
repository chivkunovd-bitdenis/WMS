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
      message: body.error_message ?? describeImportStage('failed'),
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
