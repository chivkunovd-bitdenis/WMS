import type { FormEventHandler } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'

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

type GlobalMovementRow = {
  id: string
  sku_code: string
  quantity_delta: number
  movement_type: string
}

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
  canEditOutboundDraft: boolean

  warehouses: WarehouseRow[]
  selectedWarehouseId: string | null
  locations: LocationRow[]
  products: ProductRow[]

  inboundSummaries: InboundSummaryRow[]
  selectedInboundId: string | null
  setSelectedInboundId: (id: string) => void
  inboundDetail: InboundDetailRow | null
  inboundRequestLocations: LocationRow[]
  inboundMovements: InboundMovementRow[]
  postedInventoryRows: PostedInventoryBalanceRow[]

  globalMovements: GlobalMovementRow[]

  outboundSummaries: OutboundSummaryRow[]
  selectedOutboundId: string | null
  setSelectedOutboundId: (id: string) => void
  outboundDetail: OutboundDetailRow | null
  outboundRequestLocations: LocationRow[]
  outboundMovements: OutboundMovementRow[]

  backgroundJobStatus: string | null
  backgroundJobResult: string | null

  onStartMovementsDigestJob: () => void
  onCreateInboundRequest: FormEventHandler<HTMLFormElement>
  onAddInboundLine: FormEventHandler<HTMLFormElement>
  onSubmitInboundRequest: () => void
  onSaveInboundLineStorage: FormEventHandler<HTMLFormElement>
  onReceiveInboundLine: FormEventHandler<HTMLFormElement>
  onPostInboundRequest: () => void

  onRefreshGlobalMovementsClick: () => void
  onStockTransfer: FormEventHandler<HTMLFormElement>

  onCreateOutboundRequest: FormEventHandler<HTMLFormElement>
  onAddOutboundLine: FormEventHandler<HTMLFormElement>
  onDeleteOutboundLine: (lineId: string) => void
  onSubmitOutboundRequest: () => void
  onSaveOutboundLineStorage: FormEventHandler<HTMLFormElement>
  onShipOutboundLine: FormEventHandler<HTMLFormElement>
  onPostOutboundRequest: () => void
}

