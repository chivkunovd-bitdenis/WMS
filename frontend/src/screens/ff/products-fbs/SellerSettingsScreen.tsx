import { Box, Paper, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  CheckboxInput,
  DataTable,
  ScreenHeader,
  SelectInput,
  StatusChip,
} from '../../../ui-kit'
import type { Column } from '../../../ui-kit'
import { SELLERS, type Seller, type SellerWarehouse } from './stub'

// Настройки продавца: какие его склады обслуживаем мы.
//
// Это свойство продавца, а не каждого его товара, поэтому и живёт оно здесь, а
// не в модалке остатка. Галочка решает сразу две вещи: какие заказы FBS наши и
// по каким складам раздаётся остаток. У фулфилмента обычно один такой склад —
// продавец заводит его специально под нас.

type Row = { seller: Seller; warehouse: SellerWarehouse }

export function SellerSettingsScreen({ onNote }: { onNote: (note: string) => void }) {
  const [sellerId, setSellerId] = useState(SELLERS[0]!.id)
  const [served, setServed] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      SELLERS.flatMap((seller) => seller.warehouses.map((one) => [one.id, one.fbsEnabled])),
    ),
  )
  const [bound, setBound] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      SELLERS.flatMap((seller) =>
        seller.warehouses.map((one) => [one.id, one.boundTo ?? '']),
      ),
    ),
  )

  const seller = SELLERS.find((one) => one.id === sellerId)!
  const rows: Row[] = seller.warehouses.map((warehouse) => ({ seller, warehouse }))
  const servedCount = rows.filter(({ warehouse }) => served[warehouse.id]).length

  const columns: Column<Row>[] = [
    {
      key: 'served',
      header: 'Заказы FBS',
      width: 120,
      render: ({ warehouse }) => (
        <CheckboxInput
          label={`Обслуживаем склад ${warehouse.name}`}
          hideLabel
          checked={Boolean(served[warehouse.id])}
          onChange={(checked) => {
            setServed((current) => ({ ...current, [warehouse.id]: checked }))
            onNote(
              checked
                ? `Заглушка: склад ${warehouse.name} — заказы по нему теперь наши`
                : `Заглушка: склад ${warehouse.name} отключён, заказы по нему к нам не приедут`,
            )
          }}
          testId={`seller-served-${warehouse.id}`}
        />
      ),
    },
    {
      key: 'name',
      header: 'Склад продавца',
      render: ({ warehouse }) => (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minHeight: 40 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {warehouse.name}
          </Typography>
          {served[warehouse.id] && !bound[warehouse.id] ? (
            <StatusChip
              label="не сопоставлен"
              tone="warn"
              hint="Пока склад не сопоставлен, остаток по нему не уйдёт и заказы не свяжутся"
            />
          ) : null}
        </Stack>
      ),
    },
    {
      key: 'bind',
      header: 'Склад в кабинете Wildberries',
      width: 300,
      render: ({ warehouse }) => (
        <SelectInput
          label="Склад в кабинете Wildberries"
          hideLabel
          value={bound[warehouse.id] ?? ''}
          onChange={(value) => {
            setBound((current) => ({ ...current, [warehouse.id]: value }))
            onNote(`Заглушка: сопоставление склада ${warehouse.name} изменено`)
          }}
          options={seller.wbWarehouses.map((one) => ({ value: one.id, label: one.name }))}
          emptyLabel="не сопоставлен"
          testId={`seller-bind-${warehouse.id}`}
        />
      ),
    },
  ]

  return (
    <Box data-testid="seller-settings-screen">
      <ScreenHeader
        title="Продавец"
        purpose="Какие склады продавца обслуживает фулфилмент и с чем они сопоставлены в Wildberries."
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Box sx={{ minWidth: 240 }}>
            <SelectInput
              label="Продавец"
              value={sellerId}
              onChange={setSellerId}
              options={SELLERS.map((one) => ({ value: one.id, label: one.name }))}
              testId="seller-settings-seller"
            />
          </Box>
          <Typography variant="body2" color="text.secondary">
            {servedCount === 0
              ? 'Ни один склад не обслуживается — заказы FBS этого продавца к нам не приедут'
              : servedCount === 1
                ? 'Обслуживаем один склад: в карточке товара будет один ползунок без выбора склада'
                : `Обслуживаем ${servedCount} склада: в карточке товара остаток делится между ними`}
          </Typography>
        </Stack>
      </Paper>

      <DataTable
        testId="seller-warehouses"
        columns={columns}
        rows={rows}
        getRowKey={({ warehouse }) => warehouse.id}
        empty={{ title: 'У продавца нет складов', hint: 'Склады подтянутся из кабинета Wildberries.' }}
      />

      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Заказы, адресованные невыбранным складам, к нам не попадают: они отсеиваются при импорте из
        Wildberries, а не прячутся на экране. Фильтра по складу в самом запросе к Wildberries нет —
        склад приходит внутри каждого заказа, поэтому отсев делается сразу при приёме данных.
      </Typography>
    </Box>
  )
}
