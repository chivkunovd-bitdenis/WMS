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
}

type InboundLineRow = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  expected_qty: number
  posted_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type InboundDetailRow = {
  id: string
  warehouse_id: string
  status: string
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
    onSaveInboundLineStorage,
    onReceiveInboundLine,
    onPostInboundRequest,
  } = props

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
                      <span className="ui-badge" data-testid="inbound-request-status">
                        {row.status}
                      </span>
                    </td>
                    <td>{row.line_count}</td>
                  </tr>
                ))}
                {inboundSummaries.length === 0 ? (
                  <tr>
                    <td colSpan={2}>
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

                <ul className="list-plain" data-testid="inbound-detail-lines">
                  {inboundDetail.lines.map((ln) => (
                    <li key={ln.id} data-testid="inbound-detail-line">
                      {ln.product_name} ({ln.sku_code}) — принято {ln.posted_qty} из {ln.expected_qty}
                      {ln.storage_location_code ? ` · ячейка: ${ln.storage_location_code}` : ''}
                    </li>
                  ))}
                </ul>

                {inboundDetail.status === 'draft' && canEditInboundDraft ? (
                  <form data-testid="inbound-line-form" noValidate onSubmit={onAddInboundLine}>
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
                        {products.map((p) => (
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
                isFulfillmentAdmin ? (
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
                  <div data-testid="inbound-receiving-panel">
                    <p className="subtle">Строки в работе</p>
                    {isFulfillmentAdmin ? (
                      <>
                        {inboundDetail.lines.map((ln) =>
                          ln.posted_qty < ln.expected_qty ? (
                            <Card
                              key={ln.id}
                              as="div"
                              className="card"
                              style={{ marginBottom: 10 }}
                            >
                              <p className="subtle" style={{ marginTop: 0 }}>
                                {ln.sku_code} — осталось {ln.expected_qty - ln.posted_qty} из{' '}
                                {ln.expected_qty}
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
                                    max={ln.expected_qty - ln.posted_qty}
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
                          ) : null,
                        )}
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
                        Приёмку ведёт фулфилмент; доступен просмотр строк и статуса.
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

