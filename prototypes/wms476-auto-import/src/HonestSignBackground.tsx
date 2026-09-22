import type { ReactNode } from 'react'

type Props = {
  onOpenImport: () => void
}

const kpis: { label: string; value: string }[] = [
  { label: 'Доступно личных', value: '842' },
  { label: 'С общими корзинами', value: '17' },
  { label: 'Брак', value: '6' },
  { label: 'На исходе', value: '4' },
]

type BackgroundRow = {
  id: string
  sku: string
  name: string
  size: string
  personal: number
  printed: number
  low: boolean
}

const backgroundRows: BackgroundRow[] = [
  {
    id: 'row-1',
    sku: 'PAL-CHIFFON-OASIS-2026-LTD-EDITION',
    name: 'Палантин шифоновый «Оазис», лимитированная коллекция 2026',
    size: '90×180',
    personal: 128,
    printed: 84,
    low: false,
  },
  {
    id: 'row-2',
    sku: 'HDB-CASHMERE-CLASSIC-BURGUNDY-XL',
    name: 'Худи кашемировое «Классик», бордо',
    size: 'XL',
    personal: 8,
    printed: 260,
    low: true,
  },
  {
    id: 'row-3',
    sku: 'SCR-SILK-SUNSET-70',
    name: 'Платок шёлковый «Закат»',
    size: '70×70',
    personal: 34,
    printed: 12,
    low: false,
  },
  {
    id: 'row-4',
    sku: 'DRS-LINEN-SUMMER-42',
    name: 'Платье льняное «Лето»',
    size: '42',
    personal: 0,
    printed: 6,
    low: false,
  },
]

export function HonestSignBackground({ onOpenImport }: Props): ReactNode {
  return (
    <div className="app-inner" aria-hidden={false}>
      <header className="app-bar" role="banner">
        <div className="app-bar-brand">
          <span className="app-bar-mark">SF</span>
          <span>SellerFocus WMS</span>
        </div>
        <nav className="app-bar-nav" aria-label="Основная навигация">
          <span className="app-bar-nav-item">Заказы</span>
          <span className="app-bar-nav-item">Каталог</span>
          <span className="app-bar-nav-item is-active">Честный знак</span>
          <span className="app-bar-nav-item">Ячейки</span>
          <span className="app-bar-nav-item">Расчёты</span>
        </nav>
        <div className="app-bar-user">
          <span>ФФ · Империя</span>
          <span className="app-bar-avatar">Д</span>
        </div>
      </header>

      <section className="page-header">
        <h1 className="page-title">Честный знак</h1>
        <p className="page-subtitle">
          Остатки кодов маркировки по товарам: личный запас и общие корзины на несколько SKU.
        </p>
      </section>

      <div className="kpi-row">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="paper kpi-card">
            <div className="kpi-label">{kpi.label}</div>
            <div className="kpi-value">{kpi.value}</div>
          </div>
        ))}
      </div>

      <div className="actions-row">
        <button type="button" className="btn btn-primary" onClick={onOpenImport}>
          <span aria-hidden>↥</span>
          Загрузить КМ
        </button>
        <button type="button" className="btn btn-outlined" disabled>
          Лента расхода
        </button>
        <button type="button" className="btn btn-outlined" disabled>
          Перепечатать ЧЗ
        </button>
      </div>

      <div className="paper paper-padded" style={{ marginBottom: 16 }}>
        <div className="row" style={{ gap: 12 }}>
          <div className="field-search" style={{ flex: 1, minWidth: 220 }}>
            <span className="field-search-icon" aria-hidden>
              🔍
            </span>
            <input className="input" placeholder="Артикул или название" disabled defaultValue="" />
          </div>
          <div className="row" style={{ gap: 4 }}>
            <span className="chip chip-outlined">Все</span>
            <span className="chip">На исходе</span>
            <span className="chip">Пустые</span>
          </div>
        </div>
      </div>

      <div className="paper table-wrap">
        <table className="wms-table">
          <thead>
            <tr>
              <th style={{ minWidth: 320 }}>Товар</th>
              <th className="col-num" style={{ minWidth: 132 }}>
                Личный остаток
              </th>
              <th style={{ minWidth: 160 }}>Общая корзина</th>
              <th className="col-num" style={{ minWidth: 110 }}>
                Напечатано
              </th>
              <th className="col-tight">Действия</th>
            </tr>
          </thead>
          <tbody>
            {backgroundRows.map((row) => (
              <tr key={row.id}>
                <td>
                  <div className="product-sku">{row.sku}</div>
                  <div className="product-name">{row.name}</div>
                  <div className="product-meta">Размер: {row.size}</div>
                </td>
                <td className="col-num" style={{ color: row.low ? 'var(--color-error)' : undefined, fontWeight: row.low ? 700 : 400 }}>
                  {row.personal}
                </td>
                <td>
                  {row.id === 'row-3' ? (
                    <span className="chip chip-outlined">🧺 22 · на 3 тов.</span>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </td>
                <td className="col-num">{row.printed}</td>
                <td className="col-tight">
                  <span className="text-muted">›</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
