import type { FormEventHandler } from 'react'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Input } from '../../ui/Input'
import { Select } from '../../ui/Select'
import { Screen } from '../AppV2Screens'

type LocationRow = { id: string; code: string; warehouse_id: string }
type ProductRow = { id: string; name: string; sku_code: string }

type Props = {
  opsError: string | null
  opsBusy: boolean
  isFulfillmentAdmin: boolean
  locations: LocationRow[]
  products: ProductRow[]
  onStockTransfer: FormEventHandler<HTMLFormElement>
}

export function TransfersScreen({
  opsError,
  opsBusy,
  isFulfillmentAdmin,
  locations,
  products,
  onStockTransfer,
}: Props) {
  return (
    <Screen title="Перемещения" subtitle="Перемещение между ячейками на одном складе">
      {opsError ? (
        <p className="error" data-testid="operations-error">
          {opsError}
        </p>
      ) : null}
      {!isFulfillmentAdmin ? (
        <Card className="card">
          <p className="subtle">Доступно только для фулфилмента.</p>
        </Card>
      ) : (
        <Card className="card" data-testid="stock-transfer-section">
          <p className="subtle">
            Списание с ячейки «откуда» и оприходование в «куда» на одном складе.
          </p>
          <form data-testid="stock-transfer-form" noValidate onSubmit={onStockTransfer}>
            <label>
              Откуда (ячейка)
              <Select
                name="transfer_from_loc"
                data-testid="transfer-from-loc"
                required
                defaultValue=""
              >
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
              <Select
                name="transfer_product_id"
                data-testid="transfer-product"
                required
                defaultValue=""
              >
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
      )}
    </Screen>
  )
}

