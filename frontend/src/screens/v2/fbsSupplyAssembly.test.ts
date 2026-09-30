import { describe, expect, it } from 'vitest'
import type { FbsWorklistOrder, FbsWorkspace } from './fbsApi'
import { fbsBuildPickingRows } from './fbsUx'
import {
  fbsAssemblyPickingRows,
  fbsAssemblyReadiness,
  fbsAssemblySupplyTitle,
  fbsCodeBelongsToSupply,
  fbsSelectionNeedsGroupCreate,
  groupFbsOrdersForSupplies,
  parseFbsAssemblySupplyIds,
  pickScanCandidates,
  pickScanTargets,
  planGroupPickSet,
  readFbsAssemblyStage,
  runFbsSupplyGroupCreation,
  saveFbsAssemblyStage,
  type FbsGroupCreateResult,
  type GroupPickSupplyState,
} from './fbsSupplyAssembly'

type OrderInput = {
  id: string
  seller?: string
  wbWarehouse?: number
  wms?: string
  buyer?: 'individual' | 'legal'
  cargo?: string
  marketplace?: 'wb' | 'ozon'
}

function order(input: OrderInput): FbsWorklistOrder {
  const seller = input.seller ?? 'Горячкина'
  const wbWarehouse = input.wbWarehouse ?? 507
  return {
    id: input.id,
    marketplace: input.marketplace ?? 'wb',
    seller: { id: `seller-${seller}`, name: `ИП ${seller}` },
    wb_warehouse: { id: wbWarehouse, name: `Склад ${wbWarehouse}` },
    wms_warehouse: { id: input.wms ?? 'wms-1', name: input.wms ?? 'Основной' },
    buyer_type: input.buyer ?? 'individual',
    cargo_type: input.cargo ?? 'mgt',
  } as unknown as FbsWorklistOrder
}

const storageFixture = () => {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
  }
}

describe('WMS-574 Д1: деление выбора на поставки', () => {
  it('делит 10 заказов 2 селлеров и 2 складов WB, у одного склада два грузовых типа', () => {
    const orders = [
      order({ id: 'a1', seller: 'Горячкина', wbWarehouse: 507 }),
      order({ id: 'a2', seller: 'Горячкина', wbWarehouse: 507, cargo: 'sgt' }),
      order({ id: 'a3', seller: 'Горячкина', wbWarehouse: 686 }),
      order({ id: 'b1', seller: 'Смирнов', wbWarehouse: 507 }),
      order({ id: 'b2', seller: 'Смирнов', wbWarehouse: 686 }),
      order({ id: 'a4', seller: 'Горячкина', wbWarehouse: 507 }),
      order({ id: 'a5', seller: 'Горячкина', wbWarehouse: 686 }),
      order({ id: 'b3', seller: 'Смирнов', wbWarehouse: 507 }),
      order({ id: 'b4', seller: 'Смирнов', wbWarehouse: 686 }),
      order({ id: 'a6', seller: 'Горячкина', wbWarehouse: 507, cargo: 'sgt' }),
    ]
    const groups = groupFbsOrdersForSupplies(orders)
    expect(groups).toHaveLength(5)
    expect(groups.reduce((sum, group) => sum + group.orderIds.length, 0)).toBe(10)
    expect(groups.map((group) => [group.sellerName, group.wbWarehouseName, group.cargoType, group.orderIds])).toEqual([
      ['ИП Горячкина', 'Склад 507', 'mgt', ['a1', 'a4']],
      ['ИП Горячкина', 'Склад 507', 'sgt', ['a2', 'a6']],
      ['ИП Горячкина', 'Склад 686', 'mgt', ['a3', 'a5']],
      ['ИП Смирнов', 'Склад 507', 'mgt', ['b1', 'b3']],
      ['ИП Смирнов', 'Склад 686', 'mgt', ['b2', 'b4']],
    ])
  })

  it('разделяет по складу WMS и типу покупателя — тем же признакам, по которым отказывает сервер', () => {
    const groups = groupFbsOrdersForSupplies([
      order({ id: '1' }),
      order({ id: '2', wms: 'wms-2' }),
      order({ id: '3', buyer: 'legal' }),
      order({ id: '4' }),
    ])
    expect(groups).toHaveLength(3)
    expect(groups.flatMap((group) => group.orderIds).sort()).toEqual(['1', '2', '3', '4'])
  })

  it('Д2: новое окно только для WB, который делится на 2+ поставки', () => {
    expect(fbsSelectionNeedsGroupCreate([order({ id: '1' }), order({ id: '2' }), order({ id: '3' })])).toBe(false)
    expect(fbsSelectionNeedsGroupCreate([order({ id: '1' })])).toBe(false)
    expect(fbsSelectionNeedsGroupCreate([order({ id: '1' }), order({ id: '2', seller: 'Смирнов' })])).toBe(true)
    expect(fbsSelectionNeedsGroupCreate([
      order({ id: '1', marketplace: 'ozon' }),
      order({ id: '2', marketplace: 'ozon', seller: 'Смирнов' }),
    ])).toBe(false)
    expect(fbsSelectionNeedsGroupCreate([order({ id: '1' }), order({ id: '2', marketplace: 'ozon' })])).toBe(false)
  })
})

