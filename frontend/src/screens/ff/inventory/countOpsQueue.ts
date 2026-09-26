import type { InventoryCount, InventoryNode } from './InventoryTypes'
import { allProducts } from './InventoryRows'

// WMS-542. Единая очередь операций документа инвентаризации.
//
// Почему она одна. Три круга ревью (docs/reviews/artifacts/wms-542/) ловили
// один и тот же класс ошибок: скан (+1, POST /found), ручная правка числа
// (абсолют, PUT /lines) и «Сохранить» уходили на сервер разными независимыми
// путями, обгоняли друг друга, а их ответы применялись к экрану вперемешку.
// Отсюда двойной счёт, стёртые чужие сканы, откат экрана поздним ответом и
// повторная отправка одной и той же ручной правки абсолютным числом поверх
// уже подтверждённого скана.
//
// Здесь это невозможно по построению:
//
//   * Все операции документа — скан, ручное число строки, комментарий,
//     перечитать документ, прочие действия (тара, перенос, «здесь пусто»,
//     проведение) — стоят в ОДНОЙ очереди и уходят строго по одной, FIFO.
//     Мимо очереди на сервер ничего не отправляется.
//   * Ручная правка сначала лежит черновиком (как и раньше: до «Сохранить»
//     она живёт только на экране). В очередь она попадает ровно один раз —
//     при «Сохранить», перед структурным действием или перед сканом этой же
//     строки (тогда сначала «установить N», потом «+1» — итог N+1, R5).
//     Попав в очередь, черновик исчезает, поэтому второй раз ту же правку
//     отправить нечем.
//   * Экран = последний подтверждённый сервером документ (`base`, ответ
//     последней завершённой операции) + поверх него ещё не подтверждённые
//     операции очереди по порядку + черновики. Ответы применяются строго в
//     порядке очереди, в полёте одна операция, поэтому «запоздалых» ответов
//     нет. Отклонённая сервером операция просто уходит из очереди — число
//     возвращается к серверному.
//   * Повтор после обрыва связи повторяет только ту же операцию: скан — тем же
//     scan_id (сервер его узнаёт). Ручное число и комментарий перед повтором
//     сперва перечитывают документ: если сервер уже содержит отправленное,
//     второй раз абсолют не шлём.
//
// Модуль без React: страница подписывается на изменения и рисует `view()`.

/** Скан товара: +1 к строке этого товара в этом месте (POST /found). */
export type ScanPlace = {
  /** Все прочтения кода: как пришло со сканера и как в латинской раскладке. */
  barcodes: string[]
  cellId: string | null
  containerKind: 'pallet' | 'box' | 'cargo_place' | null
  containerId: string | null
  /** Один идентификатор на пик: повтор того же скана не прибавит вторую штуку. */
  scanId: string
  /** Строка, которую экран уже показывает в открытом месте (F4). У находки пусто. */
  lineId?: string
}

/** Ручное число одной строки. */
export type LineValue = { lineId: string; value: number | null }

/** Правка комментария: новый текст и тот, от которого человек начал правку. */
export type CommentChange = { value: string; expected: string }

/** Сетевые вызовы, которыми пользуется очередь. В тестах — управляемая подделка. */
export type CountTransport = {
  found: (countId: string, place: ScanPlace) => Promise<{ count: InventoryCount; notice: string }>
  putLines: (countId: string, lines: LineValue[], comment?: CommentChange) => Promise<InventoryCount>
  get: (countId: string) => Promise<InventoryCount>
}

/**
 * Операция относится к документу, который оператор уже закрыл. Скан, ручное
 * число и комментарий такого документа не теряются: откладываются и уходят,
 * когда оператор вернётся в свой документ (как и раньше в очереди находок).
 * Ожидающему вызову (например, «Сохранить») отвечаем этой ошибкой, чтобы он не
 * висел, пока человек в другом документе.
 */
export class CountOpDeferredError extends Error {}

export type CountOpKind = 'scan' | 'lines' | 'comment' | 'load' | 'action'

type Outcome = { count: InventoryCount | null; notice?: string; result?: unknown }

type Settle = { resolve: (value: unknown) => void; reject: (error: unknown) => void }

type OpBody =
  | { kind: 'scan'; place: ScanPlace }
  | { kind: 'lines'; lines: LineValue[] }
  | { kind: 'comment'; comment: CommentChange }
  | { kind: 'load' }
  | { kind: 'action'; run: () => Promise<{ count: InventoryCount | null; result: unknown }> }

type NewOp = { countId: string } & OpBody

type Op = NewOp & { id: number; sent: boolean; settle?: Settle }

