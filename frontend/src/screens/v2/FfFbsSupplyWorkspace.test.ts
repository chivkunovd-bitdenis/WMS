import { describe, expect, it } from 'vitest'
import {
  buildFbsPickingListPrintHtml,
  buildFbsSyncTargets,
  fbsAccessibleStageIndex,
  fbsBoxEditingDisabled,
  fbsBoxProductProgress,
  fbsBoxOperationsDisabled,
  fbsDeliveryErrorKeepsIdempotencyKey,
  fbsDeliveryConfirmDisabled,
  fbsOrdersAvailableForBox,
  fbsStageAfterWorkspaceRefresh,
  fbsOrdersSyncErrorMessage,
  mixedMarketplaceSelectionMessage,
  normalizeMetadataKind,
  summarizeDeliveryChecks,
} from './fbsUx'

describe('WMS-557 product quantities beside box input', () => {
  const orders = Array.from({ length: 10 }, (_, index) => ({ id: `order-${index}`, product: { id: 'product-a' } }))
  const firstBox = new Set(orders.slice(0, 5).map((order) => order.id))

  it('keeps plan 10 after five units were saved in another box', () => {
    expect(fbsBoxProductProgress(orders, firstBox, {}).get('product-a')).toEqual({ planned: 10, remaining: 5 })
  })

  it('deducts current input and restores it when input is cleared', () => {
    expect(fbsBoxProductProgress(orders, firstBox, { 'product-a': '2' }).get('product-a')).toEqual({ planned: 10, remaining: 3 })
    expect(fbsBoxProductProgress(orders, firstBox, { 'product-a': '' }).get('product-a')).toEqual({ planned: 10, remaining: 5 })
  })

  it('recomputes after saving and removing assignments without changing plan', () => {
    const twoBoxes = new Set(orders.slice(0, 7).map((order) => order.id))
    expect(fbsBoxProductProgress(orders, twoBoxes, {}).get('product-a')).toEqual({ planned: 10, remaining: 3 })
    twoBoxes.delete('order-0')
    expect(fbsBoxProductProgress(orders, twoBoxes, {}).get('product-a')).toEqual({ planned: 10, remaining: 4 })
  })

  it('counts distinct products and unmapped orders independently', () => {
    const rows = [...orders, { id: 'other', product: { id: 'product-b' } }, { id: 'unmapped', product: { id: null } }]
    const progress = fbsBoxProductProgress(rows, firstBox, { 'product-a': '2', unmapped: '1' })
    expect(progress.get('product-b')).toEqual({ planned: 1, remaining: 1 })
    expect(progress.get('unmapped')).toEqual({ planned: 1, remaining: 0 })
  })

  it('reflects the existing whole-order selection without negative remainder', () => {
    expect(fbsBoxProductProgress(orders, firstBox, { 'product-a': '2.9' }).get('product-a')?.remaining).toBe(3)
    expect(fbsBoxProductProgress(orders, firstBox, { 'product-a': '50' }).get('product-a')?.remaining).toBe(0)
    expect(fbsBoxProductProgress(orders, firstBox, { 'product-a': '-2' }).get('product-a')?.remaining).toBe(5)
  })
})

describe('Ozon FBS UI boundaries', () => {
  it('syncs every seller and marketplace pair from one action', () => {
    expect(buildFbsSyncTargets(['seller-a', 'seller-b'], '__all__')).toEqual([
      { sellerId: 'seller-a', marketplace: 'wb' },
      { sellerId: 'seller-a', marketplace: 'ozon' },
      { sellerId: 'seller-b', marketplace: 'wb' },
      { sellerId: 'seller-b', marketplace: 'ozon' },
    ])
  })

  it('shows missing WB token as an operator action instead of a raw code', () => {
    expect(fbsOrdersSyncErrorMessage(new Error('missing_marketplace_token'))).toBe(
      'У селлера не подключён ключ Wildberries. Добавьте ключ WB в карточке селлера.',
    )
  })

  it('blocks creating and adding a mixed WB/Ozon selection', () => {
    expect(mixedMarketplaceSelectionMessage(['wb', 'ozon'])).toBe(
      'Нельзя объединить заказы Wildberries и Ozon в одну поставку.',
    )
    expect(mixedMarketplaceSelectionMessage(['ozon', 'ozon'])).toBeNull()
  })

  it('allows box operations for both marketplaces', () => {
    expect(fbsBoxOperationsDisabled('ozon')).toBe(false)
    expect(fbsBoxOperationsDisabled('wb')).toBe(false)
  })
})

