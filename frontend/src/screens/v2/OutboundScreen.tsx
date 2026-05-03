import type { FormEventHandler } from 'react'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Input } from '../../ui/Input'
import { Select } from '../../ui/Select'
import { Screen } from '../AppV2Screens'

type WarehouseRow = { id: string; name: string; code: string }
type LocationRow = { id: string; code: string; warehouse_id: string }
type ProductRow = { id: string; name: string; sku_code: string }

type OutboundSummaryRow = {
  id: string
  warehouse_id: string
  status: string
  line_count: number
}

type OutboundLineRow = {
  id: string
  product_id: string
  sku_code: string
  product_name: string
  quantity: number
  shipped_qty: number
  storage_location_id: string | null
  storage_location_code: string | null
}

type OutboundDetailRow = {
  id: string
  warehouse_id: string
  status: string
  lines: OutboundLineRow[]
}

type OutboundMovementRow = {
  id: string
  quantity_delta: number
  movement_type: string
}

type Props = {
  opsError: string | null
  opsBusy: boolean
  isFulfillmentAdmin: boolean
  isFulfillmentSeller: boolean
  canEditOutboundDraft: boolean

  warehouses: WarehouseRow[]
  selectedWarehouseId: string | null
  products: ProductRow[]

  outboundSummaries: OutboundSummaryRow[]
  selectedOutboundId: string | null
  setSelectedOutboundId: (id: string) => void
  outboundDetail: OutboundDetailRow | null
  outboundRequestLocations: LocationRow[]
  outboundMovements: OutboundMovementRow[]

  onCreateOutboundRequest: FormEventHandler<HTMLFormElement>
  onAddOutboundLine: FormEventHandler<HTMLFormElement>
  onDeleteOutboundLine: (lineId: string) => void
  onSubmitOutboundRequest: () => void
  onSaveOutboundLineStorage: FormEventHandler<HTMLFormElement>
  onShipOutboundLine: FormEventHandler<HTMLFormElement>
  onPostOutboundRequest: () => void
}

