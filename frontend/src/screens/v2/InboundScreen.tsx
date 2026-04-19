import { useMemo, useState } from 'react'
import type { FormEventHandler } from 'react'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Input } from '../../ui/Input'
import { Select } from '../../ui/Select'
import { Screen } from '../AppV2Screens'

type WarehouseRow = { id: string; name: string; code: string }
type LocationRow = { id: string; code: string; warehouse_id: string }
type ProductRow = { id: string; name: string; sku_code: string }

type InboundSummaryRow = {
  id: string
  warehouse_id: string
  status: string
  line_count: number
  planned_delivery_date: string | null
  has_discrepancy?: boolean
}

type InboundLineRow = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  expected_qty: number
  actual_qty: number | null
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type InboundDetailRow = {
  id: string
  warehouse_id: string
  status: string
  planned_delivery_date: string | null
  has_discrepancy?: boolean
  lines: InboundLineRow[]
}

type InboundMovementRow = {
  id: string
  quantity_delta: number
  movement_type: string
}

type PostedInventoryBalanceRow = {
  product_id: string
  sku_code: string
  quantity: number
  reserved: number
  available: number
}

type Props = {
  opsError: string | null
  opsBusy: boolean
  isFulfillmentAdmin: boolean
  isFulfillmentSeller: boolean
  canEditInboundDraft: boolean

  warehouses: WarehouseRow[]
  selectedWarehouseId: string | null
  products: ProductRow[]

  inboundSummaries: InboundSummaryRow[]
  selectedInboundId: string | null
  setSelectedInboundId: (id: string) => void
  inboundDetail: InboundDetailRow | null
  inboundRequestLocations: LocationRow[]
  inboundMovements: InboundMovementRow[]
  postedInventoryRows: PostedInventoryBalanceRow[]

  onCreateInboundRequest: FormEventHandler<HTMLFormElement>
  onAddInboundLine: FormEventHandler<HTMLFormElement>
  onSubmitInboundRequest: () => void
  onPrimaryAcceptInboundRequest: () => void
  onSetInboundLineActualQty: FormEventHandler<HTMLFormElement>
  onCompleteInboundVerification: () => void
  onSaveInboundLineStorage: FormEventHandler<HTMLFormElement>
  onReceiveInboundLine: FormEventHandler<HTMLFormElement>
  onPostInboundRequest: () => void
}

