import { describe, expect, it } from 'vitest'
import { buildFbsPickingListPrintHtml, normalizeMetadataKind, orderVerdictChips } from './fbsUx'

describe('FBS required identifiers', () => {
  it('TC-FBS-UX-002 sends the API-supported kind when WB calls it KIZ', () => {
    expect(normalizeMetadataKind('KIZ')).toBe('sgtin')
    expect(normalizeMetadataKind('SGTIN')).toBe('sgtin')
    expect(normalizeMetadataKind('UIN')).toBe('uin')
    expect(normalizeMetadataKind(undefined)).toBe('sgtin')
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
    expect(html).toContain('5667260 <strong>6304</strong>')
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

// Хелпер: создаёт минимальный объект order для orderVerdictChips
function makeOrder(required: string[], optional: string[], states: Array<{ kind: string; status: string; reason?: string | null }>) {
  return { metadata: { required, optional, states } }
}

describe('orderVerdictChips — WB verdict chips', () => {
  // S-03-TC-001: accepted/allowed_without_check → зелёный «WB подтвердил»
  it('TC-001 accepted → зелёный WB подтвердил', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'accepted' }]))
    expect(chips).toHaveLength(1)
    expect(chips[0]).toMatchObject({ label: 'WB подтвердил', tone: 'ok' })
  })

  it('TC-001 allowed_without_check → зелёный WB подтвердил', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'allowed_without_check' }]))
    expect(chips[0]).toMatchObject({ label: 'WB подтвердил', tone: 'ok' })
  })

  // S-03-TC-002 / S-03-TC-020: pending без reason → жёлтый «WB проверяет» (не «WB подтвердил»)
  it('TC-002/TC-020 pending без reason → жёлтый WB проверяет', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'pending' }]))
    expect(chips[0]).toMatchObject({ label: 'WB проверяет', tone: 'warn' })
  })

  // S-03-TC-003: pending c reason → красный «WB не принял» + reasonCaption
  it('TC-003 pending с reason → красный WB не принял + reasonCaption', () => {
    const chips = orderVerdictChips(makeOrder(['uin'], [], [{ kind: 'uin', status: 'pending', reason: 'uinBadStatus' }]))
    expect(chips[0]).toMatchObject({ label: 'WB не принял', tone: 'stop' })
    // reasonCaption — человеческий перевод, не пустой и не технический ключ
    expect(chips[0].reasonCaption).toBeTruthy()
    expect(chips[0].reasonCaption).not.toBe('uinBadStatus')
  })

  // S-03-TC-004: rejected → красный «WB не принял»
  it('TC-004 rejected → красный WB не принял', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'rejected' }]))
    expect(chips[0]).toMatchObject({ label: 'WB не принял', tone: 'stop' })
  })

  // S-03-TC-005: missing → красный «Нужен ЧЗ»
  it('TC-005 missing → красный Нужен ЧЗ', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'missing' }]))
    expect(chips[0]).toMatchObject({ label: 'Нужен ЧЗ', tone: 'stop' })
  })

  // S-03-TC-006/TC-007: optional kind → серый «ЧЗ не требуется»
  it('TC-006/TC-007 optional kind с любым state → серый ЧЗ не требуется', () => {
    const chips = orderVerdictChips(makeOrder([], ['sgtin'], [{ kind: 'sgtin', status: 'allowed_without_check' }]))
    expect(chips).toHaveLength(1)
    expect(chips[0]).toMatchObject({ label: 'ЧЗ не требуется', tone: 'neutral' })
  })

  // S-03-TC-008: no state for required kind → серый «Статус уточняется»
  it('TC-008 нет state для required kind → серый Статус уточняется', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], []))
    expect(chips[0]).toMatchObject({ label: 'Статус уточняется', tone: 'neutral' })
  })

  // S-03-TC-009: два required kind → два чипа с разными вердиктами
  it('TC-009 два required kind → два чипа', () => {
    const chips = orderVerdictChips(makeOrder(
      ['sgtin', 'uin'],
      [],
      [
        { kind: 'sgtin', status: 'accepted' },
        { kind: 'uin', status: 'pending', reason: 'uinBadStatus' },
      ],
    ))
    expect(chips).toHaveLength(2)
    expect(chips[0]).toMatchObject({ kind: 'sgtin', tone: 'ok' })
    expect(chips[1]).toMatchObject({ kind: 'uin', tone: 'stop' })
  })

  // S-03-TC-019: неизвестный reason → показывается как есть через translateMetaStatusReason
  it('TC-019 неизвестный reason не скрывается и не заменяется «Ошибкой WB»', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'rejected', reason: 'someUnknownReason' }]))
    // reasonCaption существует — неизвестный reason всё равно передаётся
    expect(chips[0].reasonCaption).toBeDefined()
  })

  // S-03-TC-028: reason="" (пустая строка) → трактуется как отсутствие reason → жёлтый
  it('TC-028 reason="" (пустая строка) → жёлтый WB проверяет, не красный', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'pending', reason: '' }]))
    expect(chips[0]).toMatchObject({ label: 'WB проверяет', tone: 'warn' })
  })

  // replacement_required → красный «WB не принял»
  it('replacement_required → красный WB не принял', () => {
    const chips = orderVerdictChips(makeOrder(['sgtin'], [], [{ kind: 'sgtin', status: 'replacement_required' }]))
    expect(chips[0]).toMatchObject({ label: 'WB не принял', tone: 'stop' })
  })

  // Заказ без required kinds → нет чипов (не блокирует кнопку)
  it('TC-016 заказ без required kinds → пустой массив чипов', () => {
    const chips = orderVerdictChips(makeOrder([], [], []))
    expect(chips).toHaveLength(0)
  })
})