export function OutboundScreen(props: Props) {
  const {
    opsError,
    opsBusy,
    isFulfillmentAdmin,
    isFulfillmentSeller,
    canEditOutboundDraft,
    warehouses,
    selectedWarehouseId,
    products,
    outboundSummaries,
    selectedOutboundId,
    setSelectedOutboundId,
    outboundDetail,
    outboundRequestLocations,
    outboundMovements,
    onCreateOutboundRequest,
    onAddOutboundLine,
    onDeleteOutboundLine,
    onSubmitOutboundRequest,
    onSaveOutboundLineStorage,
    onShipOutboundLine,
    onPostOutboundRequest,
  } = props

  return (
    <Screen title="Отгрузка" subtitle="Заявки → строки → подбор → списание">
      {opsError ? (
        <Card className="card">
          <p className="error" data-testid="operations-error">
            {opsError}
          </p>
        </Card>
      ) : null}

      <div className="screen-grid">
        <div className="stack">
          <Card className="card" data-testid="outbound-section">
            <h3 style={{ margin: 0, fontSize: 16 }}>Заявки на отгрузку</h3>
            <p className="subtle">
              Назначь ячейку на строке. Отгрузка по строке частями; «Провести весь остаток»
              списывает всё неотгруженное.
            </p>

            {canEditOutboundDraft ? (
              <form data-testid="outbound-create-form" noValidate onSubmit={onCreateOutboundRequest}>
                {isFulfillmentSeller && warehouses.length > 1 ? (
                  <label>
                    Склад для отгрузки
                    <Select
                      name="outbound_warehouse_id"
                      data-testid="outbound-create-warehouse"
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
                  data-testid="outbound-create-submit"
                  disabled={
                    opsBusy ||
                    warehouses.length === 0 ||
                    (!isFulfillmentSeller && !selectedWarehouseId && warehouses.length !== 1)
                  }
                >
                  {opsBusy ? '…' : 'Новая заявка на отгрузку'}
                </Button>
              </form>
            ) : null}

            <div data-testid="outbound-requests-list">
              <table className="ui-table" data-testid="outbound-requests-table">
              <thead>
                <tr>
                  <th>Статус</th>
                  <th>Строк</th>
                </tr>
              </thead>
              <tbody>
                {outboundSummaries.map((row) => (
                  <tr
                    key={row.id}
                    data-selected={row.id === selectedOutboundId ? 'true' : 'false'}
                    onClick={() => setSelectedOutboundId(row.id)}
                    data-testid="outbound-request-item"
                    data-status={row.status}
                  >
                    <td>
                      <span className="ui-badge" data-testid="outbound-request-status">
                        {row.status}
                      </span>
                    </td>
                    <td>{row.line_count}</td>
                  </tr>
                ))}
                {outboundSummaries.length === 0 ? (
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
            <h3 style={{ margin: 0, fontSize: 16 }}>Детали отгрузки</h3>
            {!outboundDetail ? (
              <p className="subtle" data-testid="outbound-detail">
                Выбери заявку слева.
              </p>
            ) : (
              <div data-testid="outbound-detail">
                <p className="subtle" data-testid="outbound-detail-status">
                  Статус: {outboundDetail.status}
                </p>

                <ul className="list-plain" data-testid="outbound-detail-lines">
                  {outboundDetail.lines.map((ln) => (
                    <li key={ln.id} data-testid="outbound-detail-line" data-line-id={ln.id}>
                      {ln.product_name} ({ln.sku_code}) — отгружено {ln.shipped_qty} из {ln.quantity}
                      {ln.storage_location_code ? ` · ячейка: ${ln.storage_location_code}` : ''}
                      {outboundDetail.status === 'draft' && isFulfillmentAdmin ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="danger"
                          data-testid="outbound-line-delete"
                          disabled={opsBusy}
                          onClick={() => onDeleteOutboundLine(ln.id)}
                        >
                          Удалить строку
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ul>

                {outboundDetail.status === 'draft' && canEditOutboundDraft ? (
                  <form data-testid="outbound-line-form" noValidate onSubmit={onAddOutboundLine}>
                    <label>
                      Товар
                      <Select
                        name="outbound_product_id"
                        data-testid="outbound-line-product"
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
                        name="outbound_qty"
                        data-testid="outbound-line-qty"
                        type="number"
                        min={1}
                        required
                      />
                    </label>
                    {outboundRequestLocations.length > 0 ? (
                      <label>
                        Ячейка (необязательно)
                        <Select
                          name="outbound_line_storage_id"
                          data-testid="outbound-line-location"
                          defaultValue=""
                        >
                          <option value="">— позже —</option>
                          {outboundRequestLocations.map((loc) => (
                            <option key={loc.id} value={loc.id}>
                              {loc.code}
                            </option>
                          ))}
                        </Select>
                      </label>
                    ) : null}
                    <Button
                      type="submit"
                      data-testid="outbound-line-submit"
                      disabled={opsBusy || products.length === 0}
                    >
                      {opsBusy ? '…' : 'Добавить строку'}
                    </Button>
                  </form>
                ) : null}

                {outboundDetail.status === 'draft' &&
                outboundDetail.lines.length > 0 &&
                isFulfillmentAdmin ? (
                  <Button
                    type="button"
                    data-testid="outbound-submit-request"
                    disabled={opsBusy}
                    onClick={onSubmitOutboundRequest}
                  >
                    {opsBusy ? '…' : 'Отправить заявку'}
                  </Button>
                ) : null}

                {outboundDetail.status === 'submitted' ? (
                  <div data-testid="outbound-ship-panel">
                    <p className="subtle">Строки в работе</p>
                    {isFulfillmentAdmin ? (
                      <>
                        {outboundDetail.lines.map((ln) =>
                          ln.shipped_qty < ln.quantity ? (
                            <Card key={ln.id} as="div" className="card" style={{ marginBottom: 10 }}>
                              <p className="subtle" style={{ marginTop: 0 }}>
                                {ln.sku_code} — осталось отгрузить {ln.quantity - ln.shipped_qty} из{' '}
                                {ln.quantity}
                              </p>
                              <form
                                data-testid="outbound-line-storage-form"
                                data-line-id={ln.id}
                                noValidate
                                onSubmit={onSaveOutboundLineStorage}
                              >
                                <label>
                                  Ячейка отбора
                                  <Select
                                    name="out_line_storage_id"
                                    data-testid="outbound-line-storage-select"
                                    defaultValue={ln.storage_location_id ?? ''}
                                    required
                                  >
                                    <option value="" disabled>
                                      Выберите ячейку
                                    </option>
                                    {outboundRequestLocations.map((loc) => (
                                      <option key={loc.id} value={loc.id}>
                                        {loc.code}
                                      </option>
                                    ))}
                                  </Select>
                                </label>
                                <Button
                                  type="submit"
                                  data-testid="outbound-line-storage-save"
                                  disabled={opsBusy || outboundRequestLocations.length === 0}
                                >
                                  Сохранить ячейку
                                </Button>
                              </form>
                              <form
                                data-testid="outbound-line-ship-form"
                                data-line-id={ln.id}
                                noValidate
                                onSubmit={onShipOutboundLine}
                              >
                                <label>
                                  Отгрузить, шт
                                  <Input
                                    name="ship_qty"
                                    data-testid="outbound-line-ship-qty"
                                    type="number"
                                    min={1}
                                    max={ln.quantity - ln.shipped_qty}
                                    required
                                  />
                                </label>
                                <Button
                                  type="submit"
                                  data-testid="outbound-line-ship-submit"
                                  disabled={opsBusy}
                                >
                                  Отгрузить
                                </Button>
                              </form>
                            </Card>
                          ) : null,
                        )}
                        <Button
                          type="button"
                          data-testid="outbound-post-submit"
                          disabled={opsBusy}
                          onClick={onPostOutboundRequest}
                        >
                          {opsBusy ? '…' : 'Провести весь остаток'}
                        </Button>
                      </>
                    ) : (
                      <p className="subtle" data-testid="outbound-seller-read-only">
                        Отгрузку ведёт фулфилмент; доступен просмотр строк и статуса.
                      </p>
                    )}
                  </div>
                ) : null}

                {outboundMovements.length > 0 ? (
                  <div data-testid="outbound-movements-block">
                    <p className="subtle">Движения по отгрузке</p>
                    <ul className="list-plain" data-testid="outbound-movements-list">
                      {outboundMovements.map((m) => (
                        <li key={m.id} data-testid="outbound-movement-row">
                          {m.quantity_delta} · {m.movement_type}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            )}
          </Card>
        </div>
      </div>
    </Screen>
  )
}