export type CountOpsView = {
  /** Что показать на экране. null — документ ещё не загружен или закрыт. */
  count: InventoryCount | null
  /** Сколько сканов открытого документа ещё не подтверждено сервером. */
  pendingScans: number
}

export type CountOpsDeps = {
  transport: CountTransport
  /** Обрыв связи (в отличие от отказа сервера) — такую операцию повторяем. */
  isRetryable: (error: unknown) => boolean
  /** Экран надо перерисовать. */
  onChange?: (view: CountOpsView) => void
  /** Сервер ответил на скан текстом для оператора (находка). */
  onScanNotice?: (notice: string) => void
  /** Отказ операции, которую никто не ждёт (скан, отложенное сохранение). */
  onRejected?: (error: unknown, kind: CountOpKind) => void
  /** Пауза между попытками; вынесена ради тестов. */
  delay?: (ms: number) => Promise<void>
}

const RETRY_DELAYS_MS = [400, 1200, 3000, 6000]

/**
 * Совпадает ли документ с тем, что отправляла ручная правка. Нужно только
 * перед повтором после потери ответа: если сервер уже содержит отправленное,
 * абсолют второй раз не шлём — иначе он мог бы стереть то, что успели
 * насчитать после него.
 */
function linesApplied(count: InventoryCount, lines: LineValue[]): boolean {
  const actual = new Map(allProducts(count).map((item) => [item.id, item.actual]))
  return lines.every((line) => actual.has(line.lineId) && actual.get(line.lineId) === line.value)
}

/** Сервер обрезает пробелы и хранит пустой комментарий как отсутствие. */
function sameComment(server: string | null | undefined, sent: string): boolean {
  return (server ?? '').trim() === sent.trim()
}

/**
 * Документ с подставленными числами строк и комментарием — за один обход
 * дерева, без копирования нетронутых веток.
 */
export function overlayCount(
  count: InventoryCount,
  values: ReadonlyMap<string, number | null>,
  comment: string,
): InventoryCount {
  let next = count
  if (values.size > 0) {
    const mapNodes = (nodes: InventoryNode[]): InventoryNode[] => {
      let changed = false
      const mapped = nodes.map((node): InventoryNode => {
        if (node.kind === 'product') {
          if (!values.has(node.id)) return node
          const value = values.get(node.id) as number | null
          if (node.actual === value) return node
          changed = true
          return { ...node, actual: value }
        }
        const children = mapNodes(node.children)
        if (children === node.children) return node
        changed = true
        return { ...node, children }
      })
      return changed ? mapped : nodes
    }
    let cellsChanged = false
    const cells = count.cells.map((cell) => {
      const children = mapNodes(cell.children)
      if (children === cell.children) return cell
      cellsChanged = true
      return { ...cell, children }
    })
    if (cellsChanged) next = { ...next, cells }
  }
  if (next.comment !== comment) next = { ...next, comment }
  return next
}

