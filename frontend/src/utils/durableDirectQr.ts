import type { PreparedQrInput } from './printPreparedQr'

export type DirectQrContext = {
  tenantId: string; userId: string; supplyId: string; orderId: string
  scanId: string; barcode: string; marketplace: 'wildberries'; wbOrderId: number
}
export type DurableQrInput = PreparedQrInput & { context: DirectQrContext }
export type NativeQrJob = {
  idempotencyKey?: string; status?: string; receipt?: string; reason?: string; error?: string
  context?: DirectQrContext; widthMm?: number; heightMm?: number
}
export type DurableQrAttempt = { input: DurableQrInput; createdAt: number; result?: NativeQrJob }
export interface QrAttemptStore {
  get(key: string): Promise<DurableQrAttempt | undefined>
  put(attempt: DurableQrAttempt): Promise<void>
}
const storageError = () => new Error('Не удалось сохранить попытку печати в браузере. Заказ не завершён. Освободите место или разрешите хранилище и повторите исходный штрихкод; не очищайте данные сайта.')
const DB = 'wms-direct-qr-v1'
const STORE = 'attempts'

/** Resolve only after transaction commit, never merely after the request succeeds. */
async function transaction<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore, tx: IDBTransaction) => IDBRequest<T>): Promise<T> {
  let db: IDBDatabase | undefined
  try {
    db = await new Promise<IDBDatabase>((resolve, reject) => {
      const open = indexedDB.open(DB, 1)
      open.onupgradeneeded = () => open.result.createObjectStore(STORE, { keyPath: 'input.idempotencyKey' })
      open.onsuccess = () => resolve(open.result)
      open.onerror = () => reject(open.error)
      open.onblocked = () => reject(storageError())
    })
    return await new Promise<T>((resolve, reject) => {
      const tx = db!.transaction(STORE, mode, { durability: 'strict' })
      const req = run(tx.objectStore(STORE), tx)
      tx.oncomplete = () => resolve(req.result)
      tx.onerror = tx.onabort = () => reject(tx.error ?? storageError())
    })
  } catch { throw storageError() }
  finally { db?.close() }
}
export const qrAttemptStore: QrAttemptStore = {
  get: (key) => transaction('readonly', (store) => store.get(key)),
  put: async (attempt) => {
    await transaction('readwrite', (store, tx) => {
      const check = store.get(attempt.input.idempotencyKey)
      check.onsuccess = () => {
        const previous = check.result as DurableQrAttempt | undefined
        // This comparison and the write share one transaction, including across tabs.
        if (previous && JSON.stringify(previous.input) !== JSON.stringify(attempt.input)) { tx.abort(); return }
        store.put(attempt)
      }
      return check
    })
  },
}

function sameContext(a: DirectQrContext, b: DirectQrContext): boolean {
  return Boolean(a && b) && a.tenantId === b.tenantId && a.userId === b.userId && a.supplyId === b.supplyId
    && a.orderId === b.orderId && a.scanId === b.scanId && a.barcode === b.barcode
}
export async function restoreDurableQr(key: string, context: DirectQrContext, store = qrAttemptStore): Promise<DurableQrAttempt | undefined> {
  const saved = await store.get(key)
  if (saved && (!saved.input || !sameContext(saved.input.context, context) || saved.input.idempotencyKey !== key
    || typeof saved.input.imageDataUrl !== 'string' || !(saved.input.widthMm > 0) || !(saved.input.heightMm > 0))) {
    throw new Error('Сохранённая попытка печати не соответствует этому заказу. Исходные данные сохранены; новая печать не отправлена.')
  }
  return saved
}
export async function prepareDurableQr(input: DurableQrInput, store = qrAttemptStore): Promise<DurableQrAttempt> {
  const saved = await restoreDurableQr(input.idempotencyKey, input.context, store)
  if (saved) {
    if (saved.input.imageDataUrl !== input.imageDataUrl || saved.input.widthMm !== input.widthMm || saved.input.heightMm !== input.heightMm) {
      throw new Error('Изображение или размер сохранённого задания изменились. Восстановите исходную попытку печати.')
    }
    return saved
  }
  const attempt = { input, createdAt: Date.now() }
  await store.put(attempt)
  return attempt
}
const BASE = 'http://127.0.0.1:17843'
const ACCEPTED = new Set(['accepted', 'pending', 'processing', 'completed'])
export type DurableQrTransport = { fetch: typeof fetch; wait: () => Promise<void>; polls: number }
const transport: DurableQrTransport = {
  fetch: (...args) => fetch(...args), wait: () => new Promise((resolve) => setTimeout(resolve, 500)), polls: 60,
}

