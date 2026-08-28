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
  onHandTotal,
  publishedQty,
  reservedTotal,
  servedWarehouses,
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
  // Склады делят между собой ОДИН свободный остаток, а не имеют каждый свой.
  // Товар лежит у нас, а склады продавца в кабинете WB — это направления, куда
  // мы его выставляем. Поэтому сумма долей не может превысить сто процентов:
  // отдать половину одному складу и половину другому можно, а по половине
  // каждому из трёх — уже нет, столько товара просто нет.
  // Раздаём остаток только по складам, которые обслуживаем. Если он один —
  // делить не с кем, и выбор складов на экране только мешает: один ползунок.
  const served = servedWarehouses(seller)
  const single = served.length <= 1

  const spent = served.reduce(
    (sum, warehouse) => sum + (draft.byWarehouse[warehouse.id] ?? 0),
    0,
  )
  const freePercent = Math.max(0, 100 - spent)
  const willPublish = products.reduce(
    (sum, product) => sum + publishedQty(product, draft, seller),
    0,
  )
  const unbound = served.filter((one) => one.boundTo === null)

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
          disabled={!single && !draft.sameEverywhere}
          disabledReason="Сейчас доля задаётся по каждому складу отдельно"
          testId="fbs-stock-percent"
        />

        {single ? null : (
          <>
            <Divider />
            <CheckboxInput
              label="Одинаково по всем складам"
              checked={draft.sameEverywhere}
              onChange={(sameEverywhere) => setDraft((one) => ({ ...one, sameEverywhere }))}
              helperText="Выключите, чтобы задать свою долю каждому складу"
              testId="fbs-stock-same"
            />
          </>
        )}

        {single || draft.sameEverywhere ? null : (
          <Typography variant="body2" color="text.secondary" data-testid="fbs-stock-rest">
            Нераспределено: {freePercent}% — это{' '}
            {Math.floor((base * freePercent) / 100).toLocaleString('ru-RU')} шт. Склады делят один
            и тот же остаток, поэтому больше ста процентов раздать нельзя.
          </Typography>
        )}

        <Stack spacing={2}>
          {(single ? [] : served).map((warehouse) => (
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
                base={base}
                max={(draft.byWarehouse[warehouse.id] ?? 0) + freePercent}
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

        {single && served[0] ? (
          <Typography variant="body2" color="text.secondary">
            Склад {served[0].name}
            {served[0].boundTo
              ? ` — сопоставлен со складом продавца в Wildberries.`
              : ` пока не сопоставлен со складом продавца, остаток по нему не уйдёт.`}{' '}
            Список складов настраивается в карточке продавца.
          </Typography>
        ) : null}

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
