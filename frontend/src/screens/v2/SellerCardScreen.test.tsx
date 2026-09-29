import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { SellerCardScreen, SellerRequisitesBlock, type SellerCardRow } from './SellerCardScreen'

const authHeaders = () => ({ Authorization: 'Bearer test-token' })

function renderCard(sellers: SellerCardRow[], sellerId = 'seller-a') {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[`/app/ff/sellers/${sellerId}`]}>
      <Routes>
        <Route
          path="/app/ff/sellers/:sellerId"
          element={<SellerCardScreen token="test-token" authHeaders={authHeaders} sellers={sellers} />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SellerRequisitesBlock', () => {
  it('shows "Не заполнены" when there is no profile', () => {
    const markup = renderToStaticMarkup(<SellerRequisitesBlock profile={null} />)
    expect(markup).toContain('Не заполнены')
    expect(markup).toContain('seller-card-requisites-empty')
  })

  it('lists the same field labels as an opened invoice profile snapshot', () => {
    const markup = renderToStaticMarkup(
      <SellerRequisitesBlock
        profile={{
          legal_name: 'ООО Восход',
          inn: '7700000000',
          kpp: '770001001',
          bank_name: 'Банк',
          bik: '044525225',
          settlement_account: '40702810000000000001',
          correspondent_account: '30101810000000000225',
        }}
      />,
    )
    expect(markup).toContain('Юридическое наименование: ООО Восход')
    expect(markup).toContain('ИНН: 7700000000')
    expect(markup).toContain('КПП: 770001001')
    expect(markup).toContain('Название банка: Банк')
    expect(markup).toContain('БИК: 044525225')
    expect(markup).toContain('Расчётный счёт: 40702810000000000001')
    expect(markup).toContain('Корреспондентский счёт: 30101810000000000225')
  })
})

describe('SellerCardScreen', () => {
  const seller: SellerCardRow = {
    id: 'seller-a',
    name: 'ООО Восход',
    wb_has_key: false,
    wb_marketplace_scope_ok: null,
    ozon_connected: true,
  }

  it('shows the seller name and the same WB/Ozon status text as the list, plus its action buttons', () => {
    const markup = renderCard([seller])
    expect(markup).toContain('ООО Восход')
    expect(markup).toContain('WB Marketplace: Ключа нет')
    expect(markup).toContain('Ozon: Подключён')
    expect(markup).toContain('data-testid="seller-card-open-products"')
    expect(markup).toContain(`/app/ff/products?seller_id=${seller.id}`)
    expect(markup).toContain('data-testid="seller-card-open-billing"')
    expect(markup).toContain(`/app/ff/billing?seller_id=${seller.id}`)
    // Реквизиты — та же кнопка/окно, что раньше жили в строке списка «Селлеры».
    expect(markup).toContain('billing-profiles-open')
  })

  it('never renders a products list, checkboxes or "Не отображать" — owner cancelled those in the same dictation', () => {
    const markup = renderCard([seller])
    expect(markup).not.toContain('Не отображать')
    expect(markup).not.toContain('type="checkbox"')
  })

  it('shows "Селлер не найден." when the seller list is already loaded and does not contain this id', () => {
    const markup = renderCard([{ id: 'other-seller', name: 'Другой селлер' }], 'seller-a')
    expect(markup).toContain('seller-card-not-found')
    expect(markup).toContain('Селлер не найден.')
    expect(markup).not.toContain('seller-card-open-products')
    expect(markup).not.toContain('seller-card-requisites')
  })
})
