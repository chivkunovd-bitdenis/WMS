import type { PreparedQrInput } from './printPreparedQr'
import { printDirectQr } from './printDirectQr'

/**
 * WMS-625: the order QR of a packing scan sent to WMS Print.
 *
 * WMS Print with protocol 2 keeps every job (exact PNG, size, key, order) and
 * reports the queue state; the browser keeps the same attempt before the first
 * request, so a lost answer, a reload or a stopped program is recovered by the
 * same key without a second copy. An older WMS Print answers only POST /print:
 * with it the label goes exactly as before (one POST, its receipt, its errors).
 */
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
  /** An older WMS Print returned its receipt for this exact label (it keeps the job by key). */
  legacyAcceptedAt?: number
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

/**
 * One job identity: the client, operator, supply, order and scan key. The
 * scanned barcode is recorded with the job but is not its identity: the same
 * order QR may be resumed by its sticker or its row (WMS-631).
 */
function sameIdentity(a: DirectQrContext, b: DirectQrContext): boolean {
  return Boolean(a && b) && a.tenantId === b.tenantId && a.userId === b.userId && a.supplyId === b.supplyId
    && a.orderId === b.orderId && a.scanId === b.scanId
    && a.marketplace === b.marketplace && a.wbOrderId === b.wbOrderId
}
export async function restoreDurableQr(key: string, context: DirectQrContext, store = qrAttemptStore): Promise<DurableQrAttempt | undefined> {
  const saved = await store.get(key)
  if (saved && (!saved.input || !sameIdentity(saved.input.context, context) || saved.input.idempotencyKey !== key
    || typeof saved.input.imageDataUrl !== 'string' || !(saved.input.widthMm > 0) || !(saved.input.heightMm > 0))) {
    throw new Error('Сохранённая попытка печати не соответствует этому заказу. Исходные данные сохранены; новая печать не отправлена.')
  }
  return saved
}
/** The first saved label of a key stays authoritative: a later preload never replaces it. */
export async function prepareDurableQr(input: DurableQrInput, store = qrAttemptStore): Promise<DurableQrAttempt> {
  const saved = await restoreDurableQr(input.idempotencyKey, input.context, store)
  if (saved) return saved
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
    && Boolean(parent.context && sameIdentity(parent.context, input.context))
    && typeof child.idempotencyKey === 'string' && Boolean(child.idempotencyKey)
    && child.idempotencyKey !== input.idempotencyKey && child.parentKey === input.idempotencyKey
    && child.duplicateRiskAcknowledged === true
    && child.hash === parent.hash && child.widthMm === input.widthMm && child.heightMm === input.heightMm
    && Boolean(child.context && sameIdentity(child.context, input.context))
}
export type DurableQrTransport = {
  fetch: typeof fetch
  /** The production request: POST /print, its receipt and its errors (printDirectQr). */
  legacy: (input: PreparedQrInput) => Promise<void>
  wait: (poll: number) => Promise<void>
  polls: number
  now: () => number
  /** Last answer of /health; an older WMS Print never pays for a second probe within a minute. */
  protocol?: { value: 1 | 2; at: number }
}
const transport: DurableQrTransport = {
  fetch: (...args) => fetch(...args),
  legacy: (input) => printDirectQr(input),
  // The queue usually accepts within a fraction of a second; then poll calmly.
  wait: (poll) => new Promise((resolve) => setTimeout(resolve, poll < 20 ? 100 : 500)),
  polls: 60,
  now: () => Date.now(),
}
const PROTOCOL_TTL_MS = 60_000
/** Test helper: forget the program version seen by the page. */
export function forgetDirectQrProtocol(io: DurableQrTransport = transport): void {
  io.protocol = undefined
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
/**
 * Protocol 2 only when WMS Print says so. Anything else — an older program,
 * its 503 without a default printer, a missing /health, no answer — keeps the
 * production request, which reports such a state exactly as before.
 */
async function nativeProtocol(io: DurableQrTransport): Promise<1 | 2> {
  if (io.protocol && io.now() - io.protocol.at < PROTOCOL_TTL_MS) return io.protocol.value
  let response: Response
  try {
    response = await io.fetch(`${BASE}/health`, { method: 'GET', headers: { 'X-WMS-Print': '1' }, signal: AbortSignal.timeout(3_000) })
  } catch {
    return 1
  }
  const health: unknown = response.ok ? await response.json().catch(() => null) : null
  const value = record(health) && health.app === 'WMS Print Direct' && health.protocolVersion === 2 ? 2 : 1
  io.protocol = { value, at: io.now() }
  return value
}

const STATES = new Set(['saved', 'submitting', 'unknown', 'accepted', 'pending', 'held', 'processing', 'stopped', 'canceled', 'aborted', 'completed', 'failed_before_submit'])
const malformed = () => new Error('WMS Print вернул повреждённый или несовместимый результат. Исходная попытка сохранена; упаковка не завершена.')
function isLegacyReceipt(value: unknown): value is { receipt: string } {
  return record(value) && Object.keys(value).length === 1 && typeof value.receipt === 'string' && Boolean(value.receipt.trim())
}
function validateJob(value: unknown): NativeQrJob {
  if (!record(value)) throw malformed()
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
    value.reprints.forEach((child) => validateJob(child))
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
const versionLost = () => new Error('Исходная отправка уже началась в WMS Print с журналом заданий, а сейчас программа не отвечает как эта версия. Результат неизвестен; новая копия не отправлена. Запустите WMS Print и повторите этот штрихкод.')

/**
 * The older WMS Print: the production request (printDirectQr). The order context
 * travels along: v2026.09.30.4/.5 read only the key, the PNG and the size and
 * ignore it, while a WMS Print with a journal reached this way (its /health did
 * not answer in time, or it was installed within the last minute) keeps the job
 * with its order, so a later retry of the key is recognised as the same job.
 * The browser record is a convenience here (the same exact label for a retry of
 * the key, a mark of the receipt), so a browser storage failure never stops it.
 */
async function dispatchLegacy(input: DurableQrInput, store: QrAttemptStore, io: DurableQrTransport, requireExisting: boolean): Promise<void> {
  // The server already marked the label started; an older program confirms nothing more.
  if (requireExisting) return
  let saved: DurableQrAttempt | undefined
  try { saved = await restoreDurableQr(input.idempotencyKey, input.context, store) } catch { saved = undefined }
  // This program already returned its receipt for this exact label (it would return it again).
  if (saved?.legacyAcceptedAt) return
  // A job handed to a WMS Print with a journal is never re-sent to a program without one.
  if (saved && (saved.dispatchStartedAt || saved.result || saved.acceptedReceipt)) throw versionLost()
  const attempt: DurableQrAttempt = saved ?? { input, createdAt: io.now(), nativeProtocol: 1 }
  if (!saved) {
    try { await store.put(attempt) } catch { /* the production path never depended on browser storage */ }
  }
  await io.legacy(attempt.input)
  try { await store.put({ ...attempt, legacyAcceptedAt: io.now() }) } catch { /* as above */ }
}

/** Retains exact artifacts, the pre-POST boundary, and the original queue receipt. */
export async function dispatchDurableQr(input: DurableQrInput, store = qrAttemptStore, io = transport, requireExisting = false): Promise<void> {
  const protocol = await nativeProtocol(io)
  if (protocol === 1) return dispatchLegacy(input, store, io, requireExisting)
  const saved = await restoreDurableQr(input.idempotencyKey, input.context, store)
  // An older WMS Print already returned its receipt for this exact label.
  if (saved?.legacyAcceptedAt) return
  // The first saved label of this key is the one printed, whatever was preloaded now.
  const exact = saved?.input ?? input
  let attempt = saved
  // R13: the exact label, key and order are committed before any request that may print.
  if (!attempt && !requireExisting) attempt = await prepareDurableQr(exact, store)
  const own = async (): Promise<DurableQrAttempt> => attempt ??= await prepareDurableQr(exact, store)
  const path = `/jobs/${encodeURIComponent(exact.idempotencyKey)}`
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
  const saveResult = async (job: NativeQrJob) => {
    const current = await own()
    const knownReceipt = current.acceptedReceipt ?? (typeof current.result?.receipt === 'string' ? current.result.receipt : undefined)
    if (knownReceipt && job.receipt && knownReceipt !== job.receipt) throw missingHistory()
    current.acceptedReceipt = knownReceipt ?? job.receipt
    current.result = job
    await store.put(current)
  }
  type Answer = NativeQrJob | 'legacy-accepted' | null
  const request = async (path: string, method = 'GET', body?: unknown, expectedKey = exact.idempotencyKey): Promise<Answer> => {
    const response = await fetchResponse(path, method, body)
    if (method === 'GET' && response.status === 404) return null
    const raw: unknown = await response.json().catch(() => { throw malformed() })
    if (!response.ok) throw new Error(record(raw) && typeof raw.error === 'string' ? raw.error : 'Не удалось прочитать результат WMS Print.')
    // The program was replaced by an older one since /health: it printed and kept the job by key.
    if (path === '/print' && isLegacyReceipt(raw)) {
      io.protocol = undefined
      const current = await own()
      current.legacyAcceptedAt = io.now()
      await store.put(current)
      return 'legacy-accepted'
    }
    const job = validateJob(raw)
    if (job.legacy === true) {
      const current = await own()
      current.legacyObservation = job
      await store.put(current)
      await diagnoseImportedLegacy(job, exact)
    }
    // Python uses :g, while Swift's retained releases serialize whole Double
    // dimensions with .0. Both hashes bind the same exact bytes and sizes.
    const nativeDouble = (value: number) => Number.isInteger(value) ? value.toFixed(1) : String(value)
    const hashes = await Promise.all([directQrHash(exact), directQrHash(exact, `|${nativeDouble(exact.widthMm)}x${nativeDouble(exact.heightMm)}`)])
    if (!hashes.includes(job.hash!)) throw malformed()
    if ((job.idempotencyKey && job.idempotencyKey !== expectedKey)
      || (job.legacy !== true && job.context && !sameIdentity(job.context, exact.context))
      || (job.widthMm != null && job.widthMm !== exact.widthMm)
      || (job.heightMm != null && job.heightMm !== exact.heightMm)) {
      throw new Error('WMS Print вернул результат другого задания. Повторная печать не отправлена.')
    }
    if (expectedKey === exact.idempotencyKey) await saveResult(job)
    return job
  }
  const asJob = (answer: Answer): NativeQrJob | null => (answer === 'legacy-accepted' ? null : answer)
  const beginDispatch = async () => {
    const current = await own()
    if (requireExisting || current.dispatchStartedAt || current.result || current.acceptedReceipt || current.legacyObservation) throw missingHistory()
    current.dispatchStartedAt = Date.now()
    current.nativeProtocol = 2
    await store.put(current) // A crash from this point onward is an unknown dispatch, never a new first call.
  }
  const first = await request(path)
  if (first === 'legacy-accepted') return
  let job = first
  if (!job) {
    // The server marked this label started, and this browser never sent it to this program.
    if (requireExisting && !attempt) return
    await beginDispatch()
    const posted = await request('/print', 'POST', { ...exact, protocolVersion: 2 })
    if (posted === 'legacy-accepted') return
    job = posted
  } else if (!job.reprints?.length && ['saved', 'failed_before_submit'].includes(job.status ?? '')) {
    job = asJob(await request(`${path}/retry`, 'POST'))
  } else if (!job.reprints?.length && (job.status === 'unknown' || job.status === 'submitting')) {
    job = asJob(await request(`${path}/reconcile`, 'POST'))
  }
  for (let poll = 0; job && ['saved', 'submitting'].includes(job.status ?? '') && poll < io.polls; poll++) {
    await io.wait(poll)
    job = asJob(await request(path))
  }
  if (job && accepted(job)) return
  const child = job?.reprints?.slice().reverse().find((candidate) => matchingReprint(job!, candidate, exact))
  if (job && child?.idempotencyKey) {
    const reconciled = asJob(await request(`/jobs/${encodeURIComponent(child.idempotencyKey)}/reconcile`, 'POST', undefined, child.idempotencyKey))
    job = asJob(await request(path))
    const currentChild = job?.reprints?.find((candidate) => candidate.idempotencyKey === child.idempotencyKey)
    if (job && reconciled && currentChild
      && matchingReprint(job, reconciled, exact) && matchingReprint(job, currentChild, exact)
      && reconciled.status && currentChild.status && accepted(reconciled) && accepted(currentChild)) return
  }
  const labels: Record<string, string> = {
    saved: 'сохранено, ожидает отправки', submitting: 'результат передачи ещё не установлен',
    unknown: 'результат передачи неизвестен', canceled: 'задание отменено', aborted: 'очередь прервала задание',
    stopped: 'очередь остановлена', held: 'задание удерживается очередью', failed_before_submit: 'не передано в очередь',
  }
  throw new Error(`WMS Print: ${labels[job?.status ?? ''] ?? 'приём этикетки не подтверждён'}${job?.reason ? ` (${job.reason})` : ''}. Заказ WB № ${exact.context.wbOrderId}, штрихкод ${exact.context.barcode}, задание ${exact.idempotencyKey}. Исходная этикетка сохранена. Повторите этот штрихкод для проверки и восстановления; журнал: ${BASE}.`)
}
