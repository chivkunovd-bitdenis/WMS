import { describe, expect, it } from 'vitest'
import { allProducts } from './InventoryRows'
import {
  createCountOps,
  type CommentChange,
  type CountOpKind,
  type CountTransport,
  type LineValue,
  type ScanPlace,
} from './countOpsQueue'
import type { InventoryCount, ProductNode } from './InventoryTypes'

// WMS-542. Сценарии обоих ревью Astra (docs/reviews/artifacts/wms-542/
// review-astra-1.md и review-astra-2.md) против единой очереди операций.
//
// Сервер здесь — управляемая подделка с той же семантикой, что у настоящего:
// PUT /lines присваивает абсолютное число, POST /found делает +1 и помнит
// scan_id, комментарий сверяется с expected_comment. Каждый запрос попадает
// в журнал `calls` и ждёт, пока тест его не выполнит на сервере (`exec`) и
// не доставит ответ (`deliver`) — или не потеряет его (`lose`). Так
// моделируются и задержка выполнения запроса, и задержка/потеря ответа.

class HttpError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

type ServerLine = { id: string; actual: number | null; expected: number; codes: string[] }

class FakeServer {
  lines: ServerLine[]
  comment = ''
  scans = new Set<string>()
  /** Коды маркетплейса, которых нет в дереве документа (Ozon: OZN<sku>). */
  marketplaceCodes = new Map<string, string>()
  newLines = 0

  constructor(lines: Array<[string, number | null]>) {
    this.lines = lines.map(([id, actual]) => ({ id, actual, expected: 5, codes: [`bc-${id}`.toLowerCase()] }))
  }

  value(id: string): number | null | undefined {
    return this.lines.find((line) => line.id === id)?.actual
  }

  doc(): InventoryCount {
    const products: ProductNode[] = this.lines.map((line) => ({
      kind: 'product',
      id: line.id,
      name: `Товар ${line.id}`,
      sku: `SKU-${line.id}`,
      seller: 'Селлер',
      category: '—',
      barcode: `BC-${line.id}`,
      wbBarcode: `BC-${line.id}`,
      photoUrl: null,
      expected: line.expected,
      actual: line.actual,
    }))
    return {
      id: 'count-1',
      number: 'ИНВ-1',
      status: 'draft',
      warehouseName: 'Склад',
      fill: { mode: 'all' },
      createdAt: '',
      createdBy: '',
      postedAt: null,
      postedBy: null,
      comment: this.comment,
      addressStorage: true,
      cells: [{ id: 'cell-1', label: 'A-1', barcode: null, children: products }],
      scannableCells: [],
      scannableContainers: [],
    }
  }

  /** Скан другого оператора — прямо на сервере, мимо этого экрана. */
  otherScan(id: string, times = 1): void {
    for (let i = 0; i < times; i += 1) this.found({ barcodes: [`BC-${id}`], cellId: 'cell-1', containerKind: null, containerId: null, scanId: `other-${Math.random()}`, lineId: id })
  }

  found(place: ScanPlace): { count: InventoryCount; notice: string } {
    if (this.scans.has(place.scanId)) return { count: this.doc(), notice: '' }
    const codes = place.barcodes.map((code) => code.toLowerCase())
    let line: ServerLine | undefined
    if (place.lineId) {
      line = this.lines.find((item) => item.id === place.lineId)
      if (!line) throw new HttpError('line_not_found', 422)
      if (!line.codes.some((code) => codes.includes(code))) throw new HttpError('line_barcode_mismatch', 422)
    } else {
      line = this.lines.find((item) => item.codes.some((code) => codes.includes(code)))
      if (!line) {
        const viaMarketplace = codes.map((code) => this.marketplaceCodes.get(code)).find(Boolean)
        line = this.lines.find((item) => item.id === viaMarketplace)
      }
      if (!line) {
        this.newLines += 1
        line = { id: `N${this.newLines}`, actual: 0, expected: 0, codes }
        this.lines.push(line)
        line.actual = 1
        this.scans.add(place.scanId)
        return { count: this.doc(), notice: 'По учёту здесь ничего не числится — записали находку.' }
      }
    }
    line.actual = (line.actual ?? 0) + 1
    this.scans.add(place.scanId)
    return { count: this.doc(), notice: '' }
  }

