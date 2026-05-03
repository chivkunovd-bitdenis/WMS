import type { FormEventHandler } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'

type Me = {
  email: string
  organization_name: string
  role: string
  seller_name?: string | null
}

type SellerRow = { id: string; name: string }

type Props = {
  me: Me
  isFulfillmentAdmin: boolean
  sellers: SellerRow[]
  catalogBusy: boolean
  catalogError: string | null
  onCreateSellerAccount: FormEventHandler<HTMLFormElement>
  /** Вложенный блок (без дублирующего data-testid на корне карточки) */
  embedded?: boolean
}

export function DashboardCard({
  me,
  isFulfillmentAdmin,
  sellers,
  catalogBusy,
  catalogError,
  onCreateSellerAccount,
  embedded = false,
}: Props) {
  return (
    <Card className="card" data-testid={embedded ? undefined : 'dashboard'}>
      {embedded ? null : (
        <>
          <p data-testid="user-email">{me.email}</p>
          <p data-testid="org-name">{me.organization_name}</p>
          <p data-testid="user-role">{me.role}</p>
          {me.seller_name ? (
            <p data-testid="seller-cabinet-label">Селлер: {me.seller_name}</p>
          ) : null}
        </>
      )}

      {isFulfillmentAdmin && sellers.length > 0 ? (
        <form
          data-testid="seller-account-form"
          style={{ marginTop: 12 }}
          noValidate
          onSubmit={onCreateSellerAccount}
        >
          <h3 className="subtle" style={{ marginTop: 0 }}>
            Аккаунт селлера
          </h3>
          <p className="subtle" style={{ marginTop: 4, fontSize: 13 }}>
            Укажите email — селлер задаёт пароль при первом входе в кабинет.
          </p>
          {catalogError ? (
            <p className="error" data-testid="seller-account-error">
              {catalogError}
            </p>
          ) : null}
          <label>
            Селлер
            <Select
              name="acc_seller_id"
              data-testid="seller-account-seller"
              required
              defaultValue=""
            >
              <option value="" disabled>
                Выберите
              </option>
              {sellers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </label>
          <label>
            Email
            <Input
              name="acc_email"
              data-testid="seller-account-email"
              type="email"
              required
              autoComplete="off"
            />
          </label>
          <Button
            type="submit"
            data-testid="seller-account-submit"
            disabled={catalogBusy}
          >
            {catalogBusy ? '…' : 'Создать аккаунт селлера'}
          </Button>
        </form>
      ) : null}
    </Card>
  )
}