describe('WMS-574 Д5: раздача общего подбора по поставкам', () => {
  const states = (...rows: Array<[number, number, number]>): GroupPickSupplyState[] =>
    rows.map(([planned, pickedTotal, pickedHere], index) => ({ index, planned, pickedTotal, pickedHere }))

  it('скан уходит первой поставке, которой товар ещё нужен', () => {
    expect(pickScanTargets(states([2, 0, 0], [1, 0, 0]))).toEqual([0, 1])
    expect(pickScanTargets(states([2, 2, 2], [1, 0, 0]))).toEqual([1])
  })

  it('если товар не нужен никому — первая поставка с ним, чтобы сервер ответил прежним отказом', () => {
    expect(pickScanTargets(states([2, 2, 2], [1, 1, 1]))).toEqual([0])
    expect(pickScanTargets([])).toEqual([])
  })

  it('C8: число 3 раздаётся по порядку, уменьшение до 1 снимает сначала со второй поставки', () => {
    const up = planGroupPickSet(states([2, 0, 0], [1, 0, 0]), 3, [])
    expect(up.changes).toEqual([{ index: 0, quantity: 2 }, { index: 1, quantity: 1 }])
    const down = planGroupPickSet(states([2, 2, 2], [1, 1, 1]), 1, up.log)
    expect(down.changes).toEqual([{ index: 1, quantity: 0 }, { index: 0, quantity: 1 }])
    expect(down.log).toEqual([{ index: 0, qty: 1 }])
  })

  it('отмена последнего снятия возвращает штуку той поставке, которой она досталась', () => {
    // Вторая поставка подобрана раньше (в своей карточке), первой сейчас досталась одна штука сканом.
    const log = [{ index: 0, qty: 1 }]
    const undo = planGroupPickSet(states([2, 1, 1], [1, 1, 1]), 1, log)
    expect(undo.changes).toEqual([{ index: 0, quantity: 0 }])
    expect(undo.log).toEqual([])
  })

  it('без истории уменьшение идёт с поставок в обратном порядке', () => {
    const down = planGroupPickSet(states([2, 2, 2], [1, 1, 1]), 2, [])
    expect(down.changes).toEqual([{ index: 1, quantity: 0 }])
  })

  it('больше, чем ждут заказы группы, — остаток уходит последней поставке, сервер ответит прежним отказом', () => {
    const plan = planGroupPickSet(states([1, 0, 0], [1, 0, 0]), 3, [])
    expect(plan.changes).toEqual([{ index: 0, quantity: 1 }, { index: 1, quantity: 2 }])
  })

  it('то же число — запросов нет', () => {
    expect(planGroupPickSet(states([2, 1, 1]), 1, []).changes).toEqual([])
  })
})

