import type { PreparedQrInput } from './printPreparedQr'
import { postDirectQr, type DirectQrAnswer } from './printDirectQr'

/**
 * WMS-625: the order QR of a packing scan sent to WMS Print.
 *
 * The first label of a key is exactly one production POST /print (plus the
 * order context and protocolVersion 2, which older programs ignore). The answer
 * tells which program printed it: v2026.09.30.4/.5 return their receipt, a WMS
 * Print with a job journal returns the job, whose queue state is then followed.
 * The browser record (IndexedDB) is kept best-effort: it carries the exact label
 * and what each program answered, but its failure never stops a scan. Every
 * program keeps the job by key, so a retry of the key is the same job.
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
  /** A WMS Print without a journal returned its receipt for this exact label. */
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
const IDENTITY = ['tenantId', 'userId', 'supplyId', 'orderId', 'scanId', 'marketplace', 'wbOrderId'] as const
function sameIdentity(a: DirectQrContext, b: DirectQrContext): boolean {
  return Boolean(a && b) && IDENTITY.every((key) => a[key] === b[key])
}
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
/**
 * A job kept without the order (sent by the production request) carries no
 * context; a job with context must not name another client, operator or order.
 */
function contextAgrees(context: unknown, input: DirectQrContext): boolean {
  if (context === undefined || context === null) return true
  if (!record(context)) return false
  return IDENTITY.every((key) => context[key] === undefined || context[key] === input[key])
}
function hasContext(context: unknown): boolean {
  return record(context) && Object.keys(context).length > 0
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
/** The browser record never stops a scan: unreadable or foreign records count as none. */
async function readAttempt(input: DurableQrInput, store: QrAttemptStore): Promise<DurableQrAttempt | undefined> {
  try { return await restoreDurableQr(input.idempotencyKey, input.context, store) } catch { return undefined }
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
    && contextAgrees(parent.context, input.context)
    && typeof child.idempotencyKey === 'string' && Boolean(child.idempotencyKey)
    && child.idempotencyKey !== input.idempotencyKey && child.parentKey === input.idempotencyKey
    && child.duplicateRiskAcknowledged === true
    && child.hash === parent.hash && child.widthMm === input.widthMm && child.heightMm === input.heightMm
    // The program copies the parent's order into its explicit copy.
    && hasContext(child.context) === hasContext(parent.context) && contextAgrees(child.context, input.context)
}
export type DurableQrTransport = {
  fetch: typeof fetch
  /** The production POST /print (printDirectQr's request and queue), answer as is. */
  post: (body: unknown) => Promise<DirectQrAnswer>
  wait: (poll: number) => Promise<void>
  polls: number
  now: () => number
}
const transport: DurableQrTransport = {
  fetch: (...args) => fetch(...args),
  post: (body) => postDirectQr(body),
  // The queue usually accepts within a fraction of a second; then poll calmly.
  wait: (poll) => new Promise((resolve) => setTimeout(resolve, poll < 20 ? 100 : 500)),
  polls: 60,
  now: () => Date.now(),
}

const STATES = new Set(['saved', 'submitting', 'unknown', 'accepted', 'pending', 'held', 'processing', 'stopped', 'canceled', 'aborted', 'completed', 'failed_before_submit'])
const malformed = () => new Error('WMS Print вернул повреждённый или несовместимый результат. Исходная попытка сохранена; упаковка не завершена.')
/**
 * A job of a WMS Print with a journal, as opposed to the bare `{receipt}` or `{error}`
 * of v2026.09.30.4/.5. Anything job-shaped is validated as a job, never taken for a receipt.
 */
function isJob(value: unknown): value is Record<string, unknown> {
  return record(value) && ['idempotencyKey', 'status', 'hash'].some((key) => key in value)
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
  if (value.legacy !== true && (
    typeof value.widthMm !== 'number' || !Number.isFinite(value.widthMm) || value.widthMm <= 0
    || typeof value.heightMm !== 'number' || !Number.isFinite(value.heightMm) || value.heightMm <= 0
    || (value.context !== undefined && value.context !== null && !record(value.context))
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
/** Python formats sizes with :g, Swift (also the old .4) whole Doubles with .0; .3 hashed the PNG alone. */
async function labelHashes(input: DurableQrInput, withoutSize = false): Promise<string[]> {
  const nativeDouble = (value: number) => Number.isInteger(value) ? value.toFixed(1) : String(value)
  const suffixes = [`|${input.widthMm}x${input.heightMm}`, `|${nativeDouble(input.widthMm)}x${nativeDouble(input.heightMm)}`]
  if (withoutSize) suffixes.push('')
  return Promise.all(suffixes.map((suffix) => directQrHash(input, suffix)))
}

/**
 * Exactly one production POST for a key the program has not answered with a
 * receipt; a journal job is then followed by key. Never stops on browser storage.
 */
export async function dispatchDurableQr(input: DurableQrInput, store = qrAttemptStore, io = transport, requireExisting = false): Promise<void> {
  const saved = await readAttempt(input, store)
  const attempt: DurableQrAttempt = saved ?? { input, createdAt: io.now() }
  // The first saved label of this key is the one printed, whatever was preloaded now.
  const exact = attempt.input
  const keep = async () => {
    try { await store.put(attempt) } catch { /* the browser record never stops a scan */ }
  }
  // A program without a journal returned its receipt for this label (it would return it again).
  if (attempt.legacyAcceptedAt) return
  const path = `/jobs/${encodeURIComponent(exact.idempotencyKey)}`
  const call = async (path: string, method = 'GET'): Promise<Response> => {
    try {
      return await io.fetch(`${BASE}${path}`, { method, headers: { 'X-WMS-Print': '1' }, signal: AbortSignal.timeout(15_000) })
    } catch {
      throw new Error('Нет ответа WMS Print. Запустите программу и повторите этот штрихкод: сначала будет проверен результат прежнего задания.')
    }
  }
  /** Checks that the answer is this job, records it, and settles an imported old-journal entry. */
  const accept = async (raw: unknown, expectedKey = exact.idempotencyKey): Promise<NativeQrJob | 'done'> => {
    const job = validateJob(raw)
    const own = expectedKey === exact.idempotencyKey
    if (job.legacy === true) {
      if (!own || job.idempotencyKey !== expectedKey) throw new Error('WMS Print вернул результат другого задания. Повторная печать не отправлена.')
      // F4: the receipt an older program kept for exactly this label completes it, as it would for a repeated POST.
      if (job.receipt && accepted(job) && (await labelHashes(exact, true)).includes(job.hash!)) {
        attempt.legacyAcceptedAt = io.now()
        await keep()
        return 'done'
      }
      attempt.legacyObservation = job
      await keep()
      throw new Error(job.receipt
        ? 'WMS Print нашёл старую квитанцию по этому ключу, но с другой этикеткой. Новая копия не отправлена; сверьте задание в журнале WMS Print.'
        : 'Старая версия WMS Print начала передачу этой этикетки, но не записала результат. Новая копия не отправлена; проверьте очередь принтера.')
    }
    if (!(await labelHashes(exact)).includes(job.hash!)) throw malformed()
    if (job.idempotencyKey !== expectedKey || !contextAgrees(job.context, exact.context)
      || (job.widthMm != null && job.widthMm !== exact.widthMm)
      || (job.heightMm != null && job.heightMm !== exact.heightMm)) {
      throw new Error('WMS Print вернул результат другого задания. Повторная печать не отправлена.')
    }
    if (own) {
      attempt.nativeProtocol = 2
      attempt.result = job
      if (!attempt.acceptedReceipt && accepted(job)) attempt.acceptedReceipt = job.receipt
      await keep()
    }
    return job
  }
  /** A journal request: GET returns null for an unknown key. */
  const request = async (path: string, method = 'GET', expectedKey = exact.idempotencyKey): Promise<NativeQrJob | 'done' | null> => {
    const response = await call(path, method)
    if (method === 'GET' && response.status === 404) return null
    const raw: unknown = await response.json().catch(() => { throw malformed() })
    if (!response.ok) throw new Error(record(raw) && typeof raw.error === 'string' ? raw.error : 'Не удалось прочитать результат WMS Print.')
    return accept(raw, expectedKey)
  }
  const settle = async (found: NativeQrJob | 'done' | null, existing: boolean): Promise<void> => {
    if (found === 'done') return
    let job = found
    if (job && !job.reprints?.length) {
      // A job found again: send only what the program proved unsent, re-read an unknown outcome.
      if (['failed_before_submit', ...(existing ? ['saved'] : [])].includes(job.status ?? '')) {
        const retried = await request(`${path}/retry`, 'POST'); if (retried === 'done') return; job = retried
      } else if (job.status === 'unknown' || (existing && job.status === 'submitting')) {
        const reconciled = await request(`${path}/reconcile`, 'POST'); if (reconciled === 'done') return; job = reconciled
      }
    }
    for (let poll = 0; job && ['saved', 'submitting'].includes(job.status ?? '') && poll < io.polls; poll++) {
      await io.wait(poll)
      const next = await request(path)
      if (next === 'done') return
      job = next
    }
    if (job && accepted(job)) return
    const parent = job
    const child = parent?.reprints?.slice().reverse().find((candidate) => matchingReprint(parent, candidate, exact))
    if (parent && child?.idempotencyKey) {
      const reconciled = await request(`/jobs/${encodeURIComponent(child.idempotencyKey)}/reconcile`, 'POST', child.idempotencyKey)
      const again = await request(path)
      if (again === 'done') return
      job = again
      const currentChild = job?.reprints?.find((candidate) => candidate.idempotencyKey === child.idempotencyKey)
      if (job && reconciled && reconciled !== 'done' && currentChild
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

  // The server already marked the label started. Only a program with a journal that
  // got this key can add anything; with an older one nothing is asked, as before.
  // The same once a journal program accepted it: its later queue state is reported,
  // and if the program no longer answers or no longer knows the key, the receipt stands.
  if (requireExisting || (attempt.acceptedReceipt && attempt.nativeProtocol === 2)) {
    if (attempt.nativeProtocol !== 2) return
    let found: NativeQrJob | 'done' | null
    // No answer, an unknown key or an unreadable answer adds nothing to the server's mark.
    try { found = await request(path) } catch { return }
    if (!found) return
    return settle(found, true)
  }

  // One production POST. The same key again is the same job in every WMS Print version.
  attempt.dispatchStartedAt ??= io.now()
  await keep()
  const answer = await io.post({ ...exact, protocolVersion: 2 })
  if (answer.ok && isJob(answer.result)) return settle(await accept(answer.result), false)
  // The answer of a program without a journal: the production rule, unchanged.
  const legacy = (record(answer.result) ? answer.result : {}) as { receipt?: unknown; error?: unknown }
  if (!answer.ok || typeof legacy.receipt !== 'string' || !legacy.receipt) {
    throw new Error(typeof legacy.error === 'string' && legacy.error ? legacy.error : 'Принтер не подтвердил приём этикетки')
  }
  attempt.legacyAcceptedAt = io.now()
  attempt.nativeProtocol ??= 1
  await keep()
}