describe('FBS required identifiers', () => {
  it('TC-FBS-UX-002 sends the API-supported kind when WB calls it KIZ', () => {
    expect(normalizeMetadataKind('KIZ')).toBe('sgtin')
    expect(normalizeMetadataKind('SGTIN')).toBe('sgtin')
    expect(normalizeMetadataKind('UIN')).toBe('uin')
    expect(normalizeMetadataKind(undefined)).toBe('sgtin')
  })
})

describe('WB optional picking', () => {
  it('opens packing immediately after work starts without picked units', () => {
    expect(fbsAccessibleStageIndex({ marketplace: 'wb', currentStage: 'picking' })).toBe(3)
  })

  it('opens every stage for Ozon too — the server does not lock tabs', () => {
    expect(fbsAccessibleStageIndex({ marketplace: 'ozon', currentStage: 'picking' })).toBe(3)
    expect(fbsAccessibleStageIndex({ marketplace: 'ozon', currentStage: 'composition' })).toBe(3)
  })

  it('keeps box controls active before WB handoff', () => {
    expect(fbsBoxEditingDisabled('wb', false)).toBe(false)
  })

  it('stops editing boxes only after WB handoff, not because the server still reports an earlier stage', () => {
    expect(fbsBoxEditingDisabled('wb', false)).toBe(false)
    expect(fbsBoxEditingDisabled('wb', true)).toBe(true)
  })

  it('opens boxes without consulting WB packaging progress', () => {
    expect(fbsAccessibleStageIndex({ marketplace: 'wb', currentStage: 'packing' })).toBe(3)
  })

  it('does not require a packaging task to leave WB composition', () => {
    expect(fbsAccessibleStageIndex({ marketplace: 'wb', currentStage: 'composition' })).toBe(3)
  })

  it('does not yank the WB operator back from boxes during refresh', () => {
    expect(fbsStageAfterWorkspaceRefresh('wb', 'boxes', 'picking')).toBe('boxes')
    expect(fbsStageAfterWorkspaceRefresh('wb', 'packing', 'picking')).toBe('packing')
  })

  it('does not yank the Ozon operator back from boxes during refresh either', () => {
    expect(fbsStageAfterWorkspaceRefresh('ozon', 'boxes', 'picking')).toBe('boxes')
    expect(fbsStageAfterWorkspaceRefresh('ozon', 'packing', 'picking')).toBe('packing')
    expect(fbsStageAfterWorkspaceRefresh('ozon', 'composition', 'picking')).toBe('picking')
  })

  it('offers unassigned orders in boxes regardless of packaging status', () => {
    const orders = [
      { id: 'pending', pack: { status: 'pending' } },
      { id: 'packed', pack: { status: 'packed' } },
      { id: 'assigned', pack: { status: 'pending' } },
    ]
    expect(fbsOrdersAvailableForBox(orders, new Set(['assigned']))).toEqual([
      orders[0],
      orders[1],
    ])
  })
})

describe('WB delivery idempotency retry', () => {
  it('keeps the key only while the result of the same operation is unresolved', () => {
    expect(fbsDeliveryErrorKeepsIdempotencyKey({ code: 'wb_timeout', retryable: true })).toBe(true)
    expect(fbsDeliveryErrorKeepsIdempotencyKey({ code: 'operation_in_progress', retryable: true })).toBe(true)
  })

  it('rotates the key after a definitive WB rejection', () => {
    expect(fbsDeliveryErrorKeepsIdempotencyKey({ code: 'meta_validation_fail', retryable: true })).toBe(false)
    expect(fbsDeliveryErrorKeepsIdempotencyKey({ code: 'meta_validation_fail', retryable: false })).toBe(false)
    expect(fbsDeliveryErrorKeepsIdempotencyKey({ code: 'wb_upstream_error_502', retryable: false })).toBe(false)
  })
})

describe('WB delivery confirmation', () => {
  it('does not freeze the action after a failed preflight request', () => {
    expect(fbsDeliveryConfirmDisabled('wb', false, null)).toBe(false)
  })

  it('stays disabled while loading or after a real server blocker', () => {
    expect(fbsDeliveryConfirmDisabled('wb', true, null)).toBe(true)
    expect(fbsDeliveryConfirmDisabled('wb', false, { can_deliver: false })).toBe(true)
    expect(fbsDeliveryConfirmDisabled('wb', false, { can_deliver: true })).toBe(false)
  })

  it('keeps Ozon disabled until a successful preflight exists', () => {
    expect(fbsDeliveryConfirmDisabled('ozon', false, null)).toBe(true)
    expect(fbsDeliveryConfirmDisabled('ozon', false, { can_deliver: false })).toBe(true)
    expect(fbsDeliveryConfirmDisabled('ozon', false, { can_deliver: true })).toBe(false)
  })
})