describe('WMS-574 R3/R4: создание поставок групп без дубля', () => {
  const groups = ['A', 'B', 'C'].map((key) => ({
    key,
    sellerName: key,
    wbWarehouseName: 'Коледино',
    cargoType: 'mgt',
    orderIds: [`${key}-1`],
  }))

  class ApiError extends Error {
    readonly code: string
    readonly retryable: boolean
    readonly context: unknown

    constructor(message: string, code: string, retryable: boolean, context: unknown = null) {
      super(message)
      this.code = code
      this.retryable = retryable
      this.context = context
    }
  }

  const workspaceFor = (key: string) => ({
    supply: { id: `supply-${key}`, name: 'FBS 29.09.2026', wb_supply_id: `WB-GI-${key}` },
  }) as unknown as FbsWorkspace

  it('WMS-588: после частичного успеха создаёт задание только из созданных в этой попытке поставок', async () => {
    const createdBatches: Array<Array<{ groupKey: string; supplyId: string }>> = []
    const result = await runFbsSupplyGroupCreation(
      groups,
      new Map(),
      new Map(),
      async (group) => {
        if (group.key === 'B') throw new TypeError('Failed to fetch')
        return workspaceFor(group.key)
      },
      {
        newKey: () => 'supply-key',
        isApiError: () => false,
        afterCreated: async (created) => { createdBatches.push(created) },
      },
    )

    expect(createdBatches).toEqual([[
      { groupKey: 'A', supplyId: 'supply-A' },
      { groupKey: 'C', supplyId: 'supply-C' },
    ]])
    expect(result.get('B')).toEqual({ status: 'failed', message: 'Failed to fetch' })
  })

  it('после сбоя повтор отправляет только несозданные группы с прежними ключами', async () => {
    let counter = 0
    const newKey = () => `key-${++counter}`
    const keys = new Map<string, string>()
    const calls: Array<[string, string]> = []
    const failures: Record<string, unknown> = {
      B: new TypeError('Failed to fetch'),
      C: new ApiError('WB не подтвердил состав поставки — повторите операцию.', 'wb_timeout', true, { wb_supply_id: 'WB-GI-C' }),
    }
    const create = async (group: { key: string }, idempotencyKey: string) => {
      calls.push([group.key, idempotencyKey])
      const failure = failures[group.key]
      if (failure) throw failure
      return workspaceFor(group.key)
    }
    const options = { newKey, isApiError: (cause: unknown) => cause instanceof ApiError }

    const first = await runFbsSupplyGroupCreation(groups, new Map(), keys, create, options)
    expect(first.get('A')).toEqual({ status: 'created', supplyId: 'supply-A', name: 'FBS 29.09.2026', wbSupplyId: 'WB-GI-A' })
    expect(first.get('B')).toEqual({ status: 'failed', message: 'Failed to fetch' })
    expect(first.get('C')).toEqual({
      status: 'pending',
      message: 'WB не подтвердил состав поставки — повторите операцию. WB: WB-GI-C. Повторите проверку, чтобы прочитать фактический состав WB.',
    })

    failures.B = undefined
    failures.C = undefined
    const second = await runFbsSupplyGroupCreation(groups, first, keys, create, options)
    expect([...second.values()].every((result: FbsGroupCreateResult) => result.status === 'created')).toBe(true)
    expect(calls).toEqual([
      ['A', 'key-1'], ['B', 'key-2'], ['C', 'key-3'],
      ['B', 'key-2'], ['C', 'key-3'],
    ])
  })

  it('окончательный отказ сервера меняет ключ группы, как в окне одной поставки', async () => {
    let counter = 0
    const keys = new Map<string, string>()
    const used: string[] = []
    let fail = true
    const create = async (_group: { key: string }, idempotencyKey: string) => {
      used.push(idempotencyKey)
      if (fail) throw new ApiError('Заказ нельзя добавить в выбранную поставку.', 'order_incompatible', false)
      return workspaceFor('A')
    }
    const options = { newKey: () => `key-${++counter}`, isApiError: (cause: unknown) => cause instanceof ApiError }
    const first = await runFbsSupplyGroupCreation([groups[0]], new Map(), keys, create, options)
    expect(first.get('A')).toEqual({ status: 'failed', message: 'Заказ нельзя добавить в выбранную поставку.' })
    fail = false
    await runFbsSupplyGroupCreation([groups[0]], first, keys, create, options)
    expect(used).toEqual(['key-1', 'key-2'])
  })
})