export function InboundScreen(props: Props) {
  const {
    opsError,
    opsBusy,
    isFulfillmentAdmin,
    isFulfillmentSeller,
    canEditInboundDraft,
    warehouses,
    selectedWarehouseId,
    products,
    inboundSummaries,
    selectedInboundId,
    setSelectedInboundId,
    inboundDetail,
    inboundRequestLocations,
    inboundMovements,
    postedInventoryRows,
    onCreateInboundRequest,
    onAddInboundLine,
    onSubmitInboundRequest,
    onPrimaryAcceptInboundRequest,
    onSetInboundLineActualQty,
    onCompleteInboundVerification,
    onSaveInboundLineStorage,
    onReceiveInboundLine,
    onPostInboundRequest,
  } = props

  const todayIso = new Date().toISOString().slice(0, 10)
  const [productQuery, setProductQuery] = useState('')

  const filteredProducts = useMemo(() => {
    const q = productQuery.trim().toLowerCase()
    if (!q) {
      return products
    }
    return products.filter((p) => {
      const anyP = p as unknown as {
        seller_name?: string | null
        wb_vendor_code?: string | null
        wb_nm_id?: number | null
      }
      const hay =
        `${p.sku_code} ${p.name} ${anyP.seller_name ?? ''} ${anyP.wb_vendor_code ?? ''} ${anyP.wb_nm_id ?? ''}`.toLowerCase()
      return hay.includes(q)
    })
  }, [productQuery, products])

  return (
    <Screen title="Приёмка" subtitle="Список заявок → детали → приём по строкам">
      {opsError ? (
        <Card className="card">
          <p className="error" data-testid="operations-error">
            {opsError}
          </p>
        </Card>
      ) : null}

      <div className="screen-grid">
        <div className="stack">
          <Card className="card">
            <h3 style={{ margin: 0, fontSize: 16 }}>Заявки на приёмку</h3>
            <p className="subtle">
              Создай заявку, добавь строки, отправь. В статусе submitted — приёмка по строкам.
            </p>

            {canEditInboundDraft ? (
              <form data-testid="inbound-create-form" noValidate onSubmit={onCreateInboundRequest}>
                <label>
                  Дата привоза (план)
                  <Input
                    name="inbound_planned_delivery_date"
                    data-testid="inbound-create-planned-date"
                    type="date"
                    required
                    defaultValue={todayIso}
                  />
                </label>
                {isFulfillmentSeller && warehouses.length > 1 ? (
                  <label>
                    Склад для заявки
                    <Select
                      name="inbound_warehouse_id"
                      data-testid="inbound-create-warehouse"
                      required
                      defaultValue=""
                    >
                      <option value="" disabled>
                        Выберите склад
                      </option>
                      {warehouses.map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.code} — {w.name}
                        </option>
                      ))}
                    </Select>
                  </label>
                ) : null}
                <Button
                  type="submit"
                  data-testid="inbound-create-submit"
                  disabled={
                    opsBusy ||
                    warehouses.length === 0 ||
                    (!isFulfillmentSeller && !selectedWarehouseId && warehouses.length !== 1)
                  }
                >
                  {opsBusy ? '…' : 'Новая заявка на приёмку'}
                </Button>
              </form>
            ) : null}

            <div data-testid="inbound-requests-list">
              <table className="ui-table" data-testid="inbound-requests-table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Статус</th>
                  <th>Строк</th>
                </tr>
              </thead>
              <tbody>
                {inboundSummaries.map((row) => (
                  <tr
                    key={row.id}
                    data-selected={row.id === selectedInboundId ? 'true' : 'false'}
                    onClick={() => setSelectedInboundId(row.id)}
                    data-testid="inbound-request-item"
                    data-status={row.status}
                  >
                    <td>
                      <span className="subtle" data-testid="inbound-request-date">
                        {row.planned_delivery_date ?? '—'}
                      </span>
                    </td>
                    <td>
                      <span className="ui-badge" data-testid="inbound-request-status">
                        {row.status}
                      </span>
                    </td>
                    <td>{row.line_count}</td>
                  </tr>
                ))}
                {inboundSummaries.length === 0 ? (
                  <tr>
                    <td colSpan={3}>
                      <span className="subtle">Пока нет заявок.</span>
                    </td>
                  </tr>
                ) : null}
              </tbody>
              </table>
            </div>
          </Card>
        </div>

        <div className="stack">
          <Card className="card">
            <h3 style={{ margin: 0, fontSize: 16 }}>Детали заявки</h3>
            {!inboundDetail ? (
              <p className="subtle" data-testid="inbound-detail">
                Выбери заявку слева.
              </p>
            ) : (
              <div data-testid="inbound-detail">
                <p className="subtle" data-testid="inbound-detail-status">
                  Статус: {inboundDetail.status}
                </p>
                <p className="subtle" data-testid="inbound-detail-planned-date">
                  Дата привоза (план): {inboundDetail.planned_delivery_date ?? '—'}
                </p>

                <ul className="list-plain" data-testid="inbound-detail-lines">
                  {inboundDetail.lines.map((ln) => (
                    <li key={ln.id} data-testid="inbound-detail-line">
                      {ln.product_name} ({ln.sku_code}) — план {ln.expected_qty}
                      {typeof ln.actual_qty === 'number' ? ` · факт ${ln.actual_qty}` : ''}
                      {' · '}
                      принято {ln.posted_qty}
                      {ln.storage_location_code ? ` · ячейка: ${ln.storage_location_code}` : ''}
                    </li>
                  ))}
                </ul>

                {inboundDetail.status === 'draft' && canEditInboundDraft ? (
                  <form data-testid="inbound-line-form" noValidate onSubmit={onAddInboundLine}>
                    <label>
                      Поиск SKU
                      <Input
                        value={productQuery}
                        onChange={(e) => setProductQuery(e.target.value)}
                        placeholder="Введи SKU или часть названия…"
                        aria-label="Поиск SKU для приёмки"
                        data-testid="inbound-line-product-search"
                      />
                    </label>
                    <label>
                      Товар
                      <Select
                        name="inbound_product_id"
                        data-testid="inbound-line-product"
                        required
                        defaultValue=""
                      >
                        <option value="" disabled>
                          Выберите SKU
                        </option>
                        {filteredProducts.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.sku_code} — {p.name}
                          </option>
                        ))}
                      </Select>
                    </label>
                    <label>
                      Количество, шт
                      <Input
                        name="inbound_qty"
                        data-testid="inbound-line-qty"
                        type="number"
                        min={1}
                        required
                      />
                    </label>
                    {inboundRequestLocations.length > 0 ? (
                      <label>
                        Ячейка (необязательно)
                        <Select
                          name="inbound_line_storage_id"
                          data-testid="inbound-line-location"
                          defaultValue=""
                        >
                          <option value="">— позже —</option>
                          {inboundRequestLocations.map((loc) => (
                            <option key={loc.id} value={loc.id}>
                              {loc.code}
                            </option>
                          ))}
                        </Select>
                      </label>
                    ) : null}
                    <Button
                      type="submit"
                      data-testid="inbound-line-submit"
                      disabled={opsBusy || products.length === 0}
                    >
                      {opsBusy ? '…' : 'Добавить строку'}
                    </Button>
                  </form>
                ) : null}

                {inboundDetail.status === 'draft' &&
                inboundDetail.lines.length > 0 &&
                (isFulfillmentAdmin || isFulfillmentSeller) ? (
                  <Button
                    type="button"
                    data-testid="inbound-submit-request"
                    disabled={opsBusy}
                    onClick={onSubmitInboundRequest}
                  >
                    {opsBusy ? '…' : 'Отправить заявку'}
                  </Button>
                ) : null}

                {inboundDetail.status === 'submitted' ? (
                  <div data-testid="inbound-primary-accept-panel">
                    {isFulfillmentAdmin ? (
                      <>
                        <p className="subtle">Привоз принят без пересчёта.</p>
                        <Button
                          type="button"
                          data-testid="inbound-primary-accept"
                          disabled={opsBusy}
                          onClick={onPrimaryAcceptInboundRequest}
                        >
                          {opsBusy ? '…' : 'Принято первично'}
                        </Button>
                      </>
                    ) : (
                      <p className="subtle" data-testid="inbound-seller-read-only">
                        Ожидает первичной приёмки фулфилментом.
                      </p>
                    )}
                  </div>
                ) : null}

                {inboundDetail.status === 'primary_accepted' || inboundDetail.status === 'verifying' ? (
                  <div data-testid="inbound-verify-panel">
                    {isFulfillmentAdmin ? (
                      <>
                        <p className="subtle">Пересчёт: укажи факт по строкам.</p>
                        {inboundDetail.lines.map((ln) => (
                          <Card
                            key={ln.id}
                            as="div"
                            className="card"
                            style={{ marginBottom: 10 }}
                            data-testid="inbound-verify-line"
                          >
                            <p className="subtle" style={{ marginTop: 0 }}>
                              {ln.sku_code} — план {ln.expected_qty}
                            </p>
                            <form
                              data-testid="inbound-line-actual-form"
                              data-line-id={ln.id}
                              noValidate
                              onSubmit={onSetInboundLineActualQty}
                            >
                              <label>
                                Факт, шт
                                <Input
                                  name="actual_qty"
                                  data-testid="inbound-line-actual-qty"
                                  type="number"
                                  min={0}
                                  required
                                  defaultValue={String(ln.actual_qty ?? ln.expected_qty)}
                                />
                              </label>
                              <Button
                                type="submit"
                                data-testid="inbound-line-actual-save"
                                disabled={opsBusy}
                              >
                                Сохранить факт
                              </Button>
                            </form>
                          </Card>
                        ))}
                        <Button
                          type="button"
                          data-testid="inbound-verify-complete"
                          disabled={opsBusy}
                          onClick={onCompleteInboundVerification}
                        >
                          {opsBusy ? '…' : 'Завершить пересчёт'}
                        </Button>
                      </>
                    ) : (
                      <p className="subtle" data-testid="inbound-seller-read-only">
                        Идёт пересчёт на фулфилменте; доступен просмотр.
                      </p>
                    )}
                  </div>
                ) : null}

                {inboundDetail.status === 'verified' ? (
                  <div data-testid="inbound-receiving-panel">
                    {inboundDetail.has_discrepancy ? (
                      <p className="error" data-testid="inbound-discrepancy-flag">
                        Есть расхождения (план ≠ факт)
                      </p>
                    ) : (
                      <p className="subtle">Факт подтверждён, можно проводить остатки.</p>
                    )}
                    {isFulfillmentAdmin ? (
                      <>
                        {inboundDetail.lines.map((ln) => {
                          const target = ln.actual_qty ?? ln.expected_qty
                          const remaining = target - ln.posted_qty
                          return remaining > 0 ? (
                            <Card
                              key={ln.id}
                              as="div"
                              className="card"
                              style={{ marginBottom: 10 }}
                            >
                              <p className="subtle" style={{ marginTop: 0 }}>
                                {ln.sku_code} — осталось {remaining} из {target}
                              </p>
                              <form
                                data-testid="inbound-line-storage-form"
                                data-line-id={ln.id}
                                noValidate
                                onSubmit={onSaveInboundLineStorage}
                              >
                                <label>
                                  Ячейка
                                  <Select
                                    name="line_storage_id"
                                    data-testid="inbound-line-storage-select"
                                    defaultValue={ln.storage_location_id ?? ''}
                                    required
                                  >
                                    <option value="" disabled>
                                      Выберите ячейку
                                    </option>
                                    {inboundRequestLocations.map((loc) => (
                                      <option key={loc.id} value={loc.id}>
                                        {loc.code}
                                      </option>
                                    ))}
                                  </Select>
                                </label>
                                <Button
                                  type="submit"
                                  data-testid="inbound-line-storage-save"
                                  disabled={opsBusy || inboundRequestLocations.length === 0}
                                >
                                  Сохранить ячейку
                                </Button>
                              </form>
                              <form
                                data-testid="inbound-line-receive-form"
                                data-line-id={ln.id}
                                noValidate
                                onSubmit={onReceiveInboundLine}
                              >
                                <label>
                                  Принять, шт
                                  <Input
                                    name="receive_qty"
                                    data-testid="inbound-line-receive-qty"
                                    type="number"
                                    min={1}
                                    max={remaining}
                                    required
                                  />
                                </label>
                                <Button
                                  type="submit"
                                  data-testid="inbound-line-receive-submit"
                                  disabled={opsBusy}
                                >
                                  Принять
                                </Button>
                              </form>
                            </Card>
                          ) : null
                        })}
                        <Button
                          type="button"
                          data-testid="inbound-post-submit"
                          disabled={opsBusy}
                          onClick={onPostInboundRequest}
                        >
                          {opsBusy ? '…' : 'Провести весь остаток'}
                        </Button>
                      </>
                    ) : (
                      <p className="subtle" data-testid="inbound-seller-read-only">
                        Проведение остатков выполняет фулфилмент; доступен просмотр.
                      </p>
                    )}
                  </div>
                ) : null}

                {inboundMovements.length > 0 ? (
                  <div data-testid="inbound-movements-block">
                    <p className="subtle">Журнал движений по заявке</p>
                    <ul className="list-plain" data-testid="inbound-movements-list">
                      {inboundMovements.map((m) => (
                        <li key={m.id} data-testid="inbound-movement-row">
                          {m.quantity_delta > 0 ? '+' : ''}
                          {m.quantity_delta} · {m.movement_type}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {isFulfillmentAdmin && postedInventoryRows.length > 0 ? (
                  <ul className="list-plain" data-testid="inventory-balance-list">
                    {postedInventoryRows.map((row) => (
                      <li key={row.product_id} data-testid="inventory-balance-row">
                        {row.sku_code} — {row.quantity} шт
                        {row.reserved > 0 ? (
                          <span data-testid="inventory-balance-available-hint">
                            {' '}
                            (доступно {row.available})
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )}
          </Card>
        </div>
      </div>
    </Screen>
  )
}

