/** Same native printer transport for the scan check and actual FBS labels. */
export type PreparedQrInput = {
  imageDataUrl: string
  idempotencyKey: string
  widthMm: number
  heightMm: number
}

export async function printPreparedQr(input: PreparedQrInput): Promise<void> {
  let response: Response
  try {
    response = await fetch('http://127.0.0.1:17845/print-image', {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: input.idempotencyKey,
        image_data_url: input.imageDataUrl,
        width_mm: input.widthMm,
        height_mm: input.heightMm,
      }),
      signal: AbortSignal.timeout(70_000),
    })
  } catch {
    // No fallback and no automatic retry: a lost response can follow an
    // accepted spooler job. Reusing this UUID is safe at the bridge boundary.
    throw new Error('Нет связи с программой печати. Проверьте её запуск и разрешение локальной сети в Chrome; если этикетка уже отправлялась, проверьте очередь принтера.')
  }
  let result: { job_id?: string; status?: string; receipt?: string; error?: string }
  try {
    result = await response.json()
  } catch {
    throw new Error('Программа печати не вернула квитанцию. Проверьте очередь принтера.')
  }
  if (!response.ok) throw new Error(result.error || 'Принтер не принял этикетку')
  if (result.job_id !== input.idempotencyKey || result.status !== 'submitted' || !result.receipt) {
    throw new Error('Квитанция печати не подтверждена. Проверьте очередь принтера.')
  }
}