describe('FBS picking list print document', () => {
  it('renders the current server-owned picking data and escapes product fields', () => {
    const html = buildFbsPickingListPrintHtml({
      supplyName: 'FBS <05.08>',
      wbSupplyId: 'WB-GI-1',
      sellerName: 'Seller & Co',
      wmsWarehouseName: 'Основной склад',
      routeLabel: 'ПВЗ',
      deadlineLabel: '10.08.2026, 12:00',
      printedAtLabel: '05.08.2026, 19:00',
      rows: [{
        name: '<script>alert(1)</script>',
        size: '38',
        imageUrl: 'javascript:alert(1)',
        identifiers: ['ART-1', '2000000000011'],
        locations: ['A-01: 2'],
        required: 2,
        picked: 1,
        wbOrders: [500001, 500002],
        stickerCodes: ['56672606304'],
        marking: 'КИЗ',
      }],
    })

    expect(html).toContain('Лист подбора FBS')
    expect(html).toContain('FBS &lt;05.08&gt;')
    expect(html).toContain('Seller &amp; Co')
    expect(html).toContain('№500001')
    expect(html).toContain('<td class="number">1–2</td>')
    expect(html).toContain('5667260 <strong>6304</strong>')
    expect(html).toContain('.sticker { width: 116px; font-size: 12px; white-space: nowrap;')
    expect(html).toContain('A-01: 2')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).not.toContain('javascript:alert(1)')
  })

  it('печатает размер отдельной колонкой, а без размера ставит прочерк', () => {
    const base = {
      supplyName: 'FBS 19.08',
      wbSupplyId: 'WB-GI-2',
      sellerName: 'Loviana',
      wmsWarehouseName: 'основной',
      routeLabel: 'Склад / СЦ',
      deadlineLabel: '24.08.2026, 12:00',
      printedAtLabel: '19.08.2026, 16:20',
    }
    const row = {
      name: 'Лоферы замшевые',
      imageUrl: null,
      identifiers: ['J308-6'],
      locations: [],
      required: 1,
      picked: 0,
      wbOrders: [5524537174],
      stickerCodes: [null],
      marking: 'Не требуется',
    }

    const withSize = buildFbsPickingListPrintHtml({ ...base, rows: [{ ...row, size: '38' }] })
    expect(withSize).toContain('<th class="size">Размер</th>')
    expect(withSize).toContain('<td class="size">38</td>')

    const noSize = buildFbsPickingListPrintHtml({ ...base, rows: [{ ...row, size: null }] })
    expect(noSize).toContain('<td class="size">—</td>')
  })
})