/** Retains exact artifacts and every received outcome, including canceled/unknown jobs. */
export async function dispatchDurableQr(input: DurableQrInput, store = qrAttemptStore, io = transport, requireExisting = false): Promise<void> {
  const attempt = await prepareDurableQr(input, store)
  const path = `/jobs/${encodeURIComponent(input.idempotencyKey)}`
  const request = async (path: string, method = 'GET', body?: unknown): Promise<NativeQrJob | null> => {
    let response: Response
    try {
      response = await io.fetch(`${BASE}${path}`, {
        method, headers: { 'X-WMS-Print': '1', ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(15_000),
      })
    } catch {
      throw new Error('Нет ответа WMS Print. Исходная этикетка сохранена. Запустите программу и повторите этот штрихкод: сначала будет проверен результат прежнего задания.')
    }
    if (method === 'GET' && response.status === 404) return null
    const job = await response.json() as NativeQrJob
    if (!response.ok) throw new Error(job.error ?? job.reason ?? 'Не удалось прочитать результат WMS Print.')
    if ((job.idempotencyKey && job.idempotencyKey !== input.idempotencyKey)
      || (job.context && !sameContext(job.context, input.context))
      || (job.widthMm !== undefined && job.widthMm !== input.widthMm)
      || (job.heightMm !== undefined && job.heightMm !== input.heightMm)) {
      throw new Error('WMS Print вернул результат другого задания. Повторная печать не отправлена.')
    }
    attempt.result = job
    await store.put(attempt)
    return job
  }
  let job = await request(path)
  if (!job) {
    if (requireExisting) {
      if (attempt.result?.receipt && !attempt.result.status) return
      throw new Error('WMS отмечает запуск печати, но WMS Print не нашёл исходное задание. Результат неизвестен; новая копия не отправлена. Проверьте локальный журнал WMS Print.')
    }
    // The old helper has no GET endpoint; POST with the same key still reconciles
    // its durable receipt. The exact image and dimensions are never regenerated.
    job = await request('/print', 'POST', { ...input, protocolVersion: 2 })
  } else if (['saved', 'failed_before_submit'].includes(job.status ?? '')) {
    job = await request(`${path}/retry`, 'POST')
  } else if (job.status === 'unknown' || job.status === 'submitting') {
    job = await request(`${path}/reconcile`, 'POST')
  }
  for (let poll = 0; job && ['saved', 'submitting'].includes(job.status ?? '') && poll < io.polls; poll++) {
    await io.wait()
    job = await request(path)
  }
  if (job?.receipt && (!job.status || ACCEPTED.has(job.status))) return
  const labels: Record<string, string> = {
    saved: 'сохранено, ожидает отправки', submitting: 'результат передачи ещё не установлен',
    unknown: 'результат передачи неизвестен', canceled: 'задание отменено', aborted: 'очередь прервала задание',
    stopped: 'очередь остановлена', held: 'задание удерживается очередью', failed_before_submit: 'не передано в очередь',
  }
  throw new Error(`WMS Print: ${labels[job?.status ?? ''] ?? 'приём этикетки не подтверждён'}${job?.reason ? ` (${job.reason})` : ''}. Заказ WB № ${input.context.wbOrderId}, штрихкод ${input.context.barcode}, задание ${input.idempotencyKey}. Исходная этикетка сохранена. Повторите этот штрихкод для проверки и восстановления; журнал: ${BASE}/jobs.`)
}
