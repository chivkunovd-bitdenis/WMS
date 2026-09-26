import { describe, expect, it } from 'vitest'
import { allProducts, setActual } from './InventoryRows'
import {
  applyLocalScanBump,
  applyScanResponse,
  applySaveResponse,
  confirmManualFlush,
  findScannedLineId,
  initSyncState,
  planScanFlush,
  recordManualEdit,
  type ScanSyncState,
} from './scanReconciliation'
import type { InventoryCount, ProductNode } from './InventoryTypes'

// Ревью Astra №1, docs/reviews/artifacts/wms-542/review-astra-1.md: F1 (блокер),
// F2, F3 воспроизведены как последовательности сетевых ответов с задержкой в
// обоих порядках — те же самые пять расписаний, только против чистого модуля
// scanReconciliation.ts вместо целого React-экрана (быстрее и не размывается
// заглушками сети). Имена тестов и комментарии внутри повторяют шаги из
// ревью, чтобы можно было свериться построчно.

function product(id: string, expected: number): ProductNode {
  return {
    kind: 'product',
    id,
    name: `Товар ${id}`,
    sku: `SKU-${id}`,
    seller: 'Селлер',
    category: '—',
    barcode: `BC-${id}`,
    wbVendorCode: null,
    wbBarcode: `BC-${id}`,
    wbSize: null,
    photoUrl: null,
    expected,
    actual: null,
  }
}

function baseCount(): InventoryCount {
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
    comment: '',
    addressStorage: true,
    cells: [
      {
        id: 'cell-1',
        label: 'A-1',
        barcode: null,
        children: [product('P', 5), product('Q', 3)],
      },
    ],
    scannableCells: [],
    scannableContainers: [],
  }
}

/**
 * Модель сервера ровно с той семантикой, что и backend record_found/
 * save_actuals: PUT — абсолютное присваивание, found — идемпотентный +1 по
 * scan_id. Достаточно для проверки последовательностей клиентской сверки;
 * настоящий сервер и его блокировка проверены отдельно на PostgreSQL в
 * backend/tests/test_wms542_inventory_scan_concurrency.py.
 */
class FakeServer {
  private readonly lines = new Map<string, number | null>()
  private readonly scans = new Set<string>()

  constructor(base: InventoryCount) {
    for (const item of allProducts(base)) this.lines.set(item.id, item.actual)
  }

  get(id: string): number | null {
    return this.lines.get(id) ?? null
  }

  put(id: string, value: number | null): void {
    this.lines.set(id, value)
  }

  found(id: string, scanId: string): void {
    if (this.scans.has(scanId)) return
    this.scans.add(scanId)
    this.lines.set(id, (this.lines.get(id) ?? 0) + 1)
  }

  /** Полный документ, каким его сейчас видит сервер — ответ на любой запрос. */
  snapshot(shape: InventoryCount): InventoryCount {
    let next = shape
    for (const [id, value] of this.lines) next = setActual(next, id, value)
    return next
  }
}

function actual(state: ScanSyncState, id: string): number | null {
  return allProducts(state.count).find((item) => item.id === id)?.actual ?? null
}

/** Снимок manual-версий на момент отправки «Сохранить» — то, что реально уходит в PUT. */
function manualVersions(state: ScanSyncState): Map<string, number> {
  return new Map([...state.manual].map(([id, edit]) => [id, edit.version]))
}

describe('R5 — контрольный случай из постановки: ручная правка + один скан', () => {
  it('7, потом скан — 8, и этот же PUT/POST больше не повторяется', () => {
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    state = recordManualEdit(state, 'P', 7)
    expect(actual(state, 'P')).toBe(7)

    state = applyLocalScanBump(state, 'P')
    expect(actual(state, 'P')).toBe(8)

    const flush = planScanFlush(state, 'P')
    expect(flush).toEqual({ value: 7, version: 1 })
    server.put('P', flush!.value)
    state = confirmManualFlush(state, 'P', flush!.version, server.snapshot(state.count))
    expect(actual(state, 'P')).toBe(8)
    // Повторный запрос плана (как будто скан переигрывают после сетевого
    // обрыва) больше не видит правку — второй PUT не отправится.
    expect(planScanFlush(state, 'P')).toBeNull()

    server.found('P', 'scan-1')
    state = applyScanResponse(state, 'P', server.snapshot(state.count))
    expect(server.get('P')).toBe(8)
    expect(actual(state, 'P')).toBe(8)
  })
})

