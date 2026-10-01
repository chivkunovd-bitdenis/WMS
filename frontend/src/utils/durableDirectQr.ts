import type { PreparedQrInput } from './printPreparedQr'

export type DirectQrContext = {
  tenantId: string; userId: string; supplyId: string; orderId: string
  scanId: string; barcode: string; marketplace: 'wildberries'; wbOrderId: number
}
export type DurableQrInput = PreparedQrInput & { context: DirectQrContext }
export type NativeQrJob = {
  idempotencyKey?: string; status?: string; receipt?: string; reason?: string; error?: string
  context?: DirectQrContext; widthMm?: number; heightMm?: number
  hash?: string; parentKey?: string; reprints?: NativeQrJob[]; legacy?: boolean; duplicateRiskAcknowledged?: boolean
}
export type DurableQrAttempt = {
  input: DurableQrInput; createdAt: number; result?: NativeQrJob
  dispatchStartedAt?: number; nativeProtocol?: 1 | 2; acceptedReceipt?: string; legacyObservation?: NativeQrJob
}
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
        if (previous?.dispatchStartedAt && !attempt.dispatchStartedAt) { tx.abort(); return }
        if (previous?.acceptedReceipt && previous.acceptedReceipt !== attempt.acceptedReceipt) { tx.abort(); return }
        store.put(attempt)
      }
      return check
    })
  },
}