describe('summarizeDeliveryChecks', () => {
  const check = (
    code: string,
    message: string,
    severity: 'blocker' | 'warning' | 'info',
    orderId: string | null = null,
  ) => ({ code, message, ok: severity === 'info', severity, order_id: orderId })

  it('схлопывает одинаковые причины и сохраняет номера заказов отдельным списком', () => {
    const summary = summarizeDeliveryChecks(
      [
        check('marking_required', 'Честный знак не нанесён.', 'warning', 'a'),
        check('marking_required', 'Честный знак не нанесён.', 'warning', 'b'),
        check('marking_required', 'Честный знак не нанесён.', 'warning', 'c'),
      ],
      new Map([['a', 530009], ['b', 530011], ['c', 530015]]),
    )
    expect(summary.blockers).toEqual([])
    expect(summary.warnings).toEqual([{
      key: 'marking_required',
      title: 'Не нанесён Честный знак',
      description: 'Передаче не мешает; нанести можно и после неё.',
      orderIds: [530009, 530011, 530015],
    }])
  })

  it('объединяет расхождения и закрытые заказы по типу, оставляя WB-номера только в раскрытии', () => {
    const summary = summarizeDeliveryChecks([
      check('wb_terminal_order_ignored', 'Заказ WB 530011 уже отменён или закрыт; он исключён из списания.', 'warning', 'b'),
      check('wb_terminal_order_ignored', 'Заказ WB 530009 уже отменён или закрыт; он исключён из списания.', 'warning', 'a'),
      check('wb_terminal_order_ignored', 'Заказ WB 530009 уже отменён или закрыт; он исключён из списания.', 'warning', 'a'),
      check('wb_supply_composition_discrepancy', 'Заказ WB 530015: unknown_order.', 'blocker'),
      check('wb_supply_composition_discrepancy', 'Заказ WB 530013: seller_mismatch.', 'blocker', 'missing-local-order'),
    ], new Map([['a', 530009], ['b', 530011]]))
    expect(summary.warnings).toEqual([{
      key: 'wb_terminal_order_ignored',
      title: 'Заказы уже отменены или закрыты',
      description: 'Исключены из списания и не мешают передаче поставки.',
      orderIds: [530009, 530011],
    }])
    expect(summary.blockers).toEqual([{
      key: 'wb_supply_composition_discrepancy',
      title: 'Состав поставки не совпадает с WB',
      description: null,
      orderIds: [530013, 530015],
      orderDetails: { 530013: ['seller_mismatch.'], 530015: ['unknown_order.'] },
    }])
  })

  it('не создаёт отдельные строки нехватки по каждому количеству', () => {
    const summary = summarizeDeliveryChecks([
      check('negative_stock', 'Не хватает 1 шт.; после подтверждения остаток будет списан в минус.', 'warning', 'a'),
      check('negative_stock', 'Не хватает 5 шт.; после подтверждения остаток будет списан в минус.', 'warning', 'b'),
    ], new Map([['a', 530009], ['b', 530011]]))
    expect(summary.warnings).toEqual([{
      key: 'negative_stock',
      title: 'Недостаточно остатка; после подтверждения он будет списан в минус.',
      description: null,
      orderIds: [530009, 530011],
      orderDetails: {
        530009: ['Не хватает 1 шт.; после подтверждения остаток будет списан в минус.'],
        530011: ['Не хватает 5 шт.; после подтверждения остаток будет списан в минус.'],
      },
    }])
  })

  it('сохраняет разные причины маркировки у конкретных заказов внутри одной группы', () => {
    const pending = 'WB ещё не подтвердил маркировку.'
    const rejected = 'WB не принял маркировку: код уже использован'
    const replacement = 'WB подтвердил другой код маркировки.'
    const summary = summarizeDeliveryChecks([
      check('marking_not_allowed', pending, 'warning', 'a'),
      check('marking_not_allowed', rejected, 'warning', 'b'),
      check('marking_not_allowed', replacement, 'warning', 'c'),
      check('marking_not_allowed', rejected, 'warning', 'b'),
    ], new Map([['a', 530009], ['b', 530011], ['c', 530015]]))
    expect(summary.warnings).toEqual([{
      key: 'marking_not_allowed', title: 'Маркировка требует проверки', description: null,
      orderIds: [530009, 530011, 530015],
      orderDetails: { 530009: [pending], 530011: [rejected], 530015: [replacement] },
    }])
  })

  it('не показывает отсутствие коробов и распределения в проверке передачи', () => {
    const summary = summarizeDeliveryChecks(
      [
        check('physical_boxes_required', 'В поставке пока нет коробов.', 'warning'),
        check('packed_order_unassigned', 'Для заказа не указан короб.', 'warning', 'a'),
        check('packed_order_unassigned', 'Для заказа не указан короб.', 'warning', 'b'),
      ],
      new Map([['a', 530015], ['b', 530009]]),
    )
    expect(summary.warnings).toEqual([])
  })

  it('разводит запреты и предупреждения по уровню, а не по признаку ok', () => {
    const summary = summarizeDeliveryChecks(
      [
        check('supply_bad_status', 'Поставка уже передана или закрыта.', 'blocker'),
        check('negative_stock', 'Остаток уйдёт в минус.', 'warning', 'a'),
        check('order_sticker_ready', 'Стикер готов.', 'info', 'a'),
      ],
      new Map([['a', 777]]),
    )
    expect(summary.blockers).toEqual([{
      key: 'supply_bad_status',
      title: 'Поставка уже передана или закрыта.',
      description: null,
      orderIds: [],
    }])
    expect(summary.warnings).toEqual([{
      key: 'negative_stock',
      title: 'Недостаточно остатка; после подтверждения он будет списан в минус.',
      description: null,
      orderIds: [777],
      orderDetails: { 777: ['Остаток уйдёт в минус.'] },
    }])
  })
})