describe('F1-A — лишняя штука, один оператор', () => {
  it('ручная правка 7 и два быстрых скана дают 9 на сервере и экране, не 10', () => {
    // Дословно шаги из ревью: 1) ввести 7; 2) первый скан, задержать ответ
    // предварительного PUT — на сервере 7, на экране уже 8; 3) до ответа —
    // второй скан, на экране 9, он ждёт очереди; 4) отпустить ответ.
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    state = recordManualEdit(state, 'P', 7)

    state = applyLocalScanBump(state, 'P') // скан 1 — мгновенная подсказка
    expect(actual(state, 'P')).toBe(8)
    const flush1 = planScanFlush(state, 'P')! // очередь берёт план ДО ответа

    state = applyLocalScanBump(state, 'P') // скан 2, пока PUT скана 1 ещё летит
    expect(actual(state, 'P')).toBe(9) // «На экране 9» — совпадает с ревью

    // Второй скан очередь ещё не начала обрабатывать (строго по одному) —
    // его собственный planScanFlush мы не спрашиваем, пока не завершится
    // весь цикл первого (PUT + POST).

    server.put('P', flush1.value) // отпустили ответ PUT: сервер 7
    state = confirmManualFlush(state, 'P', flush1.version, server.snapshot(state.count))
    expect(actual(state, 'P')).toBe(9) // база сервера 7 + два ещё непогашенных скана

    server.found('P', 'scan-1')
    state = applyScanResponse(state, 'P', server.snapshot(state.count))
    expect(server.get('P')).toBe(8)
    expect(actual(state, 'P')).toBe(9) // 8 + один оставшийся непогашенный скан

    // Очередь дошла до скана 2: правки уже нет — прямо в POST, без PUT.
    expect(planScanFlush(state, 'P')).toBeNull()
    server.found('P', 'scan-2')
    state = applyScanResponse(state, 'P', server.snapshot(state.count))

    expect(server.get('P')).toBe(9) // ожидание ревью: «9 на сервере и экране»
    expect(actual(state, 'P')).toBe(9)
  })
})

describe('F1-B — «Сохранить» не уменьшает число, посчитанное сканами', () => {
  it('пустой payload «Сохранить» не отправляет число скана и не стирает чужие сканы', () => {
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    state = recordManualEdit(state, 'P', 7)
    state = applyLocalScanBump(state, 'P')
    const flush = planScanFlush(state, 'P')!
    server.put('P', flush.value)
    state = confirmManualFlush(state, 'P', flush.version, server.snapshot(state.count))
    server.found('P', 'scan-1')
    state = applyScanResponse(state, 'P', server.snapshot(state.count))
    expect(server.get('P')).toBe(8)
    expect(actual(state, 'P')).toBe(8)

    // Второй оператор делает два скана этой же строки независимо от нас.
    server.found('P', 'other-scan-1')
    server.found('P', 'other-scan-2')
    expect(server.get('P')).toBe(10)

    // Оператор 1 жмёт «Сохранить». Ручных правок нет (manual пуст после
    // confirmManualFlush) — скан НИКОГДА не попадает в payload, значит и
    // отправлять для P нечего.
    const sentVersions = manualVersions(state)
    expect(sentVersions.size).toBe(0)
    state = applySaveResponse(state, sentVersions, server.snapshot(state.count))

    // Ключевая проверка ревью: сервер не пострадал, оба чужих скана целы.
    expect(server.get('P')).toBe(10)
    // Пустой скоп такого PUT не авторитетен для P — экран может на секунду
    // отстать от только что прилетевших чужих сканов (подтянет их следующим
    // своим сканом этой строки или перезагрузкой), но это не потеря данных:
    // сервер он точно не откатывает, в отличие от прежнего поведения.
    expect(actual(state, 'P')).toBe(8)
  })
})

describe('F1-C — повтор скана после потери ответа не переигрывает подтверждённый PUT', () => {
  it('после подтверждённого PUT повторный POST идёт один, чужие сканы не стираются', () => {
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    state = recordManualEdit(state, 'P', 7)
    state = applyLocalScanBump(state, 'P')
    const flush = planScanFlush(state, 'P')!
    server.put('P', flush.value) // сервер: 7, PUT подтверждён
    state = confirmManualFlush(state, 'P', flush.version, server.snapshot(state.count))
    // Состояние шага теперь в самой manual-карте: правки для P больше нет.
    expect(planScanFlush(state, 'P')).toBeNull()

    // POST реально прошёл на сервере, но его ОТВЕТ потерян по сети — клиент
    // ничего не применил и готовится повторить тот же scan_id.
    server.found('P', 'scan-1')
    expect(server.get('P')).toBe(8)

    // Пока клиент не повторил, другой оператор успевает сделать +2.
    server.found('P', 'other-1')
    server.found('P', 'other-2')
    expect(server.get('P')).toBe(10)

    // Повтор скана: PUT не переигрывается (плана нет), уходит только POST с
    // тем же scan_id — сервер идемпотентно не прибавляет вторую штуку.
    expect(planScanFlush(state, 'P')).toBeNull()
    server.found('P', 'scan-1')
    state = applyScanResponse(state, 'P', server.snapshot(state.count))

    expect(server.get('P')).toBe(10) // оба чужих скана целы
    expect(actual(state, 'P')).toBe(10)
  })
})

