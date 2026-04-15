import type { FormEventHandler } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'

type WarehouseRow = { id: string; name: string; code: string }
type LocationRow = { id: string; code: string; warehouse_id: string }
type SellerRow = { id: string; name: string }
type ProductRow = {
  id: string
  name: string
  sku_code: string
  volume_liters: number
  seller_id: string | null
  seller_name: string | null
  wb_nm_id?: number | null
  wb_vendor_code?: string | null
}

type WbImportedCardRow = {
  nm_id: number
  vendor_code: string | null
  title: string | null
  updated_at: string
}

type WbImportedSupplyRow = {
  external_key: string
  wb_supply_id: number | null
  wb_preorder_id: number | null
  status_id: number | null
  updated_at: string
}

type Props = {
  isFulfillmentAdmin: boolean
  catalogBusy: boolean
  catalogError: string | null
  sellers: SellerRow[]
  warehouses: WarehouseRow[]
  locations: LocationRow[]
  selectedWarehouseId: string | null
  setSelectedWarehouseId: (id: string) => void
  products: ProductRow[]

  onCreateWarehouse: FormEventHandler<HTMLFormElement>
  onCreateLocation: FormEventHandler<HTMLFormElement>
  onCreateSeller: FormEventHandler<HTMLFormElement>
  onCreateProduct: FormEventHandler<HTMLFormElement>

  // Wildberries
  wbSellerId: string | null
  setWbSellerId: (id: string) => void
  wbHasContentToken: boolean
  wbHasSuppliesToken: boolean
  wbTokensBusy: boolean
  wbSyncBusy: boolean
  wbSuppliesSyncBusy: boolean
  wbLinkBusy: boolean
  wbJobStatus: string | null
  wbJobResult: string | null
  wbSuppliesJobStatus: string | null
  wbSuppliesJobResult: string | null
  wbImportedCards: WbImportedCardRow[]
  wbImportedSupplies: WbImportedSupplyRow[]

  onSaveWbTokens: FormEventHandler<HTMLFormElement>
  onStartWbCardsSyncJob: () => void
  onStartWbSuppliesSyncJob: () => void
  onLinkProductToWb: FormEventHandler<HTMLFormElement>
}

