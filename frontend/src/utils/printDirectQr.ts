import type { PreparedQrInput } from './printPreparedQr'

export type DirectQrAnswer = { ok: boolean; status: number; result: unknown }

/** The production request to WMS Print: one POST /print, 30 seconds, the same texts. */
async function post(body: unknown): Promise<DirectQrAnswer> {
  let response: Response
  try {
    response = await fetch('http://127.0.0.1:17843/print', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-WMS-Print': '1' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    })
  } catch {
    throw new Error('Нет ответа WMS Print. Запустите программу. Если Chrome запросил доступ к этому компьютеру — разрешите его. Перед повтором проверьте очередь принтера.')
  }
  const result: unknown = await response.json()
  return { ok: response.ok, status: response.status, result }
}

/** A receipt means accepted by the OS queue, not confirmed paper output. */
async function dispatch(input: PreparedQrInput): Promise<void> {
  const { ok, result } = await post(input)
  const answer = result as { receipt?: string; error?: string }
  if (!ok || !answer.receipt) throw new Error(answer.error || 'Принтер не подтвердил приём этикетки')
}

// Labels go to WMS Print strictly one after another, whatever sends them.
let queue: Promise<void> = Promise.resolve()
function serial<T>(task: () => Promise<T>): Promise<T> {
  const result = queue.then(task, task)
  queue = result.then(() => undefined, () => undefined)
  return result
}

export function printDirectQr(input: PreparedQrInput): Promise<void> {
  return serial(() => dispatch(input))
}

/**
 * WMS-625: the same request in the same queue, returning WMS Print's answer as is:
 * an older program answers its receipt, a program with a job journal its job.
 */
export function postDirectQr(body: unknown): Promise<DirectQrAnswer> {
  return serial(() => post(body))
}