describe('WMS-574 окно сборки', () => {
  const workspace = (id: string, marketplace: 'wb' | 'ozon', progress: FbsWorkspace['progress'], orders: unknown[] = []) => ({
    supply: {
      id,
      marketplace,
      name: 'FBS 29.09.2026',
      wb_supply_id: `WB-GI-${id}`,
      seller: { id: 's', name: 'ИП Горячкина' },
      wb_warehouse: { id: 507, name: 'Коледино' },
    },
    progress,
    orders,
  }) as unknown as FbsWorkspace

  it('R5: шапка — сумма тех же чисел, что шапка карточки каждой поставки', () => {
    const progress = { picked: 1, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 4 }
    expect(fbsAssemblyReadiness([workspace('a', 'wb', progress), workspace('b', 'wb', { ...progress, total: 6 })]))
      .toEqual({ ready: 10, total: 10 })
    expect(fbsAssemblyReadiness([workspace('c', 'ozon', progress)])).toEqual({ ready: 0, total: 4 })
  })

  it('R7: подзаголовок поставки', () => {
    expect(fbsAssemblySupplyTitle(workspace('a', 'wb', { picked: 0, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 0 })))
      .toBe('Поставка FBS 29.09.2026 · WB № WB-GI-a · ИП Горячкина · Склад WB Коледино')
  })

  it('Д4: supply_ids из адреса и вкладка по группе', () => {
    expect(parseFbsAssemblySupplyIds('a, b,,a,c')).toEqual(['a', 'b', 'c'])
    expect(parseFbsAssemblySupplyIds(null)).toEqual([])
    const storage = storageFixture()
    expect(readFbsAssemblyStage(['a', 'b'], storage)).toBeNull()
    saveFbsAssemblyStage(['a', 'b'], 'picking', storage)
    expect(readFbsAssemblyStage(['a', 'b'], storage)).toBe('picking')
    expect(readFbsAssemblyStage(['a'], storage)).toBeNull()
  })

  it('Д14: строки листа подбора суммируют план товара по всем поставкам группы', () => {
    const line = (id: string, productId: string, picked: boolean, tape: number) => ({
      id,
      wb_order_id: Number(id.replace(/\D/g, '')),
      tape_order_index: tape,
      deadline_at: '2026-09-30T10:00:00Z',
      product: { id: productId, name: `Товар ${productId}`, size: 'M', image_url: null, seller_article: 'ART', wb_article: 1, barcode: '468' },
      metadata: { required: [] },
      pick: { status: picked ? 'picked' : 'pending' },
      sticker: { code: null },
      inventory: { locations: [{ code: 'A-1', available_unpacked: 5 }] },
    })
    const progress = { picked: 0, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 0 }
    const rows = fbsAssemblyPickingRows([
      workspace('a', 'wb', progress, [line('o1', 'x', true, 0), line('o2', 'x', false, 1)]),
      workspace('b', 'wb', progress, [line('o3', 'x', false, 0), line('o4', 'y', false, 1)]),
    ])
    expect(rows.map((row) => [row.key, row.required, row.picked, row.wbOrders])).toEqual([
      ['x', 3, 1, [1, 2, 3]],
      ['y', 1, 0, [4]],
    ])
  })

  it('WMS-580 R5/R6: порядок строк листа группы для одной поставки совпадает с её собственной лентой/листом', () => {
    // Заказы одной поставки не по возрастанию номера WB — только tape_order_index
    // задаёт порядок. fbsAssemblyPickingRows (лист подбора группы, Д14) и
    // fbsBuildPickingRows (лист/лента карточки этой же поставки, FfFbsSupplyWorkspace
    // в режиме рамки сборки — WMS-574 R14/R21) — разные функции, но обязаны
    // выстраивать заказы одной поставки в одном и том же порядке.
    const line = (id: string, productId: string, wbOrderId: number, tape: number) => ({
      id,
      wb_order_id: wbOrderId,
      tape_order_index: tape,
      deadline_at: '2026-09-30T10:00:00Z',
      product: { id: productId, name: `Товар ${productId}`, size: 'M', image_url: null, seller_article: 'ART', wb_article: 1, barcode: '468' },
      positions: [],
      metadata: { required: [] },
      pick: { status: 'pending' },
      sticker: { code: null },
      inventory: { locations: [] },
    })
    const progress = { picked: 0, packed: 0, metadata_ready: 0, stickers_ready: 0, total: 0 }
    const orders = [
      line('o-300', 'x', 300, 2),
      line('o-150', 'y', 150, 3),
      line('o-100', 'x', 100, 0),
      line('o-200', 'x', 200, 1),
    ]
    const groupRows = fbsAssemblyPickingRows([workspace('a', 'wb', progress, orders)])
    const cardRows = fbsBuildPickingRows(orders as unknown as FbsWorkspace['orders'], false).rows
    expect(groupRows.map((row) => [row.key, row.wbOrders])).toEqual(
      cardRows.map((row) => [row.key, row.wbOrders]),
    )
    expect(groupRows.map((row) => [row.key, row.wbOrders])).toEqual([
      ['x', [100, 200, 300]],
      ['y', [150]],
    ])
  })
})