  put(lines: LineValue[], comment?: CommentChange): InventoryCount {
    if (comment && comment.expected !== this.comment) throw new HttpError('comment_changed', 409)
    for (const item of lines) {
      if (!this.lines.some((line) => line.id === item.lineId)) throw new HttpError('line_not_found', 422)
    }
    for (const item of lines) {
      const line = this.lines.find((row) => row.id === item.lineId) as ServerLine
      line.actual = item.value
    }
    if (comment) this.comment = comment.value.trim()
    return this.doc()
  }
}

type Call = {
  kind: 'found' | 'put' | 'get'
  body: unknown
  /** Сервер выполнил запрос (ответ ещё не доставлен). */
  exec: () => void
  /** Выполнить (если ещё не) и доставить ответ. */
  deliver: () => void
  /** Связь оборвалась: ответ не доехал (сам запрос мог и выполниться). */
  lose: () => void
}

function controlled(server: FakeServer) {
  const calls: Call[] = []
  let auto = false
  function defer<T>(kind: Call['kind'], body: unknown, run: () => T): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      let executed = false
      let result: T | undefined
      let failure: unknown
      const call: Call = {
        kind,
        body,
        exec() {
          if (executed) return
          executed = true
          try {
            result = run()
          } catch (error) {
            failure = error
          }
        },
        deliver() {
          call.exec()
          if (failure !== undefined) reject(failure)
          else resolve(result as T)
        },
        lose() {
          reject(new TypeError('Failed to fetch'))
        },
      }
      calls.push(call)
      if (auto) queueMicrotask(() => call.deliver())
    })
  }
  const transport: CountTransport = {
    found: (_countId, place) => defer('found', place, () => server.found(place)),
    putLines: (_countId, lines, comment) => defer('put', { lines, comment }, () => server.put(lines, comment)),
    get: () => defer('get', null, () => server.doc()),
  }
  return {
    calls,
    transport,
    setAuto(value: boolean) {
      auto = value
      if (value) for (const call of calls) call.deliver()
    },
  }
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

async function setup(lines: Array<[string, number | null]> = [['P', 0], ['Q', 0]]) {
  const server = new FakeServer(lines)
  const net = controlled(server)
  const rejected: Array<{ error: unknown; kind: CountOpKind }> = []
  const notices: string[] = []
  const ops = createCountOps({
    transport: net.transport,
    isRetryable: (error) => !(error instanceof HttpError),
    onRejected: (error, kind) => rejected.push({ error, kind }),
    onScanNotice: (notice) => notices.push(notice),
    delay: () => Promise.resolve(),
  })
  const opened = ops.open('count-1')
  await settle()
  net.calls[0].deliver()
  await opened
  net.calls.length = 0
  let scanNo = 0
  const scan = (lineId?: string, code?: string) => {
    scanNo += 1
    ops.scan({
      barcodes: [code ?? `BC-${lineId}`],
      cellId: 'cell-1',
      containerKind: null,
      containerId: null,
      scanId: `s${scanNo}`,
      ...(lineId ? { lineId } : {}),
    })
  }
  const shown = (id: string) => allProducts(ops.view().count as InventoryCount).find((item) => item.id === id)?.actual
  /** Журнал запросов в человеческом виде: «PUT P=7», «POST s1», «GET». */
  const trace = () => net.calls.map((call) => {
    if (call.kind === 'get') return 'GET'
    if (call.kind === 'found') return `POST ${(call.body as ScanPlace).scanId}`
    const body = call.body as { lines: LineValue[]; comment?: CommentChange }
    const parts = body.lines.map((line) => `${line.lineId}=${line.value}`)
    if (body.comment) parts.push(`comment=${JSON.stringify(body.comment.value)}`)
    return `PUT ${parts.join(',')}`
  })
  /** Дать очереди дойти до следующего запроса и доставить все ответы по порядку. */
  const drain = async () => {
    for (let i = 0; i < 50; i += 1) {
      await settle()
      const open = net.calls.filter((call) => !(call as Call & { done?: boolean }).done)
      if (open.length === 0) break
      for (const call of open) {
        ;(call as Call & { done?: boolean }).done = true
        call.deliver()
      }
    }
    await settle()
  }
  const mark = (call: Call) => {
    ;(call as Call & { done?: boolean }).done = true
    return call
  }
  return { server, net, ops, scan, shown, trace, drain, mark, rejected, notices }
}

