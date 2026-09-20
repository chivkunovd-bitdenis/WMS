import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { FbsStockDialog, type FbsStockDialogProps } from './FbsStockDialog'
import { fbsWarehousesLoadError, type CabinetList } from './fbsSellerWarehouseRows'
import { toProductBindingState, type StockBinding, type StockDialogProduct } from './fbsStockBlocks'

// Разметка окна «Остаток для FBS» (WMS-469) без браузера: что показывается и
// что скрыто при разных данных. Поведение по нажатиям проверяется руками в
// браузере — здесь только то, что видно сразу после открытия.

vi.mock('../../../ui-kit', async (original) => ({
  ...await original<object>(),
  // Only remove the portal for SSR; all fields and dialog content are real.
  AppDialog: ({ title, children, actions }: { title: ReactNode; children: ReactNode; actions: ReactNode }) =>
    <div><h2>{title}</h2>{children}{actions}</div>,
}))

const YARTSEVO = '441c8654-b6c2-48fe-950f-65acbc921118'
const wb: StockBinding = {
  id: 'b-wb', marketplace: 'wb', externalId: '501001', name: 'E2E Seller Warehouse',
  wmsWarehouseId: YARTSEVO, wmsWarehouseName: 'Ярцево', served: true, editable: true,
}
const ozon: StockBinding = {
  id: 'b-ozon', marketplace: 'ozon', externalId: '1020005029603630', name: 'Хоругвино',
  wmsWarehouseId: YARTSEVO, wmsWarehouseName: 'Ярцево', served: true, editable: true,
}
const received: CabinetList = { received: true, rows: [] }
const cabinets = { wb: received, ozon: received }

function product(
  id: string, name: string,
  rules: Record<string, { free: number; applicable?: boolean; mode?: 'percent' | 'units'; value?: number; publish?: boolean }>,
): StockDialogProduct {
  return {
    id, name, sku: id.toUpperCase(), size: null,
    byBinding: Object.fromEntries(Object.entries(rules).map(([bindingId, one]) => [bindingId, toProductBindingState({
      publish: one.publish ?? true, mode: one.mode ?? 'percent', value: one.value ?? 0, marketplace: 'wb',
      external_warehouse_id: '501001', wms_warehouse_id: YARTSEVO, served: true,
      applicable: one.applicable ?? true, on_hand: one.free, reserved: 0, free_stock: one.free, published_now: 0,
    })])),
  }
}

function render(overrides: Partial<FbsStockDialogProps>) {
  return renderToStaticMarkup(<FbsStockDialog open sellerName="ИП Тестовый Аудит"
    products={[product('p', 'Футболка', { 'b-wb': { free: 120 } })]} bindings={[wb]} cabinets={cabinets}
    wmsWarehouses={[{ id: YARTSEVO, name: 'Ярцево' }]} canEditBindings onClose={() => {}} onSave={() => {}}
    onAddBinding={() => {}} onChangeWmsWarehouse={() => {}} onServedChange={() => {}} {...overrides} />)
}

/** Тег с этим data-testid — чтобы проверить его атрибуты, а не всю разметку. */
function tag(markup: string, testId: string): string {
  const match = markup.match(new RegExp(`<[^>]*data-testid="${testId}"[^>]*>`))
  if (!match) throw new Error(`no element ${testId}`)
  return match[0]
}