export function OperationsSection(props: Props) {
  const {
    opsError,
    opsBusy,
    isFulfillmentAdmin,
    isFulfillmentSeller,
    canEditInboundDraft,
    canEditOutboundDraft,
    warehouses,
    selectedWarehouseId,
    locations,
    products,
    inboundSummaries,
    selectedInboundId,
    setSelectedInboundId,
    inboundDetail,
    inboundRequestLocations,
    inboundMovements,
    postedInventoryRows,
    globalMovements,
    outboundSummaries,
    selectedOutboundId,
    setSelectedOutboundId,
    outboundDetail,
    outboundRequestLocations,
    outboundMovements,
    backgroundJobStatus,
    backgroundJobResult,
    onStartMovementsDigestJob,
    onCreateInboundRequest,
    onAddInboundLine,
    onSubmitInboundRequest,
    onSaveInboundLineStorage,
    onReceiveInboundLine,
    onPostInboundRequest,
    onRefreshGlobalMovementsClick,
    onStockTransfer,
    onCreateOutboundRequest,
    onAddOutboundLine,
    onDeleteOutboundLine,
    onSubmitOutboundRequest,
    onSaveOutboundLineStorage,
    onShipOutboundLine,
    onPostOutboundRequest,
  } = props

  return (
    <div
      id="operations-section"
      className="stack"
      data-testid="operations-section"
    >
      {opsError ? (
        <p className="error" data-testid="operations-error">
          {opsError}
        </p>
      ) : null}

      {isFulfillmentAdmin ? (
        <Card className="card" data-testid="background-job-section">
          <h2>Фоновая задача</h2>
          <p className="subtle">
            Сервер считает сводку по журналу движений в фоне; статус обновляется
            после запуска (как отчёт / тяжёлая операция).
          </p>
          <Button
            type="button"
            data-testid="background-job-start"
            disabled={opsBusy}
            onClick={onStartMovementsDigestJob}
          >
            {opsBusy ? '…' : 'Сводка по движениям'}
          </Button>
          <p className="subtle" data-testid="background-job-status">
            Статус: {backgroundJobStatus ?? '—'}
          </p>
          {backgroundJobResult ? (
            <p data-testid="background-job-result">{backgroundJobResult}</p>
          ) : null}
        </Card>
      ) : null}

      <Card className="card">
        <h2>Приёмка</h2>
        <p className="subtle">
          Ячейку можно указать при добавлении строки или позже. Частичный приём —
          по строке; «Провести весь остаток» оприходует всё непринятое по строкам
          с назначенной ячейкой. Движения пишутся в журнал.
        </p>

        {canEditInboundDraft ? (
          <form
            data-testid="inbound-create-form"
            noValidate
            onSubmit={onCreateInboundRequest}
          >
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
                (!isFulfillmentSeller &&
                  !selectedWarehouseId &&
                  warehouses.length !== 1)
              }
            >
              {opsBusy ? '…' : 'Новая заявка на приёмку'}
            </Button>
          </form>
        ) : null}

        <ul className="list-plain" data-testid="inbound-requests-list">
          {inboundSummaries.map((row) => (
            <li key={row.id}>
              <Button
                type="button"
                variant="ghost"
                className="list-row-button"
                data-testid="inbound-request-item"
                data-status={row.status}
                data-selected={row.id === selectedInboundId ? 'true' : 'false'}
                onClick={() => setSelectedInboundId(row.id)}
              >
                <span data-testid="inbound-request-status">{row.status}</span> ·
                строк: {row.line_count}
              </Button>
            </li>
          ))}
        </ul>

        {inboundDetail ? (
          <div data-testid="inbound-detail">
            <p className="subtle" data-testid="inbound-detail-status">
              Статус: {inboundDetail.status}
            </p>
            <ul className="list-plain" data-testid="inbound-detail-lines">
              {inboundDetail.lines.map((ln) => (
                <li key={ln.id} data-testid="inbound-detail-line">
                  {ln.product_name} ({ln.sku_code}) — принято {ln.posted_qty} из{' '}
                  {ln.expected_qty}
                  {ln.storage_location_code
                    ? ` · ячейка: ${ln.storage_location_code}`
                    : ''}
                </li>
              ))}
            </ul>

            {inboundDetail.status === 'draft' && canEditInboundDraft ? (
              <form
                data-testid="inbound-line-form"
                noValidate
                onSubmit={onAddInboundLine}
              >
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
                            {ln.sku_code} — осталось {ln.expected_qty - ln.posted_qty}{' '}
                            из {ln.expected_qty}
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
        ) : null}
      </Card>

      <Card className="card" data-testid="global-movements-section">
        <h2>Журнал движений</h2>
        <p className="subtle">
          Последние операции по складу (приёмка, перемещение, отгрузка).
        </p>
        <Button
          type="button"
          data-testid="global-movements-refresh"
          onClick={onRefreshGlobalMovementsClick}
        >
          Обновить
        </Button>
        <ul className="list-plain" data-testid="global-movements-list">
          {globalMovements.map((m) => (
            <li key={m.id} data-testid="global-movement-row">
              {m.sku_code}: {m.quantity_delta > 0 ? '+' : ''}
              {m.quantity_delta} · {m.movement_type}
            </li>
          ))}
        </ul>
      </Card>

      {isFulfillmentAdmin ? (
        <Card className="card" data-testid="stock-transfer-section">
          <h2>Перемещение между ячейками</h2>
          <p className="subtle">
            Списание с ячейки «откуда» и оприходование в «куда» на одном складе.
          </p>
          <form data-testid="stock-transfer-form" noValidate onSubmit={onStockTransfer}>
            <label>
              Откуда (ячейка)
              <Select name="transfer_from_loc" data-testid="transfer-from-loc" required defaultValue="">
                <option value="" disabled>
                  Выберите
                </option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.code}
                  </option>
                ))}
              </Select>
            </label>
            <label>
              Куда (ячейка)
              <Select name="transfer_to_loc" data-testid="transfer-to-loc" required defaultValue="">
                <option value="" disabled>
                  Выберите
                </option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.code}
                  </option>
                ))}
              </Select>
            </label>
            <label>
              Товар
              <Select name="transfer_product_id" data-testid="transfer-product" required defaultValue="">
                <option value="" disabled>
                  SKU
                </option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.sku_code} — {p.name}
                  </option>
                ))}
              </Select>
            </label>
            <label>
              Количество
              <Input
                name="transfer_qty"
                data-testid="transfer-qty"
                type="number"
                min={1}
                required
              />
            </label>
            <Button
              type="submit"
              data-testid="transfer-submit"
              disabled={opsBusy || locations.length < 2}
            >
              {opsBusy ? '…' : 'Переместить'}
            </Button>
          </form>
        </Card>
      ) : null}

      <Card className="card" data-testid="outbound-section">
        <h2>Отгрузка</h2>
        <p className="subtle">
          Заявка на списание остатков из выбранных ячеек. Назначьте ячейку на строке;
          отгрузка по строке частями; «Провести весь остаток» списывает всё неотгруженное.
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
                (!isFulfillmentSeller &&
                  !selectedWarehouseId &&
                  warehouses.length !== 1)
              }
            >
              {opsBusy ? '…' : 'Новая заявка на отгрузку'}
            </Button>
          </form>
        ) : null}

        <ul className="list-plain" data-testid="outbound-requests-list">
          {outboundSummaries.map((row) => (
            <li key={row.id}>
              <Button
                type="button"
                variant="ghost"
                className="list-row-button"
                data-testid="outbound-request-item"
                data-status={row.status}
                data-selected={row.id === selectedOutboundId ? 'true' : 'false'}
                onClick={() => setSelectedOutboundId(row.id)}
              >
                <span data-testid="outbound-request-status">{row.status}</span> · строк:{' '}
                {row.line_count}
              </Button>
            </li>
          ))}
        </ul>

        {outboundDetail ? (
          <div data-testid="outbound-detail">
            <p className="subtle" data-testid="outbound-detail-status">
              Статус: {outboundDetail.status}
            </p>
            <ul className="list-plain" data-testid="outbound-detail-lines">
              {outboundDetail.lines.map((ln) => (
                <li key={ln.id} data-testid="outbound-detail-line" data-line-id={ln.id}>
                  {ln.product_name} ({ln.sku_code}) — отгружено {ln.shipped_qty} из{' '}
                  {ln.quantity}
                  {ln.storage_location_code
                    ? ` · ячейка: ${ln.storage_location_code}`
                    : ''}
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
                        <Card
                          key={ln.id}
                          as="div"
                          className="card"
                          style={{ marginBottom: 10 }}
                        >
                          <p className="subtle" style={{ marginTop: 0 }}>
                            {ln.sku_code} — осталось отгрузить {ln.quantity - ln.shipped_qty}{' '}
                            из {ln.quantity}
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
        ) : null}
      </Card>
    </div>
  )
}