export function createCountOps(deps: CountOpsDeps) {
  const wait = deps.delay ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)))
  let seq = 0
  /** Открытый сейчас документ. */
  let current: string | null = null
  /** Последний подтверждённый сервером документ — ответ последней завершённой операции. */
  let base: InventoryCount | null = null
  /** Ручные числа, ещё не поставленные в очередь (несохранённые правки). */
  let drafts = new Map<string, number | null>()
  /** Несохранённый текст комментария. */
  let commentDraft: CommentChange | null = null
  const queue: Op[] = []
  /** Операции документа, из которого оператор ушёл: ждут его возвращения. */
  let parked: Op[] = []
  let running = false
  let view: CountOpsView = { count: null, pendingScans: 0 }

  function computeView(): CountOpsView {
    const mine = queue.filter((op) => op.countId === current)
    const pendingScans = mine.filter((op) => op.kind === 'scan').length
    if (!base || base.id !== current) return { count: null, pendingScans }
    const values = new Map<string, number | null>()
    let baseValues: Map<string, number | null> | null = null
    let comment = base.comment
    for (const op of mine) {
      if (op.kind === 'lines') {
        for (const line of op.lines) values.set(line.lineId, line.value)
      } else if (op.kind === 'comment') {
        comment = op.comment.value
      } else if (op.kind === 'scan' && op.place.lineId) {
        const id = op.place.lineId
        if (!values.has(id)) {
          baseValues ??= new Map(allProducts(base).map((item) => [item.id, item.actual]))
          values.set(id, baseValues.get(id) ?? null)
        }
        values.set(id, (values.get(id) ?? 0) + 1)
      }
    }
    for (const [id, value] of drafts) values.set(id, value)
    if (commentDraft) comment = commentDraft.value
    return { count: overlayCount(base, values, comment), pendingScans }
  }

  function notify(): void {
    view = computeView()
    deps.onChange?.(view)
  }

  function enqueue(partial: NewOp, awaited: boolean): Promise<unknown> | undefined {
    const op = { ...partial, id: ++seq, sent: false } as Op
    let promise: Promise<unknown> | undefined
    if (awaited) {
      promise = new Promise((resolve, reject) => {
        op.settle = { resolve, reject }
      })
    }
    queue.push(op)
    notify()
    void pump()
    return promise
  }

  /** Операция документа, из которого ушли: скан/правки откладываем, остальное снимаем. */
  function setAside(op: Op): void {
    if (op.kind === 'load') {
      op.settle?.resolve(null)
      return
    }
    if (op.kind === 'action') {
      // Структурное действие (тара, перенос, проведение) без человека в
      // документе не выполняем и не воскрешаем потом.
      op.settle?.reject(new CountOpDeferredError('Документ закрыт до выполнения действия'))
      return
    }
    parked.push(op)
    op.settle?.reject(new CountOpDeferredError('Документ закрыт — отправим, когда он снова откроется'))
    op.settle = undefined
  }

  async function attemptOnce(op: Op): Promise<Outcome> {
    switch (op.kind) {
      case 'scan': {
        op.sent = true
        const found = await deps.transport.found(op.countId, op.place)
        return { count: found.count, notice: found.notice }
      }
      case 'lines': {
        if (op.sent) {
          const fresh = await deps.transport.get(op.countId)
          if (linesApplied(fresh, op.lines)) return { count: fresh }
        }
        op.sent = true
        return { count: await deps.transport.putLines(op.countId, op.lines) }
      }
      case 'comment': {
        if (op.sent) {
          const fresh = await deps.transport.get(op.countId)
          if (sameComment(fresh.comment, op.comment.value)) return { count: fresh }
        }
        op.sent = true
        return { count: await deps.transport.putLines(op.countId, [], op.comment) }
      }
      case 'load':
        return { count: await deps.transport.get(op.countId) }
      case 'action': {
        op.sent = true
        const done = await op.run()
        return { count: done.count, result: done.result }
      }
    }
  }

  async function execute(op: Op): Promise<Outcome> {
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await attemptOnce(op)
      } catch (error) {
        // Действия не идемпотентны (вторая тара, второе проведение) — не
        // повторяем. Отказ сервера повторять бессмысленно.
        if (op.kind === 'action' || !deps.isRetryable(error)) throw error
        // Документ перечитываем ограниченно. Скан, ручное число и комментарий
        // повторяем, пока связь не вернётся: исход неизвестен, и выдать его
        // оператору ни за «сохранено», ни за «не записано» нельзя (F9).
        if (op.kind === 'load' && attempt >= RETRY_DELAYS_MS.length) throw error
        await wait(RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)])
        if (op.countId !== current) throw new CountOpDeferredError('Документ закрыт')
      }
    }
  }

  function applyOutcome(op: Op, outcome: Outcome): void {
    if (op.countId === current && outcome.count && outcome.count.id === current) {
      base = outcome.count
    }
    if (op.kind === 'scan' && outcome.notice && op.countId === current) {
      deps.onScanNotice?.(outcome.notice)
    }
    op.settle?.resolve(op.kind === 'action' ? outcome.result : outcome.count)
  }

  function rejectOp(op: Op, error: unknown): void {
    // Сервер отказал в сохранении правки — она снова несохранённая, как было
    // до нажатия «Сохранить», а не пропадает с экрана.
    if (op.countId === current) {
      if (op.kind === 'lines') {
        for (const line of op.lines) if (!drafts.has(line.lineId)) drafts.set(line.lineId, line.value)
      } else if (op.kind === 'comment' && !commentDraft) {
        commentDraft = { ...op.comment }
      }
    }
    if (op.settle) op.settle.reject(error)
    else deps.onRejected?.(error, op.kind)
  }

  async function pump(): Promise<void> {
    if (running) return
    running = true
    try {
      while (queue.length > 0) {
        const op = queue[0]
        if (op.countId !== current) {
          queue.shift()
          setAside(op)
          notify()
          continue
        }
        let outcome: { ok: true; value: Outcome } | { ok: false; error: unknown }
        try {
          outcome = { ok: true, value: await execute(op) }
        } catch (error) {
          outcome = { ok: false, error }
        }
        queue.shift()
        if (outcome.ok) applyOutcome(op, outcome.value)
        else if (outcome.error instanceof CountOpDeferredError) setAside(op)
        else rejectOp(op, outcome.error)
        notify()
      }
    } finally {
      running = false
    }
  }

  /** Черновики — в очередь. Возвращает обещания поставленных операций. */
  function flushDrafts(): Promise<unknown>[] {
    if (!current) return []
    const promises: Promise<unknown>[] = []
    if (drafts.size > 0) {
      const lines = [...drafts].map(([lineId, value]) => ({ lineId, value }))
      drafts = new Map()
      promises.push(enqueue({ kind: 'lines', countId: current, lines }, true) as Promise<unknown>)
    }
    if (commentDraft) {
      const comment = commentDraft
      commentDraft = null
      promises.push(enqueue({ kind: 'comment', countId: current, comment }, true) as Promise<unknown>)
    }
    return promises
  }

  async function all(promises: Promise<unknown>[]): Promise<void> {
    // Отказ одной не должен оставить вторую необработанной.
    for (const promise of promises) promise.catch(() => undefined)
    await Promise.all(promises)
  }

  function resetDocument(countId: string | null, count: InventoryCount | null): void {
    current = countId
    base = count
    drafts = new Map()
    commentDraft = null
    if (countId) {
      // Отложенные операции этого документа снова в работе — в том же порядке,
      // в каком их сделали, и раньше перечитывания документа.
      const resumed = parked.filter((op) => op.countId === countId)
      parked = parked.filter((op) => op.countId !== countId)
      queue.push(...resumed)
    }
  }

  return {
    view(): CountOpsView {
      return view
    },
    currentId(): string | null {
      return current
    },
    /** Открыть документ: перечитать его с сервера после его же отложенных операций. */
    open(countId: string): Promise<InventoryCount | null> {
      resetDocument(countId, null)
      return enqueue({ kind: 'load', countId }, true) as Promise<InventoryCount | null>
    },
    /** Показать документ, который уже пришёл от сервера (только что создан). */
    show(count: InventoryCount): void {
      resetDocument(count.id, count)
      notify()
      void pump()
    },
    /** Оператор ушёл из документа. Несохранённые черновики пропадают, как и раньше. */
    close(): void {
      resetDocument(null, null)
      notify()
    },
    /**
     * Скан товара. Если у этой строки есть несохранённое ручное число, сначала
     * в очередь встаёт оно («установить N»), потом сам скан (+1): итог N+1.
     */
    scan(place: ScanPlace): void {
      if (!current) return
      if (place.lineId && drafts.has(place.lineId)) {
        const value = drafts.get(place.lineId) as number | null
        drafts = new Map(drafts)
        drafts.delete(place.lineId)
        enqueue({ kind: 'lines', countId: current, lines: [{ lineId: place.lineId, value }] }, false)
      }
      enqueue({ kind: 'scan', countId: current, place }, false)
    },
    /** Человек ввёл число в строке. На экране — сразу, на сервер — при «Сохранить». */
    editLine(lineId: string, value: number | null): void {
      if (!current || !base) return
      drafts = new Map(drafts)
      drafts.set(lineId, value)
      notify()
    },
    /** Человек поправил комментарий. На сервер — при «Сохранить». */
    editComment(value: string): void {
      if (!current || !base) return
      if (commentDraft) {
        commentDraft = { ...commentDraft, value }
      } else {
        // Правку начали от того текста, что сервер отдаст после уже
        // поставленных в очередь правок, — его и ждём на сервере.
        const queued = [...queue].reverse().find((op) => op.countId === current && op.kind === 'comment')
        const expected = queued && queued.kind === 'comment' ? queued.comment.value : base.comment
        commentDraft = { value, expected }
      }
      notify()
    },
    /** Отправить черновики (перед структурным действием) и дождаться их. */
    async flush(): Promise<void> {
      await all(flushDrafts())
    },
    /**
     * «Сохранить»: черновики — в очередь и дождаться всего, что стоит до них.
     * Если отправлять нечего — перечитать документ в той же очереди, чтобы
     * экран подтянул и чужие изменения.
     */
    async save(): Promise<void> {
      if (!current) return
      const promises = flushDrafts()
      if (promises.length === 0) {
        promises.push(enqueue({ kind: 'load', countId: current }, true) as Promise<unknown>)
      }
      await all(promises)
    },
    /**
     * Прочее действие над документом — в той же очереди, после всего, что уже
     * стоит. `run` возвращает новый документ (или null) и результат для вызова.
     */
    action<T>(run: () => Promise<{ count: InventoryCount | null; result: T }>): Promise<T> {
      if (!current) return Promise.reject(new CountOpDeferredError('Документ не открыт'))
      return enqueue({ kind: 'action', countId: current, run }, true) as Promise<T>
    },
    /** Сколько операций ждёт возвращения в свой документ — для тестов и отладки. */
    parked(): number {
      return parked.length
    },
  }
}

export type CountOps = ReturnType<typeof createCountOps>