describe('WMS-469 окно «Остаток для FBS»: структура', () => {
  it('C1: без связок — текст, кнопка «Добавить склад», без общего остатка в шапке и «уедет»', () => {
    const markup = render({ bindings: [], products: [product('p', 'Футболка', {})] })
    expect(markup).toContain('Склады селлера ещё не добавлены.')
    expect(markup).toContain('data-testid="fbs-stock-add"')
    expect(markup).not.toContain('data-testid="fbs-stock-block-')
    expect(markup).not.toContain('уедет')
    expect(markup).toContain('Футболка · P')
  })

  it('R2: блок — значок и название склада продавца, выбор склада ФФ, суммы по этому складу', () => {
    const markup = render({})
    expect(markup).toContain('data-testid="fbs-stock-block-b-wb"')
    expect(markup).toContain('E2E Seller Warehouse')
    expect(tag(markup, 'fbs-stock-bind-b-wb')).toContain('<select')
    expect(markup).toContain('на складе 120 шт, занято 0 — свободно')
    expect(markup).toContain('Принимаем заказы продавца со склада «E2E Seller Warehouse»')
    expect(markup).toContain('Передавать остаток на')
    expect(markup).toContain('data-testid="fbs-stock-percent-b-wb"')
    expect(markup).toContain('data-testid="fbs-stock-units-b-wb"')
    expect(markup).toContain('data-testid="fbs-stock-by-percent-b-wb"')
    expect(markup).toContain('data-testid="fbs-stock-add"')
  })

  it('заголовок массового окна называет число товаров и продавца', () => {
    const markup = render({ products: [product('a', 'А', { 'b-wb': { free: 1 } }), product('b', 'Б', { 'b-wb': { free: 1 } })] })
    expect(markup).toContain('Остаток для FBS · 2 товара')
    expect(markup).toContain('2 товара, ИП Тестовый Аудит')
  })

  it('R9: процентный режим — поле «шт» только для чтения и показывает расчёт; ручной — редактируемое число', () => {
    const percent = render({ products: [product('p', 'Футболка', { 'b-wb': { free: 120, mode: 'percent', value: 50 } })] })
    expect(tag(percent, 'fbs-stock-units-b-wb')).toContain('readOnly=""')
    expect(tag(percent, 'fbs-stock-units-b-wb')).toContain('value="60"')
    expect(tag(percent, 'fbs-stock-by-percent-b-wb')).toContain('checked')
    const units = render({ products: [product('p', 'Футболка', { 'b-wb': { free: 120, mode: 'units', value: 30 } })] })
    expect(tag(units, 'fbs-stock-units-b-wb')).not.toContain('readOnly')
    expect(tag(units, 'fbs-stock-units-b-wb')).toContain('value="30"')
    expect(tag(units, 'fbs-stock-by-percent-b-wb')).not.toContain('checked')
    expect(units).toContain('>25 %<')
  })
})

describe('WMS-469 F2/F6: сохранённый лимит и время записи', () => {
  it('R14: сохранённый ручной потолок выше остатка при открытии не режется и подписи нет', () => {
    const markup = render({ products: [product('p', 'Футболка', { 'b-wb': { free: 30, mode: 'units', value: 50 } })] })
    expect(tag(markup, 'fbs-stock-units-b-wb')).toContain('value="50"')
    expect(markup).not.toContain('data-testid="fbs-stock-cap-note-b-wb"')
    // Уедет min(50, 30) = 30 из 30 — индикатор честно показывает 100 %.
    expect(markup).toContain('>100 %<')
  })

  it('R14: выключенная передача с потолком выше остатка тоже остаётся как сохранена', () => {
    const markup = render({ products: [product('p', 'Футболка', { 'b-wb': { free: 30, mode: 'units', value: 50, publish: false } })] })
    expect(tag(markup, 'fbs-stock-units-b-wb')).toContain('value="50"')
    expect(tag(markup, 'fbs-stock-publish-b-wb')).not.toContain('checked')
  })

  it('R16/R17: пока идёт запись, поля, переключатель, галка приёма и кнопки заперты', () => {
    const markup = render({ busy: true, products: [product('p', 'Футболка', { 'b-wb': { free: 30, mode: 'units', value: 10 } })] })
    for (const id of ['fbs-stock-units-b-wb', 'fbs-stock-by-percent-b-wb', 'fbs-stock-publish-b-wb', 'fbs-stock-served-b-wb', 'fbs-stock-bind-b-wb', 'fbs-stock-add', 'fbs-stock-cancel', 'fbs-stock-save']) {
      expect(tag(markup, id), id).toContain('disabled')
    }
    expect(markup).toContain('data-testid="fbs-stock-percent-b-wb"')
    expect(tag(markup, 'fbs-stock-percent-b-wb')).toContain('Mui-disabled')
  })
})

