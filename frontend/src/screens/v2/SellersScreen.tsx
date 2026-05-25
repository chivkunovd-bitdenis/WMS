import type { FormEventHandler } from 'react'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Input } from '../../ui/Input'
import { Screen } from '../AppV2Screens'

type SellerRow = { id: string; name: string }

type Props = {
  isFulfillmentAdmin: boolean
  catalogBusy: boolean
  catalogError: string | null
  sellers: SellerRow[]
  onCreateSeller: FormEventHandler<HTMLFormElement>
}

export function SellersScreen({
  isFulfillmentAdmin,
  catalogBusy,
  catalogError,
  sellers,
  onCreateSeller,
}: Props) {
  return (
    <Screen
      title="Селлеры"
      subtitle="Клиенты фулфилмента. Запись селлера — здесь; вход в кабинет — на дашборде (аккаунт по email)."
    >
      {catalogError ? (
        <Card className="card">
          <p className="error" data-testid="catalog-error">
            {catalogError}
          </p>
        </Card>
      ) : null}

      <div className="screen-grid">
        <div className="stack">
          <Card className="card" data-testid="sellers-panel">
            <h3 style={{ marginTop: 0 }}>Список селлеров</h3>
            <table className="data-table" data-testid="sellers-table">
              <thead>
                <tr>
                  <th>Название</th>
                </tr>
              </thead>
              <tbody>
                {sellers.map((s) => (
                  <tr key={s.id} data-testid="seller-row" data-seller-id={s.id}>
                    <td>{s.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sellers.length === 0 ? (
              <p className="subtle" data-testid="sellers-empty">
                Пока нет селлеров. Добавьте первого справа.
              </p>
            ) : null}
          </Card>
        </div>

        <div className="stack">
          {isFulfillmentAdmin ? (
            <Card className="card" data-testid="seller-create-panel">
              <h3 style={{ marginTop: 0 }}>Добавить селлера</h3>
              <p className="subtle" style={{ marginTop: 0, fontSize: 13 }}>
                Создаётся только запись клиента. Учётная запись для входа в портал селлера
                выдаётся отдельно на дашборде.
              </p>
              <form data-testid="seller-form" noValidate onSubmit={onCreateSeller}>
                <label>
                  Название / бренд
                  <Input
                    name="seller_name"
                    data-testid="seller-name"
                    required
                    autoComplete="off"
                    placeholder="Например, ACME Brand"
                  />
                </label>
                <Button
                  type="submit"
                  data-testid="seller-submit"
                  disabled={catalogBusy}
                  style={{ marginTop: 12 }}
                >
                  {catalogBusy ? '…' : 'Добавить селлера'}
                </Button>
              </form>
            </Card>
          ) : (
            <Card className="card">
              <p className="subtle" data-testid="sellers-admin-only">
                Добавление селлеров доступно только администратору фулфилмента.
              </p>
            </Card>
          )}
        </div>
      </div>
    </Screen>
  )
}