export function CatalogSection(props: Props) {
  const {
    isFulfillmentAdmin,
    catalogBusy,
    catalogError,
    sellers,
    warehouses,
    locations,
    selectedWarehouseId,
    setSelectedWarehouseId,
    products,
    onCreateWarehouse,
    onCreateLocation,
    onCreateSeller,
    onCreateProduct,
    wbSellerId,
    setWbSellerId,
    wbHasContentToken,
    wbHasSuppliesToken,
    wbTokensBusy,
    wbSyncBusy,
    wbSuppliesSyncBusy,
    wbLinkBusy,
    wbJobStatus,
    wbJobResult,
    wbSuppliesJobStatus,
    wbSuppliesJobResult,
    wbImportedCards,
    wbImportedSupplies,
    onSaveWbTokens,
    onStartWbCardsSyncJob,
    onStartWbSuppliesSyncJob,
    onLinkProductToWb,
  } = props

  return (
    <div id="catalog-section" className="stack" data-testid="catalog-section">
      {catalogError ? (
        <p className="error" data-testid="catalog-error">
          {catalogError}
        </p>
      ) : null}

      {!isFulfillmentAdmin ? (
        <p className="subtle" data-testid="seller-cabinet-notice">
          Режим селлера: доступны ваши SKU, заявки с вашими товарами и журнал
          движений. Управление складом — у фулфилмента.
        </p>
      ) : null}

      {isFulfillmentAdmin ? (
        <Card className="card">
          <h2>Склады</h2>
          <p className="subtle">Код склада — латиница, цифры, символы _ и -.</p>
          <form data-testid="warehouse-form" noValidate onSubmit={onCreateWarehouse}>
            <label>
              Название
              <Input name="warehouse_name" data-testid="warehouse-name" required />
            </label>
            <label>
              Код
              <Input
                name="warehouse_code"
                data-testid="warehouse-code"
                required
                autoComplete="off"
              />
            </label>
            <Button
              type="submit"
              data-testid="warehouse-submit"
              disabled={catalogBusy}
            >
              {catalogBusy ? '…' : 'Добавить склад'}
            </Button>
          </form>
          <ul className="list-plain" data-testid="warehouse-list">
            {warehouses.map((w) => (
              <li key={w.id}>
                <Button
                  type="button"
                  variant="ghost"
                  className="list-row-button"
                  data-testid="warehouse-item"
                  data-selected={w.id === selectedWarehouseId ? 'true' : 'false'}
                  onClick={() => setSelectedWarehouseId(w.id)}
                >
                  <strong>{w.name}</strong>{' '}
                  <span className="subtle" style={{ margin: 0 }}>
                    ({w.code})
                  </span>
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {isFulfillmentAdmin ? (
        <Card className="card">
          <h2>Ячейки</h2>
          {!selectedWarehouseId ? (
            <p className="subtle">Сначала создайте склад.</p>
          ) : (
            <form data-testid="location-form" noValidate onSubmit={onCreateLocation}>
              <label>
                Код ячейки
                <Input
                  name="location_code"
                  data-testid="location-code"
                  required
                  autoComplete="off"
                />
              </label>
              <Button
                type="submit"
                data-testid="location-submit"
                disabled={catalogBusy}
              >
                {catalogBusy ? '…' : 'Добавить ячейку'}
              </Button>
            </form>
          )}
          <ul className="list-plain" data-testid="location-list">
            {locations.map((loc) => (
              <li key={loc.id} data-testid="location-item">
                {loc.code}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card className="card" data-testid="sellers-section">
        <h2>Селлеры</h2>
        <p className="subtle">
          Клиенты фулфилмента; можно привязать к SKU при создании товара.
        </p>
        {isFulfillmentAdmin ? (
          <form data-testid="seller-form" noValidate onSubmit={onCreateSeller}>
            <label>
              Название селлера
              <Input
                name="seller_name"
                data-testid="seller-name"
                required
                autoComplete="off"
              />
            </label>
            <Button
              type="submit"
              data-testid="seller-submit"
              disabled={catalogBusy}
            >
              {catalogBusy ? '…' : 'Добавить селлера'}
            </Button>
          </form>
        ) : null}
        <ul className="list-plain" data-testid="seller-list">
          {sellers.map((s) => (
            <li key={s.id} data-testid="seller-item">
              {s.name}
            </li>
          ))}
        </ul>
      </Card>

      {isFulfillmentAdmin && sellers.length > 0 && wbSellerId ? (
        <Card className="card" data-testid="wildberries-integration-section">
          <h2>Wildberries (импорт)</h2>
          <p className="subtle">
            Токены хранятся зашифрованно. Синхронизация — только чтение: карточки
            (первая страница) и список поставок FBW (первая страница), без записи
            в WB.
          </p>
          <label>
            Селлер для интеграции
            <Select
              data-testid="wb-seller-select"
              value={wbSellerId}
              onChange={(ev) => setWbSellerId(ev.target.value)}
            >
              {sellers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </label>
          <p className="subtle" data-testid="wb-token-flags">
            Контент API: {wbHasContentToken ? 'токен есть' : 'нет токена'} ·
            Поставки API: {wbHasSuppliesToken ? 'токен есть' : 'нет токена'}
          </p>
          <form data-testid="wb-tokens-form" noValidate onSubmit={onSaveWbTokens}>
            <label>
              Токен контента WB
              <Input
                name="wb_content_token"
                data-testid="wb-content-token"
                type="password"
                autoComplete="off"
                placeholder="вставьте токен категории «Контент»"
              />
            </label>
            <label>
              Токен поставок WB (необязательно)
              <Input
                name="wb_supplies_token"
                data-testid="wb-supplies-token"
                type="password"
                autoComplete="off"
                placeholder="для импорта поставок FBW (первая страница)"
              />
            </label>
            <Button type="submit" data-testid="wb-save-tokens" disabled={wbTokensBusy}>
              {wbTokensBusy ? '…' : 'Сохранить токены'}
            </Button>
          </form>
          <Button
            type="button"
            data-testid="wb-sync-cards"
            disabled={wbSyncBusy || !wbHasContentToken}
            onClick={onStartWbCardsSyncJob}
          >
            {wbSyncBusy ? '…' : 'Обновить карточки из WB'}
          </Button>
          <p className="subtle" data-testid="wb-sync-status">
            Синхронизация: {wbJobStatus ?? '—'}
          </p>
          {wbJobResult ? <p data-testid="wb-sync-result">{wbJobResult}</p> : null}
          <Button
            type="button"
            variant="secondary"
            data-testid="wb-sync-supplies"
            disabled={wbSuppliesSyncBusy || !wbHasSuppliesToken}
            onClick={onStartWbSuppliesSyncJob}
          >
            {wbSuppliesSyncBusy ? '…' : 'Обновить поставки из WB'}
          </Button>
          <p className="subtle" data-testid="wb-supplies-sync-status">
            Синхронизация поставок: {wbSuppliesJobStatus ?? '—'}
          </p>
          {wbSuppliesJobResult ? (
            <p data-testid="wb-supplies-sync-result">{wbSuppliesJobResult}</p>
          ) : null}

          <h3 className="subtle" style={{ marginTop: 16 }}>
            Импортированные карточки
          </h3>
          {wbImportedCards.length === 0 ? (
            <p className="subtle" data-testid="wb-imported-cards-empty">
              Пока нет — выполните синхронизацию.
            </p>
          ) : (
            <ul className="list-plain" data-testid="wb-imported-cards-list">
              {wbImportedCards.map((c) => (
                <li key={String(c.nm_id)} data-testid="wb-imported-card-item">
                  nmID {c.nm_id}
                  {c.vendor_code ? ` · ${c.vendor_code}` : ''}
                </li>
              ))}
            </ul>
          )}

          <h3 className="subtle" style={{ marginTop: 16 }}>
            Импортированные поставки
          </h3>
          {wbImportedSupplies.length === 0 ? (
            <p className="subtle" data-testid="wb-imported-supplies-empty">
              Пока нет — сохраните токен поставок и выполните синхронизацию.
            </p>
          ) : (
            <ul className="list-plain" data-testid="wb-imported-supplies-list">
              {wbImportedSupplies.map((s) => (
                <li key={s.external_key} data-testid="wb-imported-supply-item">
                  {s.wb_supply_id != null ? `supply ${s.wb_supply_id}` : ''}
                  {s.wb_supply_id != null && s.wb_preorder_id != null ? ' · ' : ''}
                  {s.wb_preorder_id != null ? `preorder ${s.wb_preorder_id}` : ''}
                  {s.status_id != null ? ` · статус ${s.status_id}` : ''}
                </li>
              ))}
            </ul>
          )}

          <h3 className="subtle" style={{ marginTop: 16 }}>
            Привязка SKU к карточке WB
          </h3>
          <p className="subtle">
            Товар должен быть привязан к тому же селлеру, что выбран выше; nm_id —
            из списка импортированных карточек.
          </p>
          <form data-testid="wb-link-product-form" noValidate onSubmit={onLinkProductToWb}>
            <label>
              Товар
              <Select
                name="wb_link_product_id"
                data-testid="wb-link-product-id"
                required
                defaultValue=""
              >
                <option value="" disabled>
                  — выберите —
                </option>
                {products
                  .filter((p) => p.seller_id === wbSellerId)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku_code} — {p.name}
                    </option>
                  ))}
              </Select>
            </label>
            <label>
              nm_id (WB)
              <Input
                name="wb_link_nm_id"
                data-testid="wb-link-nm-id"
                type="number"
                min={1}
                required
                autoComplete="off"
              />
            </label>
            <Button type="submit" data-testid="wb-link-submit" disabled={wbLinkBusy}>
              {wbLinkBusy ? '…' : 'Привязать'}
            </Button>
          </form>
        </Card>
      ) : null}

      <Card className="card">
        <h2>Товары (SKU)</h2>
        {isFulfillmentAdmin ? (
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
        ) : null}
        <ul className="list-plain" data-testid="product-list">
          {products.map((p) => (
            <li key={p.id} data-testid="product-item" data-product-id={p.id}>
              <strong>{p.name}</strong> — {p.sku_code},{' '}
              <span data-testid="product-volume">{p.volume_liters.toFixed(1)} л</span>
              {p.seller_name ? (
                <span data-testid="product-seller-name"> · селлер: {p.seller_name}</span>
              ) : null}
              {p.wb_nm_id != null ? (
                <span data-testid="product-wb-nm">
                  {' '}
                  · WB nmID {p.wb_nm_id}
                  {p.wb_vendor_code ? ` (${p.wb_vendor_code})` : ''}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

