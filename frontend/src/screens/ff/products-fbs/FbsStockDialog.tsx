import { Box, Divider, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  CheckboxInput,
  PercentSlider,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  StatusChip,
} from '../../../ui-kit'
import {
  freeStock,
  freeStockAt,
  onHandTotal,
  publishedQty,
  reservedTotal,
  type FbsRule,
  type Product,
  type Seller,
} from './stub'

// Модалка остатка для FBS. Заменяет собой целую вкладку «Остатки WB».
//
// Главное отличие от того, что было: раньше оператор вводил абсолютное число
// штук, и оно устаревало в тот момент, когда на склад приезжала новая партия.
// Здесь задаётся не число, а правило — доля свободного остатка. Свободный
// остаток пересчитывается сам, поэтому правило не устаревает: приехала тысяча
// штук — на FBS сразу стало больше, и никто не ходит поправлять цифру руками.

export function FbsStockDialog({
  open,
  products,
  seller,
  rule,
  onClose,
  onSave,
  onBind,
}: {
  open: boolean
  /** Один товар или несколько — модалка одна и та же. */
  products: Product[]
  seller: Seller
  rule: FbsRule
  onClose: () => void
  onSave: (rule: FbsRule) => void
  onBind: (warehouseId: string, wbWarehouseId: string) => void
}) {
  if (!open) return null
  return (
    <FbsStockDialogBody
      products={products}
      seller={seller}
      rule={rule}
      onClose={onClose}
      onSave={onSave}
      onBind={onBind}
    />
  )
}

function FbsStockDialogBody({
  products,
  seller,
  rule,
  onClose,
  onSave,
  onBind,
}: {
  products: Product[]
  seller: Seller
  rule: FbsRule
  onClose: () => void
  onSave: (rule: FbsRule) => void
  onBind: (warehouseId: string, wbWarehouseId: string) => void
}) {
  // Черновик начинается с текущего правила; тело монтируется на каждое открытие,
  // поэтому синхронизировать его с внешним значением не нужно.
  const [draft, setDraft] = useState<FbsRule>(rule)

  const many = products.length > 1
  // При нескольких товарах свободный остаток у каждого свой; показываем сумму,
  // чтобы процент не выглядел числом, взятым с потолка.
  const base = products.reduce((sum, product) => sum + freeStock(product), 0)
  const onHand = products.reduce((sum, product) => sum + onHandTotal(product), 0)
  const reserved = products.reduce((sum, product) => sum + reservedTotal(product), 0)
  // Доля склада считается от того, что лежит НА ЭТОМ складе. Считать её от общего
  // остатка нельзя: 100% на одном складе и 70% на другом дали бы в сумме больше,
  // чем есть на самом деле, — товар нельзя опубликовать дважды.
  const baseAt = (warehouseId: string) =>
    products.reduce((sum, product) => sum + freeStockAt(product, warehouseId), 0)
  const willPublish = products.reduce(
    (sum, product) => sum + publishedQty(product, draft, seller),
    0,
  )
  const unbound = seller.warehouses.filter((one) => one.boundTo === null)

  return (
    <AppDialog
      open
      onClose={onClose}
      maxWidth="md"
      testId="fbs-stock-dialog"
      title={many ? `Остаток для FBS · ${products.length} товаров` : 'Остаток для FBS'}
      actions={
        <ActionGroup>
          <SecondaryAction onClick={onClose} data-testid="fbs-stock-cancel">
            Отмена
          </SecondaryAction>
          <PrimaryAction onClick={() => onSave(draft)} data-testid="fbs-stock-save">
            Сохранить
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={2.5}>
        <Stack spacing={0.5}>
          <Typography variant="subtitle2">
            {many
              ? `${products.length} товаров, ${seller.name}`
              : `${products[0]!.name}${products[0]!.size ? `, ${products[0]!.size}` : ''} · ${products[0]!.sku}`}
          </Typography>
          {/* Три числа, а не одно: без «занято» непонятно, почему процент даёт
              меньше, чем ожидал оператор, глядя на общий остаток. */}
          <Typography variant="body2" color="text.secondary">
            На складе {onHand.toLocaleString('ru-RU')} шт, занято{' '}
            {reserved.toLocaleString('ru-RU')} — свободно {base.toLocaleString('ru-RU')}
          </Typography>
        </Stack>

        <CheckboxInput
          label="Передавать остаток в Wildberries"
          checked={draft.publish}
          onChange={(publish) => setDraft((one) => ({ ...one, publish }))}
          testId="fbs-stock-publish"
        />

        <PercentSlider
          label="Доля свободного остатка"
          value={draft.percent}
          onChange={(percent) => setDraft((one) => ({ ...one, percent }))}
          base={base}
          disabled={!draft.sameEverywhere}
          disabledReason="Сейчас доля задаётся по каждому складу отдельно"
          testId="fbs-stock-percent"
        />

        <Divider />

        <CheckboxInput
          label="Одинаково по всем складам"
          checked={draft.sameEverywhere}
          onChange={(sameEverywhere) => setDraft((one) => ({ ...one, sameEverywhere }))}
          helperText="Выключите, чтобы задать свою долю каждому складу"
          testId="fbs-stock-same"
        />

        <Stack spacing={2}>
          {seller.warehouses.map((warehouse) => (
            <Stack key={warehouse.id} spacing={1}>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography variant="subtitle2">{warehouse.name}</Typography>
                {warehouse.boundTo === null ? (
                  <StatusChip
                    label="склад не сопоставлен"
                    tone="warn"
                    hint="Пока склад не сопоставлен со складом продавца в кабинете WB, остаток по нему не уйдёт"
                  />
                ) : null}
                <Box sx={{ flexGrow: 1 }} />
                <Box sx={{ minWidth: 240 }}>
                  <SelectInput
                    label="Склад продавца в Wildberries"
                    value={warehouse.boundTo ?? ''}
                    onChange={(value) => onBind(warehouse.id, value)}
                    options={seller.wbWarehouses.map((one) => ({ value: one.id, label: one.name }))}
                    emptyLabel="не сопоставлен"
                    testId={`fbs-stock-bind-${warehouse.id}`}
                  />
                </Box>
              </Stack>
              <PercentSlider
                label="Доля на этот склад"
                value={
                  draft.sameEverywhere ? draft.percent : (draft.byWarehouse[warehouse.id] ?? 0)
                }
                onChange={(percent) =>
                  setDraft((one) => ({
                    ...one,
                    byWarehouse: { ...one.byWarehouse, [warehouse.id]: percent },
                  }))
                }
                base={baseAt(warehouse.id)}
                disabled={draft.sameEverywhere}
                disabledReason="Включено «одинаково по всем складам»"
                testId={`fbs-stock-percent-${warehouse.id}`}
              />
            </Stack>
          ))}
        </Stack>

        <Divider />

        <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
          <Typography variant="h6" data-testid="fbs-stock-result">
            {willPublish.toLocaleString('ru-RU')} шт
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {draft.publish
              ? 'уйдёт в Wildberries прямо сейчас и будет пересчитываться само'
              : 'передача выключена — в Wildberries не уйдёт ничего'}
          </Typography>
        </Stack>

        {unbound.length > 0 && draft.publish ? (
          <Typography variant="body2" color="text.secondary">
            По складам {unbound.map((one) => one.name).join(', ')} остаток не уйдёт, пока они не
            сопоставлены со складами продавца.
          </Typography>
        ) : null}
      </Stack>
    </AppDialog>
  )
}