describe('WMS-454 C28: Ozon-блок только у товара с карточкой Ozon', () => {
  it('прячет Ozon у WB-only товара, даже если у продавца есть Ozon-привязка', () => {
    const markup = render({ bindings: [wb, ozon],
      products: [product('p', 'Футболка', { 'b-wb': { free: 10 }, 'b-ozon': { free: 10, applicable: false } })] })
    expect(markup).toContain('data-testid="fbs-stock-block-b-wb"')
    expect(markup).not.toContain('data-testid="fbs-stock-block-b-ozon"')
    expect(markup).not.toContain('Ozon')
  })

  it('показывает Ozon-блок со своим цветом и подписью товару с карточкой Ozon', () => {
    const markup = render({ bindings: [wb, ozon],
      products: [product('p', 'Футболка', { 'b-wb': { free: 10 }, 'b-ozon': { free: 10 } })] })
    expect(markup).toContain('data-testid="fbs-stock-block-b-ozon"')
    expect(markup).toContain('Хоругвино')
    expect(markup).toContain('data-testid="fbs-stock-publish-b-ozon"')
    expect(markup).toContain('data-testid="fbs-stock-publish-b-wb"')
  })

  it('WMS-417: одинаковый номер склада у WB и Ozon — два разных блока со своими числами', () => {
    const wb123 = { ...wb, id: 'b-wb-123', externalId: '123', name: 'wb' }
    const ozon123 = { ...ozon, id: 'b-ozon-123', externalId: '123', name: 'ozon' }
    const markup = render({ bindings: [wb123, ozon123], products: [product('p', 'Synthetic', {
      'b-wb-123': { free: 6, mode: 'units', value: 5 }, 'b-ozon-123': { free: 6, mode: 'units', value: 3 },
    })] })
    expect(tag(markup, 'fbs-stock-units-b-wb-123')).toContain('value="5"')
    expect(tag(markup, 'fbs-stock-units-b-ozon-123')).toContain('value="3"')
  })
})

describe('WMS-469 R7 галка приёма заказов', () => {
  it('C13: при снятой галке — чип, строка публикации скрыта', () => {
    const markup = render({ bindings: [{ ...wb, served: false }] })
    expect(tag(markup, 'fbs-stock-served-b-wb')).not.toContain('checked')
    expect(markup).toContain('заказы не принимаем')
    expect(markup).not.toContain('data-testid="fbs-stock-row-b-wb"')
    expect(markup).not.toContain('Обслуживаем склад')
  })

  it('C9: длинные названия склада и продавца остаются в разметке целиком', () => {
    const longName = 'Склад продавца с очень длинным названием, которое не помещается в одну строку окна'
    const markup = render({ bindings: [{ ...wb, name: longName, served: false }],
      sellerName: 'ИП Тестовый Аудит с очень длинным наименованием продавца',
      products: [product('a', 'Костюм с очень длинным названием товара для проверки переноса', { 'b-wb': { free: 1 } }),
        product('b', 'Б', { 'b-wb': { free: 1 } })] })
    expect(markup).toContain(`Принимаем заказы продавца со склада «${longName}»`)
    expect(markup).toContain('ИП Тестовый Аудит с очень длинным наименованием продавца')
  })
})

describe('WMS-469 R18 / D4 кабинет селлера', () => {
  it('C26: связка, склад ФФ и приём заказов только читаются; «Добавить склад» нет; лимит правится', () => {
    const markup = render({ canEditBindings: false, onAddBinding: undefined, onChangeWmsWarehouse: undefined,
      onServedChange: undefined, bindings: [{ ...wb, editable: false }] })
    expect(tag(markup, 'fbs-stock-bind-b-wb')).toContain('disabled')
    expect(tag(markup, 'fbs-stock-served-b-wb')).toContain('disabled')
    expect(markup).not.toContain('data-testid="fbs-stock-add"')
    expect(markup).not.toContain('Склады селлера ещё не добавлены')
    expect(tag(markup, 'fbs-stock-units-b-wb')).not.toContain('disabled')
    expect(tag(markup, 'fbs-stock-publish-b-wb')).not.toContain('disabled')
  })

  it('editable=false от сервера запирает связку и у администратора', () => {
    const markup = render({ bindings: [{ ...wb, editable: false }] })
    expect(tag(markup, 'fbs-stock-bind-b-wb')).toContain('disabled')
    expect(tag(markup, 'fbs-stock-served-b-wb')).toContain('disabled')
  })
})

