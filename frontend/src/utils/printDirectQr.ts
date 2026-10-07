import type { PreparedQrInput } from './printPreparedQr'

/** A receipt means accepted by the OS queue, not confirmed paper output. */
async function dispatch(input: PreparedQrInput): Promise<void> {
  await input.beforeDispatch?.()
  let response: Response
  try {
    response = await fetch('http://127.0.0.1:17843/print', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-WMS-Print': '1' },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(30_000),
    })
  } catch {
    throw new Error('Нет ответа WMS Print. Запустите программу. Если Chrome запросил доступ к этому компьютеру — разрешите его. Перед повтором проверьте очередь принтера.')
  }
  const result = await response.json() as { receipt?: string; error?: string }
  if (!response.ok || !result.receipt) throw new Error(result.error || 'Принтер не подтвердил приём этикетки')
}

let queue: Promise<void> = Promise.resolve()
export function printDirectQr(input: PreparedQrInput): Promise<void> {
  const result = queue.then(() => dispatch(input), () => dispatch(input))
  queue = result.catch(() => undefined)
  return result
}
