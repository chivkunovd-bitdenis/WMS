// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import {
  BOX_PAIR_WINDOW_MS,
  createBoxPairTracker,
  loadFboContainers,
  loadFboPickUi,
  saveFboContainers,
  saveFboPickUi,
} from './fboPickState'
import { kizCountsByProduct, kizDisplayCode, type FboKizCode } from './fboKizData'

// WMS-686 · D1.6: правило «двойного скана» короба и сохранение состояния экрана подбора FBO.

describe('createBoxPairTracker', () => {
  const BOX = 'INB-000101'
  const SOURCE = 'obj:box-1'

  it('второй такой же код в пределах окна — «забрать»; третий быстрый — «игнорировать»', () => {
    const tracker = createBoxPairTracker()
    expect(tracker.arrive(BOX, 1000, null)).toBe('normal')
    tracker.selected(BOX, 1000, SOURCE)
    expect(tracker.arrive(BOX, 1000 + BOX_PAIR_WINDOW_MS, SOURCE)).toBe('take')
    expect(tracker.arrive(BOX, 3100, SOURCE)).toBe('ignore')
    expect(tracker.arrive(BOX, 5000, SOURCE)).toBe('ignore')
    // Прошло больше окна после последнего такого скана — это уже новый первый скан.
    expect(tracker.arrive(BOX, 8000, SOURCE)).toBe('normal')
  })

  it('второй скан позже окна пары не образует', () => {
    const tracker = createBoxPairTracker()
    tracker.selected(BOX, 1000, SOURCE)
    expect(tracker.arrive(BOX, 1000 + BOX_PAIR_WINDOW_MS + 1, SOURCE)).toBe('normal')
    expect(tracker.arrive(BOX, 3100, SOURCE)).toBe('normal')
  })

  it('любой другой код между сканами рвёт пару', () => {
    const tracker = createBoxPairTracker()
    tracker.selected(BOX, 1000, SOURCE)
    expect(tracker.arrive('010460000000001121AbCd000001', 1200, SOURCE)).toBe('normal')
    expect(tracker.arrive(BOX, 1400, SOURCE)).toBe('normal')
  })

  it('источник сменили — пары нет', () => {
    const tracker = createBoxPairTracker()
    tracker.selected(BOX, 1000, SOURCE)
    expect(tracker.arrive(BOX, 1200, 'obj:box-2')).toBe('normal')
  })

  it('reset (кнопка «Забрать короб целиком») убирает пару', () => {
    const tracker = createBoxPairTracker()
    tracker.selected(BOX, 1000, SOURCE)
    tracker.reset()
    expect(tracker.arrive(BOX, 1200, SOURCE)).toBe('normal')
  })
})

describe('хранилище состояния экрана подбора FBO', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('вид, раскрытия и источник читаются обратно по id отгрузки; чужой документ не затронут', () => {
    const ui = {
      view: 'products' as const,
      source: 'obj:box-1',
      sourceLabel: 'INB-000101',
      sourceBarcode: 'INB-000101',
      expanded: ['line-1'],
      collapsed: ['cell:loc-a'],
      kizOpen: ['p-a'],
    }
    saveFboPickUi('doc-1', ui)
    expect(loadFboPickUi('doc-1')).toEqual(ui)
    expect(loadFboPickUi('doc-2')).toBeNull()
  })

  it('повреждённая запись читается как пустая, а не роняет экран', () => {
    window.sessionStorage.setItem('wms.fbo-pick.ui.v1.doc-1', '{bad json')
    expect(loadFboPickUi('doc-1')).toBeNull()
    window.sessionStorage.setItem('wms.fbo-pick.ui.v1.doc-2', JSON.stringify({ view: 'nonsense', expanded: 5 }))
    expect(loadFboPickUi('doc-2')).toMatchObject({ view: 'cells', expanded: [], source: null })
  })

  it('тара, выбранная сканом, сохраняется вместе с ячейкой', () => {
    const containers = new Map([['obj:box-1', { locationId: 'loc-a', containerKind: 'box' as const, containerId: 'box-1' }]])
    saveFboContainers('doc-1', containers)
    expect(loadFboContainers('doc-1')).toEqual(containers)
    expect(loadFboContainers('doc-2').size).toBe(0)
  })
})

describe('КИЗ товара', () => {
  const code = (id: string, productId: string): FboKizCode => ({
    marking_code_id: id, cis_code: `01${id}`, product_id: productId, line_id: null, status: 'applied',
    intake_document_number: null, linked_at: null, has_label_artifact: false,
  })

  it('число КИЗ — счёт кодов по product_id', () => {
    const counts = kizCountsByProduct([code('1', 'a'), code('2', 'a'), code('3', 'b')])
    expect(counts.get('a')).toBe(2)
    expect(counts.get('b')).toBe(1)
    expect(counts.get('c')).toBeUndefined()
  })

  it('разделитель GS в коде показывается видимым значком', () => {
    expect(kizDisplayCode(`0104600000000011\u001d21AbCd`)).toBe('0104600000000011␝21AbCd')
  })
})