describe('F2 — ручная правка другой строки во время PUT скана', () => {
  it('Q, введённая пока летит запрос по P, не теряется и уходит на «Сохранить»', () => {
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    // Скан P без ручной правки — сразу POST, PUT вообще не нужен.
    state = applyLocalScanBump(state, 'P')
    expect(planScanFlush(state, 'P')).toBeNull()

    // Пока «летит» запрос по P, оператор руками вводит Q = 9.
    state = recordManualEdit(state, 'Q', 9)
    expect(actual(state, 'Q')).toBe(9)

    server.found('P', 'scan-1')
    state = applyScanResponse(state, 'P', server.snapshot(state.count))
    // Ответ по P не имеет отношения к Q — правка на месте.
    expect(actual(state, 'Q')).toBe(9)
    expect(state.manual.has('Q')).toBe(true)

    const sentVersions = manualVersions(state)
    expect(sentVersions.has('Q')).toBe(true)
    server.put('Q', state.manual.get('Q')!.value)
    state = applySaveResponse(state, sentVersions, server.snapshot(state.count))

    expect(server.get('Q')).toBe(9)
    expect(actual(state, 'Q')).toBe(9)
    expect(state.manual.has('Q')).toBe(false)
  })
})

describe('F3 — запоздалый ответ «Сохранить» не откатывает подтверждённый скан', () => {
  it('P=0, скан даёт 1, устаревший пустой ответ «Сохранить» доставлен позже — экран остаётся на 1', () => {
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    // Скан P — мгновенно 1 на экране, запрос ещё не подтверждён.
    state = applyLocalScanBump(state, 'P')
    expect(actual(state, 'P')).toBe(1)

    // «Сохранить» отправлен без ручных правок (payload пуст) — сервер успел
    // прочитать документ ДО того, как скан коммитнулся, и вернуть P=0. Этот
    // ответ мы придерживаем («доставить позже») — ниже применяем его
    // ПОСЛЕДНИМ, хотя запрос ушёл раньше.
    const savePayload = manualVersions(state)
    expect(savePayload.size).toBe(0)
    const staleSaveSnapshot = server.snapshot(state.count) // сервер ещё не знает о скане

    // Скан коммитится и подтверждается первым.
    server.found('P', 'scan-1')
    state = applyScanResponse(state, 'P', server.snapshot(state.count))
    expect(actual(state, 'P')).toBe(1)
    expect(server.get('P')).toBe(1)

    // Теперь доставляем устаревший ответ «Сохранить».
    state = applySaveResponse(state, savePayload, staleSaveSnapshot)

    // Ожидание ревью: экран сохраняет подтверждённую 1, а не откатывается к 0.
    expect(actual(state, 'P')).toBe(1)
    expect(server.get('P')).toBe(1)
  })

  it('тот же сценарий, но ответы доставлены в обратном порядке — тоже 1', () => {
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    state = applyLocalScanBump(state, 'P')
    const savePayload = manualVersions(state)
    const staleSaveSnapshot = server.snapshot(state.count)

    server.found('P', 'scan-1')
    const scanSnapshot = server.snapshot(state.count)

    // На этот раз ответ «Сохранить» применяется ПЕРВЫМ (не запаздывает) —
    // пустой скоп всё равно ничего не трогает, порядок не имеет значения.
    state = applySaveResponse(state, savePayload, staleSaveSnapshot)
    expect(actual(state, 'P')).toBe(1)

    state = applyScanResponse(state, 'P', scanSnapshot)
    expect(actual(state, 'P')).toBe(1)
    expect(server.get('P')).toBe(1)
  })
})

describe('R3 — двое операторов сканируют одну строку одновременно', () => {
  it('оба скана учтены, ни один не потерян', () => {
    const server = new FakeServer(baseCount())
    let state = initSyncState(baseCount())

    state = applyLocalScanBump(state, 'P') // оператор 1
    server.found('P', 'operator-1-scan')
    // Оператор 2 сканирует ту же строку в своей вкладке независимо от нас —
    // на сервере это уже отдельный, параллельный запрос.
    server.found('P', 'operator-2-scan')
    expect(server.get('P')).toBe(2)

    state = applyScanResponse(state, 'P', server.snapshot(state.count))
    expect(actual(state, 'P')).toBe(2)
  })
})

describe('findScannedLineId — настоящая находка без заранее известного id', () => {
  it('находит товар внутри указанной тары по штрихкоду', () => {
    const withBox: InventoryCount = {
      ...baseCount(),
      cells: [
        {
          id: 'cell-1',
          label: 'A-1',
          barcode: null,
          children: [
            {
              kind: 'box',
              id: 'box-1',
              code: 'K-1',
              barcode: null,
              children: [product('surprise', 0)],
            },
          ],
        },
      ],
    }
    const id = findScannedLineId(
      withBox,
      { cellId: null, containerKind: 'box', containerId: 'box-1' },
      ['BC-surprise'],
    )
    expect(id).toBe('surprise')
  })

  it('находит товар россыпью в указанной ячейке', () => {
    const id = findScannedLineId(baseCount(), { cellId: 'cell-1', containerKind: null, containerId: null }, ['BC-Q'])
    expect(id).toBe('Q')
  })

  it('ничего не находит вне указанного места, даже если код есть в документе', () => {
    const id = findScannedLineId(
      baseCount(),
      { cellId: 'unassigned', containerKind: null, containerId: null },
      ['BC-P'],
    )
    expect(id).toBeUndefined()
  })
})