function sameContext(a: DirectQrContext, b: DirectQrContext): boolean {
  return Boolean(a && b) && a.tenantId === b.tenantId && a.userId === b.userId && a.supplyId === b.supplyId
    && a.orderId === b.orderId && a.scanId === b.scanId && a.barcode === b.barcode
    && a.marketplace === b.marketplace && a.wbOrderId === b.wbOrderId
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
function accepted(job: NativeQrJob): boolean {
  return typeof job.receipt === 'string' && Boolean(job.receipt.trim()) && (!job.status || ACCEPTED.has(job.status))
}
function matchingReprint(parent: NativeQrJob, child: NativeQrJob, input: DurableQrInput): boolean {
  return parent.idempotencyKey === input.idempotencyKey
    && typeof parent.hash === 'string' && /^[a-f0-9]{64}$/.test(parent.hash)
    && parent.widthMm === input.widthMm && parent.heightMm === input.heightMm
    && Boolean(parent.context && sameContext(parent.context, input.context))
    && typeof child.idempotencyKey === 'string' && Boolean(child.idempotencyKey)
    && child.idempotencyKey !== input.idempotencyKey && child.parentKey === input.idempotencyKey
    && child.duplicateRiskAcknowledged === true
    && child.hash === parent.hash && child.widthMm === input.widthMm && child.heightMm === input.heightMm
    && Boolean(child.context && sameContext(child.context, input.context))
}
export type DurableQrTransport = { fetch: typeof fetch; wait: () => Promise<void>; polls: number }
const transport: DurableQrTransport = {
  fetch: (...args) => fetch(...args), wait: () => new Promise((resolve) => setTimeout(resolve, 500)), polls: 60,
}

const STATES = new Set(['saved', 'submitting', 'unknown', 'accepted', 'pending', 'held', 'processing', 'stopped', 'canceled', 'aborted', 'completed', 'failed_before_submit'])
const malformed = () => new Error('WMS Print вернул повреждённый или несовместимый результат. Исходная попытка сохранена; упаковка не завершена.')
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function validateJob(value: unknown, protocol: 1 | 2): NativeQrJob {
  if (!record(value)) throw malformed()
  if (protocol === 1) {
    if (Object.keys(value).some((key) => key !== 'receipt') || typeof value.receipt !== 'string' || !value.receipt.trim()) throw malformed()
    return value as NativeQrJob
  }
  if (typeof value.idempotencyKey !== 'string' || !value.idempotencyKey
    || typeof value.status !== 'string' || !STATES.has(value.status)
    || typeof value.hash !== 'string' || !/^[a-f0-9]{64}$/.test(value.hash)
    || (value.receipt != null && (typeof value.receipt !== 'string' || !value.receipt.trim()))
    || (value.legacy !== undefined && typeof value.legacy !== 'boolean')) throw malformed()
  if (value.parentKey !== undefined && (typeof value.parentKey !== 'string' || !value.parentKey || value.duplicateRiskAcknowledged !== true)) throw malformed()
  if (ACCEPTED.has(value.status) && (typeof value.receipt !== 'string' || !value.receipt.trim())) throw malformed()
  const context = value.context
  if (value.legacy !== true && (
    typeof value.widthMm !== 'number' || !Number.isFinite(value.widthMm) || value.widthMm <= 0
    || typeof value.heightMm !== 'number' || !Number.isFinite(value.heightMm) || value.heightMm <= 0
    || !record(context)
    || !['tenantId', 'userId', 'supplyId', 'orderId', 'scanId', 'barcode'].every((key) => typeof context[key] === 'string' && Boolean(context[key]))
    || context.marketplace !== 'wildberries' || typeof context.wbOrderId !== 'number' || !Number.isFinite(context.wbOrderId)
  )) throw malformed()
  if (value.reprints !== undefined) {
    if (!Array.isArray(value.reprints)) throw malformed()
    value.reprints.forEach((child) => validateJob(child, 2))
  }
  return value as NativeQrJob
}
export async function directQrHash(input: DurableQrInput, suffix = `|${input.widthMm}x${input.heightMm}`): Promise<string> {
  const encoded = input.imageDataUrl.split(',')[1]
  if (!encoded) throw malformed()
  const bytes = Uint8Array.from(atob(encoded), (char) => char.charCodeAt(0))
  const tail = new TextEncoder().encode(suffix)
  const content = new Uint8Array(bytes.length + tail.length)
  content.set(bytes); content.set(tail, bytes.length)
  const digest = await crypto.subtle.digest('SHA-256', content)
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}
async function diagnoseImportedLegacy(job: NativeQrJob, input: DurableQrInput): Promise<never> {
  const suffixes = ['', `|${input.widthMm}x${input.heightMm}`, `|${Number(input.widthMm).toFixed(1)}x${Number(input.heightMm).toFixed(1)}`]
  let matches = false
  for (const suffix of suffixes) { if (await directQrHash(input, suffix) === job.hash) matches = true }
  throw new Error(matches
    ? 'WMS Print нашёл старую квитанцию исходной этикетки, но в старом журнале нет размера и принадлежности заказу. Результат требует сверки в журнале; упаковка не завершена, новая копия не отправлена.'
    : 'WMS Print сохранил старую квитанцию, но соответствие исходной этикетке не подтверждено. Результат требует сверки; новая копия не отправлена.')
}
const missingHistory = () => new Error('Исходная отправка уже началась, но WMS Print не нашёл её в журнале. Результат неизвестен; новая копия не отправлена. Сохранённые данные и квитанция оставлены для восстановления.')

/** Retains exact artifacts, the pre-POST boundary, and the original queue receipt. */
export async function dispatchDurableQr(input: DurableQrInput, store = qrAttemptStore, io = transport, requireExisting = false): Promise<void> {
  const attempt = await prepareDurableQr(input, store)
  const path = `/jobs/${encodeURIComponent(input.idempotencyKey)}`
  const fetchResponse = async (path: string, method = 'GET', body?: unknown): Promise<Response> => {
    try {
      return await io.fetch(`${BASE}${path}`, {
        method, headers: { 'X-WMS-Print': '1', ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(15_000),
      })
    } catch {
      throw new Error('Нет ответа WMS Print. Исходная этикетка сохранена. Запустите программу и повторите этот штрихкод: сначала будет проверен результат прежнего задания.')
    }
  }
  const healthResponse = await fetchResponse('/health')
  const health: unknown = await healthResponse.json().catch(() => { throw malformed() })
  if (!healthResponse.ok || !record(health) || health.app !== 'WMS Print Direct') throw malformed()
  let protocol: 1 | 2
  if (health.protocolVersion === 2) protocol = 2
  else if (health.protocolVersion === undefined && typeof health.printer === 'string' && health.printer.trim()) protocol = 1
  else throw malformed()
  const saveResult = async (job: NativeQrJob) => {
    const knownReceipt = attempt.acceptedReceipt ?? (typeof attempt.result?.receipt === 'string' ? attempt.result.receipt : undefined)
    if (knownReceipt && job.receipt && knownReceipt !== job.receipt) throw missingHistory()
    attempt.acceptedReceipt = knownReceipt ?? job.receipt
    attempt.result = job
    await store.put(attempt)
  }
  const request = async (path: string, method = 'GET', body?: unknown, expectedKey = input.idempotencyKey): Promise<NativeQrJob | null> => {
    const response = await fetchResponse(path, method, body)
    if (method === 'GET' && response.status === 404) return null
    const raw: unknown = await response.json().catch(() => { throw malformed() })
    if (!response.ok) throw new Error(record(raw) && typeof raw.error === 'string' ? raw.error : 'Не удалось прочитать результат WMS Print.')
    const job = validateJob(raw, protocol)
    if (job.legacy === true) {
      attempt.legacyObservation = job
      await store.put(attempt)
      await diagnoseImportedLegacy(job, input)
    }
    if (protocol === 2) {
      // Python uses :g, while Swift's retained releases serialize whole Double
      // dimensions with .0. Both hashes bind the same exact bytes and sizes.
      const nativeDouble = (value: number) => Number.isInteger(value) ? value.toFixed(1) : String(value)
      const hashes = await Promise.all([directQrHash(input), directQrHash(input, `|${nativeDouble(input.widthMm)}x${nativeDouble(input.heightMm)}`)])
      if (!hashes.includes(job.hash!)) throw malformed()
    }
    if ((job.idempotencyKey && job.idempotencyKey !== expectedKey)
      || (job.legacy !== true && job.context && !sameContext(job.context, input.context))
      || (job.widthMm != null && job.widthMm !== input.widthMm)
      || (job.heightMm != null && job.heightMm !== input.heightMm)) {
      throw new Error('WMS Print вернул результат другого задания. Повторная печать не отправлена.')
    }
    if (expectedKey === input.idempotencyKey) await saveResult(job)
    return job
  }
  const beginDispatch = async () => {
    if (requireExisting || attempt.dispatchStartedAt || attempt.result || attempt.acceptedReceipt || attempt.legacyObservation) throw missingHistory()
    attempt.dispatchStartedAt = Date.now()
    attempt.nativeProtocol = protocol
    await store.put(attempt) // A crash from this point onward is an unknown dispatch, never a new first call.
  }
  if (protocol === 1) {
    if (attempt.dispatchStartedAt || attempt.result || requireExisting) {
      // The old helper exposes no instance identity or read endpoint. Never replay
      // an uncertain POST against it. A previously committed legacy receipt is enough.
      if (attempt.nativeProtocol === 1 && attempt.result && accepted(validateJob(attempt.result, 1))) return
      throw missingHistory()
    }
    await beginDispatch()
    const legacy = await request('/print', 'POST', input)
    if (legacy && accepted(legacy)) return
    throw malformed()
  }
  let job = await request(path)
  if (!job) {
    await beginDispatch()
    job = await request('/print', 'POST', { ...input, protocolVersion: 2 })
  } else if (!job.reprints?.length && ['saved', 'failed_before_submit'].includes(job.status ?? '')) {
    job = await request(`${path}/retry`, 'POST')
  } else if (!job.reprints?.length && (job.status === 'unknown' || job.status === 'submitting')) {
    job = await request(`${path}/reconcile`, 'POST')
  }
  for (let poll = 0; job && ['saved', 'submitting'].includes(job.status ?? '') && poll < io.polls; poll++) {
    await io.wait()
    job = await request(path)
  }
  if (job && accepted(job)) return
  const child = job?.reprints?.slice().reverse().find((candidate) => matchingReprint(job!, candidate, input))
  if (job && child?.idempotencyKey) {
    const reconciled = await request(`/jobs/${encodeURIComponent(child.idempotencyKey)}/reconcile`, 'POST', undefined, child.idempotencyKey)
    job = await request(path)
    const currentChild = job?.reprints?.find((candidate) => candidate.idempotencyKey === child.idempotencyKey)
    if (job && reconciled && currentChild
      && matchingReprint(job, reconciled, input) && matchingReprint(job, currentChild, input)
      && reconciled.status && currentChild.status && accepted(reconciled) && accepted(currentChild)) return
  }
  const labels: Record<string, string> = {
    saved: 'сохранено, ожидает отправки', submitting: 'результат передачи ещё не установлен',
    unknown: 'результат передачи неизвестен', canceled: 'задание отменено', aborted: 'очередь прервала задание',
    stopped: 'очередь остановлена', held: 'задание удерживается очередью', failed_before_submit: 'не передано в очередь',
  }
  throw new Error(`WMS Print: ${labels[job?.status ?? ''] ?? 'приём этикетки не подтверждён'}${job?.reason ? ` (${job.reason})` : ''}. Заказ WB № ${input.context.wbOrderId}, штрихкод ${input.context.barcode}, задание ${input.idempotencyKey}. Исходная этикетка сохранена. Повторите этот штрихкод для проверки и восстановления; журнал: ${BASE}/jobs.`)
}