describe('WMS-542: единая очередь операций документа', () => {
  it('в полёте всегда одна операция, ответы применяются по порядку', async () => {
    const { net, scan, mark } = await setup()
    scan('P')
    scan('P')
    scan('Q')
    await settle()
    expect(net.calls).toHaveLength(1)
    mark(net.calls[0]).deliver()
    await settle()
    expect(net.calls).toHaveLength(2)
  })

  it('F1-A: ручные 7 и два скана при задержанном PUT — один PUT, итог 9', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    ops.editLine('P', 7)
    scan('P')
    await settle()
    // PUT уже на сервере, ответ задержан. Экран: 7 + 1.
    net.calls[0].exec()
    expect(shown('P')).toBe(8)
    scan('P')
    expect(shown('P')).toBe(9)
    await settle()
    expect(net.calls).toHaveLength(1)
    mark(net.calls[0]).deliver()
    await drain()
    expect(trace()).toEqual(['PUT P=7', 'POST s1', 'POST s2'])
    expect(server.value('P')).toBe(9)
    expect(shown('P')).toBe(9)
  })

  it('F1-B: после 7+скан чужие +2, «Сохранить» не уменьшает — 10 и на сервере, и на экране', async () => {
    const { server, ops, scan, shown, trace, drain } = await setup()
    ops.editLine('P', 7)
    scan('P')
    await drain()
    expect(server.value('P')).toBe(8)
    server.otherScan('P', 2)
    const saved = ops.save()
    await drain()
    await saved
    expect(trace()).toEqual(['PUT P=7', 'POST s1', 'GET'])
    expect(server.value('P')).toBe(10)
    expect(shown('P')).toBe(10)
  })

  it('F1-C: ответ скана потерян, чужие +2, повтор тем же scan_id — PUT не повторяется, итог 10', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    ops.editLine('P', 7)
    scan('P')
    await settle()
    mark(net.calls[0]).deliver()
    await settle()
    const post = mark(net.calls[1])
    post.exec()
    expect(server.value('P')).toBe(8)
    server.otherScan('P', 2)
    post.lose()
    await drain()
    expect(trace()).toEqual(['PUT P=7', 'POST s1', 'POST s1'])
    expect(server.value('P')).toBe(10)
    expect(shown('P')).toBe(10)
    expect(ops.view().pendingScans).toBe(0)
  })

  it('F2: ручная правка другой строки во время скана сохраняется и уходит своим PUT', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    scan('P')
    await settle()
    ops.editLine('Q', 9)
    mark(net.calls[0]).deliver()
    await settle()
    expect(shown('Q')).toBe(9)
    expect(shown('P')).toBe(1)
    const saved = ops.save()
    await drain()
    await saved
    expect(trace()).toEqual(['POST s1', 'PUT Q=9'])
    expect(server.value('Q')).toBe(9)
    expect(shown('Q')).toBe(9)
    expect(server.value('P')).toBe(1)
    expect(shown('P')).toBe(1)
  })

  it('F3, порядок 1: «Сохранить» с правкой другой строки нажато, пока PUT скана без ответа — экран не откатывается', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    ops.editLine('P', 7)
    scan('P')
    await settle()
    net.calls[0].exec()
    ops.editLine('Q', 4)
    const saved = ops.save()
    await settle()
    // «Сохранить» стоит в очереди за сканом и ничего не шлёт мимо неё.
    expect(trace()).toEqual(['PUT P=7'])
    expect(shown('P')).toBe(8)
    mark(net.calls[0]).deliver()
    await drain()
    await saved
    expect(trace()).toEqual(['PUT P=7', 'POST s1', 'PUT Q=4'])
    expect(server.value('P')).toBe(8)
    expect(shown('P')).toBe(8)
    expect(server.value('Q')).toBe(4)
    expect(shown('Q')).toBe(4)
  })

  it('F3, порядок 2: «Сохранить» с правкой нажато, пока POST скана без ответа — итог 8, сохранённое на месте', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    ops.editLine('P', 7)
    scan('P')
    await settle()
    mark(net.calls[0]).deliver()
    await settle()
    net.calls[1].exec()
    ops.editLine('Q', 4)
    const saved = ops.save()
    await settle()
    expect(trace()).toEqual(['PUT P=7', 'POST s1'])
    expect(shown('P')).toBe(8)
    mark(net.calls[1]).deliver()
    await drain()
    await saved
    expect(trace()).toEqual(['PUT P=7', 'POST s1', 'PUT Q=4'])
    expect(server.value('P')).toBe(8)
    expect(shown('P')).toBe(8)
    expect(shown('Q')).toBe(4)
  })

  it('F3 исходный: пустое «Сохранить» во время скана не возвращает 0 поверх подтверждённой 1', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    scan('P')
    await settle()
    const saved = ops.save()
    mark(net.calls[0]).deliver()
    await drain()
    await saved
    expect(trace()).toEqual(['POST s1', 'GET'])
    expect(server.value('P')).toBe(1)
    expect(shown('P')).toBe(1)
  })

  it('F5: «Сохранить» во время скана с ручной правкой не шлёт ту же правку второй раз — скан не стирается', async () => {
    const { server, ops, scan, shown, trace, drain, net } = await setup()
    ops.editLine('P', 7)
    scan('P')
    await settle()
    net.calls[0].exec()
    const saved = ops.save()
    await drain()
    await saved
    expect(trace().filter((line) => line.startsWith('PUT'))).toEqual(['PUT P=7'])
    expect(trace()).toEqual(['PUT P=7', 'POST s1', 'GET'])
    expect(server.value('P')).toBe(8)
    expect(shown('P')).toBe(8)
  })

  it('F6: ручное число во время скана той же строки видно на экране и именно оно сохраняется', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    scan('P')
    await settle()
    ops.editLine('P', 9)
    expect(shown('P')).toBe(9)
    mark(net.calls[0]).deliver()
    await settle()
    // Ответ скана (1) не подменяет введённое человеком число.
    expect(shown('P')).toBe(9)
    const saved = ops.save()
    await drain()
    await saved
    expect(trace()).toEqual(['POST s1', 'PUT P=9'])
    expect(server.value('P')).toBe(9)
    expect(shown('P')).toBe(9)
  })

  it('F7: ответ скана не стирает несохранённый комментарий, «Сохранить» отправляет его текст', async () => {
    const { server, ops, scan, trace, drain, net, mark } = await setup()
    scan('P')
    await settle()
    ops.editComment('new comment')
    mark(net.calls[0]).deliver()
    await settle()
    expect(ops.view().count?.comment).toBe('new comment')
    const saved = ops.save()
    await drain()
    await saved
    expect(trace()).toEqual(['POST s1', 'PUT comment="new comment"'])
    expect((net.calls[1].body as { comment: CommentChange }).comment.expected).toBe('')
    expect(server.comment).toBe('new comment')
    expect(ops.view().count?.comment).toBe('new comment')
  })

  it('F7: комментарий, введённый до скана, тоже не пропадает после ответа скана', async () => {
    const { server, ops, scan, drain } = await setup()
    ops.editComment('до скана')
    scan('P')
    await drain()
    expect(ops.view().count?.comment).toBe('до скана')
    const saved = ops.save()
    await drain()
    await saved
    expect(server.comment).toBe('до скана')
  })

  it('F8: скан кода маркетплейса без строки на экране — экран показывает ответ сервера', async () => {
    const { server, ops, scan, shown, drain } = await setup()
    server.marketplaceCodes.set('ozn123', 'P')
    scan(undefined, 'OZN123')
    await drain()
    expect(server.value('P')).toBe(1)
    expect(shown('P')).toBe(1)
    scan(undefined, 'OZN123')
    await drain()
    expect(server.value('P')).toBe(2)
    expect(shown('P')).toBe(2)
    expect(ops.view().pendingScans).toBe(0)
  })

  it('F8: настоящая находка — новая строка появляется из ответа, оператор видит текст сервера', async () => {
    const { ops, scan, shown, drain, notices } = await setup()
    scan(undefined, 'NEW-CODE')
    await drain()
    expect(shown('N1')).toBe(1)
    expect(notices).toEqual(['По учёту здесь ничего не числится — записали находку.'])
    expect(ops.view().pendingScans).toBe(0)
  })

  it('F9: окончательно отклонённый скан не оставляет вечный +1', async () => {
    const { server, ops, shown, drain, rejected } = await setup()
    // Первый скан отклонён: код не соответствует строке (справочник изменился).
    ops.scan({ barcodes: ['CHANGED'], cellId: 'cell-1', containerKind: null, containerId: null, scanId: 'x1', lineId: 'P' })
    expect(shown('P')).toBe(1)
    ops.scan({ barcodes: ['BC-P'], cellId: 'cell-1', containerKind: null, containerId: null, scanId: 'x2', lineId: 'P' })
    expect(shown('P')).toBe(2)
    await drain()
    expect(rejected.map((item) => [(item.error as Error).message, item.kind])).toEqual([['line_barcode_mismatch', 'scan']])
    expect(server.value('P')).toBe(1)
    expect(shown('P')).toBe(1)
    expect(ops.view().pendingScans).toBe(0)
  })

  it('F9: обрыв связи — скан не выдаётся за сохранённый и не выбрасывается, повторяется до доставки', async () => {
    const { server, ops, scan, shown, net, mark, drain } = await setup()
    scan('P')
    for (let i = 0; i < 6; i += 1) {
      await settle()
      mark(net.calls[net.calls.length - 1]).lose()
    }
    await settle()
    // Шесть обрывов подряд: скан всё ещё в очереди, проведение закрыто.
    expect(ops.view().pendingScans).toBe(1)
    expect(shown('P')).toBe(1)
    expect(server.value('P')).toBe(0)
    await drain()
    expect(server.value('P')).toBe(1)
    expect(shown('P')).toBe(1)
    expect(ops.view().pendingScans).toBe(0)
  })

  it('R5: ручные 7 и скан — 8 на сервере и на экране', async () => {
    const { server, ops, scan, shown, trace, drain } = await setup()
    ops.editLine('P', 7)
    expect(shown('P')).toBe(7)
    scan('P')
    expect(shown('P')).toBe(8)
    await drain()
    expect(trace()).toEqual(['PUT P=7', 'POST s1'])
    expect(server.value('P')).toBe(8)
    expect(shown('P')).toBe(8)
  })

  it('R3: два оператора сканируют одну строку вперемешку — сервер суммирует, «Сохранить» ничего не уменьшает', async () => {
    const server = new FakeServer([['P', 0]])
    const netA = controlled(server)
    const netB = controlled(server)
    netA.setAuto(true)
    netB.setAuto(true)
    const make = (transport: CountTransport) => createCountOps({
      transport,
      isRetryable: (error) => !(error instanceof HttpError),
      delay: () => Promise.resolve(),
    })
    const a = make(netA.transport)
    const b = make(netB.transport)
    await a.open('count-1')
    await b.open('count-1')
    const pick = (ops: typeof a, id: string) => ops.scan({ barcodes: ['BC-P'], cellId: 'cell-1', containerKind: null, containerId: null, scanId: id, lineId: 'P' })
    for (let i = 0; i < 5; i += 1) {
      pick(a, `a${i}`)
      pick(b, `b${i}`)
    }
    await settle()
    await settle()
    expect(server.value('P')).toBe(10)
    await a.save()
    await b.save()
    expect(server.value('P')).toBe(10)
    const actualOf = (ops: typeof a) => allProducts(ops.view().count as InventoryCount)[0].actual
    expect(actualOf(a)).toBe(10)
    expect(actualOf(b)).toBe(10)
  })

  it('обрыв после выполненного PUT: перед повтором документ перечитывается, абсолют второй раз не шлётся', async () => {
    const { server, ops, scan, shown, trace, drain, net, mark } = await setup()
    ops.editLine('P', 7)
    scan('P')
    await settle()
    const put = mark(net.calls[0])
    put.exec()
    put.lose()
    await drain()
    expect(trace()).toEqual(['PUT P=7', 'GET', 'POST s1'])
    expect(server.value('P')).toBe(8)
    expect(shown('P')).toBe(8)
  })

  it('обрыв до выполнения PUT: правка отправляется повторно той же версией', async () => {
    const { server, ops, trace, drain, net, mark } = await setup()
    ops.editLine('P', 7)
    const saved = ops.save()
    await settle()
    mark(net.calls[0]).lose()
    await drain()
    await saved
    expect(trace()).toEqual(['PUT P=7', 'GET', 'PUT P=7'])
    expect(server.value('P')).toBe(7)
  })

  it('обрыв после выполненного сохранения комментария: повтор не упирается в comment_changed', async () => {
    const { server, ops, trace, drain, net, mark } = await setup()
    ops.editComment('пересорт')
    const saved = ops.save()
    await settle()
    const put = mark(net.calls[0])
    put.exec()
    put.lose()
    await drain()
    await saved
    expect(trace()).toEqual(['PUT comment="пересорт"', 'GET'])
    expect(server.comment).toBe('пересорт')
    expect(ops.view().count?.comment).toBe('пересорт')
  })

  it('«Сохранить» без правок подтягивает чужие изменения строк (сервер 11 — экран 11)', async () => {
    const { server, ops, shown, drain } = await setup([['P', 9]])
    server.otherScan('P', 2)
    expect(shown('P')).toBe(9)
    const saved = ops.save()
    await drain()
    await saved
    expect(shown('P')).toBe(11)
  })

  it('ответ любой операции обновляет чужие строки, но не строки с ожидающими локальными операциями', async () => {
    const { server, ops, scan, shown, drain, net, mark } = await setup()
    ops.editLine('Q', 4)
    server.otherScan('Q', 3)
    server.otherScan('P', 2)
    scan('P')
    await settle()
    mark(net.calls[0]).deliver()
    await settle()
    expect(shown('P')).toBe(3)
    // Черновик Q остаётся тем, что ввёл человек.
    expect(shown('Q')).toBe(4)
    await drain()
  })

  it('отказ сервера в сохранении ручного числа возвращает его в несохранённые, а не стирает с экрана', async () => {
    const { server, ops, shown, drain } = await setup()
    server.lines = server.lines.filter((line) => line.id !== 'Q')
    ops.editLine('Q', 4)
    const saved = ops.save()
    saved.catch(() => undefined)
    await drain()
    await expect(saved).rejects.toThrow('line_not_found')
    // Правка снова несохранённая — число на экране то, что ввёл человек.
    expect(shown('Q')).toBe(4)
    expect(shown('P')).toBe(0)
  })

  it('отказ comment_changed оставляет текст оператора на экране', async () => {
    const { server, ops, drain } = await setup()
    ops.editComment('мой текст')
    server.comment = 'чужой текст'
    const saved = ops.save()
    saved.catch(() => undefined)
    await drain()
    await expect(saved).rejects.toThrow('comment_changed')
    expect(ops.view().count?.comment).toBe('мой текст')
  })

  it('прочие действия идут в той же очереди: после сканов, с перечитанным документом в ответе', async () => {
    const { server, ops, scan, shown, drain } = await setup()
    scan('P')
    const order: string[] = []
    const done = ops.action(async () => {
      order.push(`action sees P=${server.value('P')}`)
      return { count: server.doc(), result: 'ok' }
    })
    await drain()
    await expect(done).resolves.toBe('ok')
    expect(order).toEqual(['action sees P=1'])
    expect(shown('P')).toBe(1)
  })

  it('действие не повторяется при обрыве — вторая тара не создаётся', async () => {
    const { ops, drain } = await setup()
    let calls = 0
    const done = ops.action(async () => {
      calls += 1
      throw new TypeError('Failed to fetch')
    })
    done.catch(() => undefined)
    await drain()
    await expect(done).rejects.toThrow('Failed to fetch')
    expect(calls).toBe(1)
  })
})

