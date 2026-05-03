import type { FormEventHandler } from 'react'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Input } from '../../ui/Input'
import { Select } from '../../ui/Select'
import { Screen } from '../AppV2Screens'

type SellerRow = { id: string; name: string }
type ProductRow = { id: string; name: string; sku_code: string; seller_id: string | null }

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
  sellers: SellerRow[]
  products: ProductRow[]

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

export function WildberriesScreen(props: Props) {
  const {
    sellers,
    products,
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
    <Screen title="Wildberries" subtitle="Импорт карточек/поставок и привязка SKU (read-only)">
      <div className="screen-grid">
        <div className="stack">
          <Card className="card" data-testid="wildberries-integration-section">
            <h3 style={{ margin: 0, fontSize: 16 }}>Интеграция</h3>
            <p className="subtle">
              Токены хранятся зашифрованно. Синхронизация — только чтение: карточки (первая
              страница) и список поставок FBW (первая страница), без записи в WB.
            </p>

            {sellers.length > 0 && wbSellerId ? (
              <>
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
                  Контент API: {wbHasContentToken ? 'токен есть' : 'нет токена'} · Поставки API:{' '}
                  {wbHasSuppliesToken ? 'токен есть' : 'нет токена'}
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

                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <Button
                    type="button"
                    data-testid="wb-sync-cards"
                    disabled={wbSyncBusy || !wbHasContentToken}
                    onClick={onStartWbCardsSyncJob}
                  >
                    {wbSyncBusy ? '…' : 'Обновить карточки'}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    data-testid="wb-sync-supplies"
                    disabled={wbSuppliesSyncBusy || !wbHasSuppliesToken}
                    onClick={onStartWbSuppliesSyncJob}
                  >
                    {wbSuppliesSyncBusy ? '…' : 'Обновить поставки'}
                  </Button>
                </div>

                <p className="subtle" data-testid="wb-sync-status">
                  Синхронизация: {wbJobStatus ?? '—'}
                </p>
                {wbJobResult ? <p data-testid="wb-sync-result">{wbJobResult}</p> : null}
                <p className="subtle" data-testid="wb-supplies-sync-status">
                  Синхронизация поставок: {wbSuppliesJobStatus ?? '—'}
                </p>
                {wbSuppliesJobResult ? (
                  <p data-testid="wb-supplies-sync-result">{wbSuppliesJobResult}</p>
                ) : null}
              </>
            ) : (
              <p className="subtle">Нужен хотя бы один селлер.</p>
            )}
          </Card>

          <Card className="card">
            <h3 className="subtle" style={{ marginTop: 0 }}>
              Привязка SKU к карточке WB
            </h3>
            <p className="subtle">
              Товар должен быть привязан к тому же селлеру, что выбран выше; nm_id — из списка
              импортированных карточек.
            </p>

            <form data-testid="wb-link-product-form" noValidate onSubmit={onLinkProductToWb}>
              <label>
                Товар
                <Select
                  name="wb_link_product_id"
                  data-testid="wb-link-product-id"
                  required
                  defaultValue=""
                  disabled={!wbSellerId}
                >
                  <option value="" disabled>
                    — выберите —
                  </option>
                  {wbSellerId
                    ? products
                        .filter((p) => p.seller_id === wbSellerId)
                        .map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.sku_code} — {p.name}
                          </option>
                        ))
                    : null}
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
              <Button type="submit" data-testid="wb-link-submit" disabled={wbLinkBusy || !wbSellerId}>
                {wbLinkBusy ? '…' : 'Привязать'}
              </Button>
            </form>
          </Card>
        </div>

        <div className="stack">
          <Card className="card">
            <h3 className="subtle" style={{ marginTop: 0 }}>
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
          </Card>

          <Card className="card">
            <h3 className="subtle" style={{ marginTop: 0 }}>
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
          </Card>
        </div>
      </div>
    </Screen>
  )
}