describe('WMS-574 итоговое ревью', () => {
  it('Д5 при одном ШК у товаров разных селлеров: первая поставка, которой нужен именно её товар', () => {
    const candidates = [
      { index: 0, productId: 'p-a', planned: 1, pickedTotal: 1 },
      { index: 1, productId: 'p-b', planned: 1, pickedTotal: 0 },
    ]
    expect(pickScanCandidates(candidates).map((one) => [one.index, one.productId])).toEqual([[1, 'p-b']])
    expect(pickScanCandidates([
      { index: 1, productId: 'p-b', planned: 1, pickedTotal: 1 },
      { index: 0, productId: 'p-a', planned: 1, pickedTotal: 1 },
    ]).map((one) => [one.index, one.productId])).toEqual([[0, 'p-a']])
  })

  it('Д19: ШК товара заказа, ШК привязки и ЧЗ с тем же GTIN относятся к поставке, чужой код — нет', () => {
    const supply = {
      orders: [{
        product: { barcode: '4600000000017', marketplace_bindings: [{ marketplace: 'wb', external_barcodes: ['2040000000011'] }] },
        positions: [{ barcode: '4600000000024', marketplace_bindings: [] }],
      }],
    } as unknown as Pick<FbsWorkspace, 'orders'>
    expect(fbsCodeBelongsToSupply('4600000000017', supply)).toBe(true)
    expect(fbsCodeBelongsToSupply('2040000000011', supply)).toBe(true)
    expect(fbsCodeBelongsToSupply('4600000000024', supply)).toBe(true)
    expect(fbsCodeBelongsToSupply('0104600000000017215AbCdEfGh1234', supply)).toBe(true)
    expect(fbsCodeBelongsToSupply(']d20104600000000017215AbCdEfGh1234', supply)).toBe(true)
    expect(fbsCodeBelongsToSupply('0104600000099999215AbCdEfGh1234', supply)).toBe(false)
    expect(fbsCodeBelongsToSupply('4600000099999', supply)).toBe(false)
    expect(fbsCodeBelongsToSupply('*STICKER', supply)).toBe(false)
  })
})

describe('WMS-604 independent seller creation', () => {
  it('starts different sellers together, keeps one seller sequential and preserves group order', async () => {
    const groups = ['wb|seller-a|1', 'wb|seller-a|2', 'wb|seller-b|1'].map((key) => ({
      key, sellerName: key, wbWarehouseName: 'WB', cargoType: 'mgt', orderIds: [key],
    }))
    const calls: string[] = []
    let releaseA: () => void = () => undefined
    const waitA = new Promise<void>((resolve) => { releaseA = resolve })
    const batches: string[][] = []
    const running = runFbsSupplyGroupCreation(groups, new Map(), new Map(), async (group) => {
      calls.push(group.key)
      if (group.key === groups[0].key) await waitA
      return { supply: { id: group.key, name: group.key, wb_supply_id: group.key } } as unknown as FbsWorkspace
    }, {
      newKey: () => crypto.randomUUID(), isApiError: () => false,
      afterCreated: async (created) => { batches.push(created.map((row) => row.groupKey)) },
    })
    await Promise.resolve()
    expect(calls).toEqual([groups[0].key, groups[2].key])
    releaseA()
    await running
    expect(calls).toEqual([groups[0].key, groups[2].key, groups[1].key])
    expect(batches).toEqual([groups.map((group) => group.key)])
  })
})