describe('WMS-542: уход в другой документ', () => {
  it('скан закрытого документа откладывается, не уходит в чужой и доезжает при возвращении, по порядку', async () => {
    const { server, ops, scan, trace, net, mark } = await setup()
    scan('P')
    scan('Q')
    // Первый скан ушёл, но ответа нет; оператор уходит в список.
    await settle()
    ops.close()
    mark(net.calls[0]).lose()
    await settle()
    await settle()
    expect(ops.parked()).toBe(2)
    expect(trace()).toEqual(['POST s1'])
    // Возвращается в свой документ: отложенное — раньше перечитывания.
    const opened = ops.open('count-1')
    for (let i = 0; i < 10; i += 1) {
      await settle()
      for (const call of net.calls) {
        const flagged = call as Call & { done?: boolean }
        if (!flagged.done) {
          flagged.done = true
          call.deliver()
        }
      }
    }
    await opened
    expect(trace()).toEqual(['POST s1', 'POST s1', 'POST s2', 'GET'])
    expect(ops.parked()).toBe(0)
    expect(server.value('P')).toBe(1)
    expect(server.value('Q')).toBe(1)
    expect(allProducts(ops.view().count as InventoryCount).map((item) => item.actual)).toEqual([1, 1])
  })

  it('«Сохранить» документа, из которого ушли, не висит: отвечает отложением, правка уходит при возвращении', async () => {
    const { server, ops, net, mark, trace, drain } = await setup()
    ops.editLine('P', 3)
    const saved = ops.save()
    saved.catch(() => undefined)
    await settle()
    ops.close()
    mark(net.calls[0]).lose()
    await expect(saved).rejects.toThrow('Документ закрыт')
    expect(ops.parked()).toBe(1)
    const opened = ops.open('count-1')
    await drain()
    await opened
    expect(trace()).toEqual(['PUT P=3', 'GET', 'PUT P=3', 'GET'])
    expect(server.value('P')).toBe(3)
  })
})
