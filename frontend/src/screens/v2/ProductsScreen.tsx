import { useMemo, useState } from 'react'
import type { FormEventHandler } from 'react'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Input } from '../../ui/Input'
import { Select } from '../../ui/Select'
import { Screen } from '../AppV2Screens'

type SellerRow = { id: string; name: string }

type ProductRow = {
  id: string
  name: string
  sku_code: string
  length_mm: number
  width_mm: number
  height_mm: number
  volume_liters: number
  seller_id: string | null
  seller_name: string | null
  wb_nm_id?: number | null
  wb_vendor_code?: string | null
}

type Props = {
  isFulfillmentAdmin: boolean
  catalogBusy: boolean
  catalogError: string | null
  sellers: SellerRow[]
  products: ProductRow[]
  onCreateProduct: FormEventHandler<HTMLFormElement>
}

export function ProductsScreen({
  isFulfillmentAdmin,
  catalogBusy,
  catalogError,
  sellers,
  products,
  onCreateProduct,
}: Props) {
  const [q, setQ] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) {
      return products
    }
    return products.filter((p) => {
      const hay = `${p.name} ${p.sku_code} ${p.seller_name ?? ''} ${p.wb_vendor_code ?? ''}`.toLowerCase()
      return hay.includes(s)
    })
  }, [products, q])

  const selected = useMemo(
    () => (selectedId ? products.find((p) => p.id === selectedId) ?? null : null),
    [products, selectedId],
  )

  return (
    <Screen title="Товары (SKU)" subtitle="Таблица SKU, детали, создание и привязки">
      {catalogError ? (
        <Card className="card">
          <p className="error" data-testid="catalog-error">
            {catalogError}
          </p>
        </Card>
      ) : null}

      <div className="screen-grid">
        <div className="stack">
          <Card className="card">
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <div style={{ flex: 1 }}>
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Поиск по названию, SKU, селлеру, WB…"
                  aria-label="Поиск SKU"
                />
              </div>
              <div className="ui-badge" aria-label="Количество результатов">
                {filtered.length}
              </div>
            </div>
          </Card>

          <table className="ui-table" data-testid="product-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Название</th>
                <th>Объём</th>
                <th>Селлер</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr
                  key={p.id}
                  data-selected={p.id === selectedId ? 'true' : 'false'}
                  onClick={() => setSelectedId(p.id)}
                  data-testid="product-item"
                  data-product-id={p.id}
                >
                  <td data-testid="product-sku-cell">{p.sku_code}</td>
                  <td>{p.name}</td>
                  <td>
                    <span data-testid="product-volume">{p.volume_liters.toFixed(1)} л</span>
                  </td>
                  <td>
                    {p.seller_name ? (
                      <span data-testid="product-seller-name">{p.seller_name}</span>
                    ) : (
                      <span className="subtle">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <span className="subtle">Ничего не найдено.</span>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="stack">
          <Card className="card">
            <h3 style={{ margin: 0, fontSize: 16 }}>Детали SKU</h3>
            {selected ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div>
                  <div style={{ fontWeight: 650, color: 'var(--text-h)' }}>{selected.name}</div>
                  <div className="subtle" style={{ margin: 0 }}>
                    {selected.sku_code}
                    {selected.wb_nm_id != null ? (
                      <span data-testid="product-wb-nm">
                        {' '}
                        · WB nmID {selected.wb_nm_id}
                        {selected.wb_vendor_code ? ` (${selected.wb_vendor_code})` : ''}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="ui-badge">
                  {selected.length_mm}×{selected.width_mm}×{selected.height_mm} мм ·{' '}
                  {selected.volume_liters.toFixed(2)} л
                </div>
              </div>
            ) : (
              <p className="subtle">Выбери строку в таблице слева.</p>
            )}
          </Card>

          {isFulfillmentAdmin ? (
            <Card className="card">
              <h3 style={{ margin: 0, fontSize: 16 }}>Создать SKU</h3>
              <form data-testid="product-form" noValidate onSubmit={onCreateProduct}>
                <label>
                  Название
                  <Input name="product_name" data-testid="product-name" required />
                </label>
                <label>
                  SKU
                  <Input
                    name="product_sku"
                    data-testid="product-sku"
                    required
                    autoComplete="off"
                  />
                </label>
                <div className="grid2">
                  <label>
                    Длина, мм
                    <Input
                      name="product_length_mm"
                      data-testid="product-length-mm"
                      type="number"
                      min={1}
                      required
                    />
                  </label>
                  <label>
                    Ширина, мм
                    <Input
                      name="product_width_mm"
                      data-testid="product-width-mm"
                      type="number"
                      min={1}
                      required
                    />
                  </label>
                </div>
                <label>
                  Высота, мм
                  <Input
                    name="product_height_mm"
                    data-testid="product-height-mm"
                    type="number"
                    min={1}
                    required
                  />
                </label>
                {sellers.length > 0 ? (
                  <label>
                    Селлер (необязательно)
                    <Select name="product_seller_id" data-testid="product-seller" defaultValue="">
                      <option value="">— нет —</option>
                      {sellers.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </Select>
                  </label>
                ) : null}
                <Button type="submit" data-testid="product-submit" disabled={catalogBusy}>
                  {catalogBusy ? '…' : 'Добавить товар'}
                </Button>
              </form>
            </Card>
          ) : null}
        </div>
      </div>
    </Screen>
  )
}