describe('WMS-457 названия и причины в окне', () => {
  it('чипы «нет в кабинете» и «название недоступно» рядом с номером; выдуманных названий нет', () => {
    const markup = render({
      bindings: [wb,
        { ...wb, id: 'b-gone', externalId: '501999', name: '№ 501999', nameIssue: 'not_in_cabinet', served: true },
        { ...ozon, id: 'b-ozon', name: '№ 1020005029603630', nameIssue: 'list_unavailable' }],
      products: [product('p', 'Худи', { 'b-wb': { free: 100 }, 'b-gone': { free: 0 }, 'b-ozon': { free: 100 } })],
      ozonWarehousesError: 'Справочник складов Ozon недоступен',
    })
    expect(markup).not.toContain('data-testid="fbs-stock-name-issue-b-wb"')
    expect(markup).toContain('Принимаем заказы продавца со склада «№ 501999»')
    expect(markup).toContain('data-testid="fbs-stock-name-issue-b-gone"')
    expect(markup).toContain('нет в кабинете')
    expect(markup).toContain('Принимаем заказы продавца со склада «№ 1020005029603630»')
    expect(markup).toContain('data-testid="fbs-stock-name-issue-b-ozon"')
    expect(markup).toContain('название недоступно')
    expect(markup).not.toContain('Склад Ozon 1020005029603630')
    expect(markup).not.toContain('Склад WB 501999')
  })

  it('плашка причины Wildberries отдельно от ошибки действия', () => {
    const reason = fbsWarehousesLoadError({ status: 403, code: 'missing_marketplace_token', message: 'Нет токена WB Marketplace.' })
    const markup = render({ wbWarehousesError: reason, actionError: null,
      bindings: [{ ...wb, id: 'b-nokey', externalId: '777001', name: '№ 777001', nameIssue: 'list_unavailable' }],
      products: [product('p', 'Кепка', { 'b-nokey': { free: 1 } })], cabinets: { wb: { received: false }, ozon: { received: false } } })
    expect(markup).toContain('data-testid="fbs-stock-wb-directory-error"')
    expect(markup).toContain('У продавца не сохранён ключ Wildberries с правами «Маркетплейс»')
    expect(markup).not.toContain('data-testid="fbs-stock-error"')
    expect(markup).toContain('Принимаем заказы продавца со склада «№ 777001»')
    expect(markup).toContain('название недоступно')
    // Справочник не получен — добавить склад нельзя, и кнопка заперта.
    expect(tag(markup, 'fbs-stock-add')).toContain('disabled')
  })

  it('F7 / R19: причина недоступности имени Ozon видна в окне у селлера, без формы добавления', () => {
    const reason = 'Справочник складов Ozon недоступен: боевые запросы к Ozon выключены настройкой WMS_OZON_LIVE_API.'
    const markup = render({
      canEditBindings: false, onAddBinding: undefined, onChangeWmsWarehouse: undefined, onServedChange: undefined,
      bindings: [{ ...wb, editable: false }, { ...ozon, name: '№ 1020005029603630', nameIssue: 'list_unavailable', editable: false }],
      products: [product('p', 'Худи', { 'b-wb': { free: 100 }, 'b-ozon': { free: 100 } })],
      cabinets: { wb: received, ozon: { received: false } }, ozonWarehousesError: reason,
    })
    expect(markup).not.toContain('data-testid="fbs-stock-picker"')
    expect(markup).toContain('data-testid="fbs-stock-ozon-directory-error"')
    expect(markup).toContain(reason)
    expect(markup).toContain('название недоступно')
  })

  it('F7: без Ozon-блока без имени плашки Ozon нет — у продавца только WB', () => {
    const markup = render({ cabinets: { wb: received, ozon: { received: false } }, ozonWarehousesError: 'Справочник складов Ozon недоступен' })
    expect(markup).not.toContain('data-testid="fbs-stock-ozon-directory-error"')
  })

  it('R17: ошибка действия показывается в окне, а само окно с блоками остаётся', () => {
    const markup = render({ actionError: 'Не удалось сохранить правило' })
    expect(markup).toContain('data-testid="fbs-stock-error"')
    expect(markup).toContain('Не удалось сохранить правило')
    expect(markup).toContain('data-testid="fbs-stock-block-b-wb"')
  })
})
