import { Box, Divider, Slider, Stack, Typography } from '@mui/material'
import { useState } from 'react'
import {
  ActionGroup,
  AppDialog,
  CheckboxInput,
  ErrorNotice,
  NumberInput,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  StatusChip,
  WarningNotice,
} from '../../../ui-kit'
import {
  freeStock,
  MARKETPLACE_NAMES,
  onHandTotal,
  publishesTo,
  reservedTotal,
  servedWarehouses,
  totalPercent,
  totalUnits,
  warehouseMarketplace,
  type FbsRule,
  type MarketplaceCode,
  type Product,
  type Seller,
  type SellerWarehouse,
} from './stub'

type DialogProduct = Product & { savedPublishedNow?: number }

// The API supplies aggregate stock, not the per-warehouse inputs needed for a
// draft quantity. Keep percentage editing without inventing a quantity preview.
function PercentSlider({ label, value, onChange, disabled = false, disabledReason,
  max = 100, testId }: {
  label: string; value: number; onChange: (value: number) => void
  disabled?: boolean; disabledReason?: string; max?: number; testId?: string
}) {
  return <Stack spacing={0.5} sx={{ opacity: disabled ? 0.5 : 1 }}>
    <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>{label}</Typography>
      <Typography variant="body2">{value}%</Typography>
    </Stack>
    <Slider value={value} onChange={(_event, next) =>
      onChange(Math.min(Array.isArray(next) ? next[0]! : next, max))}
      min={0} max={100} step={10} marks disabled={disabled} valueLabelDisplay="auto"
      aria-label={label} data-testid={testId} sx={{ mx: 1, width: 'auto' }} />
    {disabled && disabledReason ? <Typography variant="caption" color="text.secondary">
      {disabledReason}
    </Typography> : null}
  </Stack>
}

export function FbsStockDialog({
  open,
  products,
  seller,
  rule,
  onClose,
  onSave,
  onBind,
  onServedChange,
  saveError,
  ozonWarehousesError,
}: {
  open: boolean
  /** Один товар или несколько — модалка одна и та же. */
  products: DialogProduct[]
  seller: Seller
  rule: FbsRule
  onClose: () => void
  onSave: (rule: FbsRule) => void
  onBind: (warehouseId: string, wbWarehouseId: string) => void
  /** Обслуживаем ли мы склад продавца. Свойство продавца, не товара. */
  onServedChange?: (warehouseId: string, served: boolean) => void
  /** Отказ сервера. Показываем прямо здесь: окно с введённым не закрываем. */
  saveError?: string | null
  /** Почему не приехал справочник складов Ozon — текст в озоновском блоке. */
  ozonWarehousesError?: string | null
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
      onServedChange={onServedChange}
      saveError={saveError}
      ozonWarehousesError={ozonWarehousesError}
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
  onServedChange,
  saveError,
  ozonWarehousesError,
}: {
  products: DialogProduct[]
  seller: Seller
  rule: FbsRule
  onClose: () => void
  onSave: (rule: FbsRule) => void
  onBind: (warehouseId: string, wbWarehouseId: string) => void
  onServedChange?: (warehouseId: string, served: boolean) => void
  saveError?: string | null
  ozonWarehousesError?: string | null
}) {
  // The percentage limit is shared across destinations. Publication quantities
  // additionally depend on each destination's physical WMS warehouse.
  const served = servedWarehouses(seller)
  // Ни одного обслуживаемого склада — раздавать долю некуда. Ползунок в этом
  // состоянии обманывает: он показывает штуки, которых в кабинете не появится,
  // потому что публикация идёт только по обслуживаемым складам.
  const noWarehouses = seller.warehouses.length === 0
  const noneServed = served.length === 0
  const single = served.length <= 1

  // Черновик начинается с текущего правила; тело монтируется на каждое открытие,
  // поэтому синхронизировать его с внешним значением не нужно.
  //
  // Единственный обслуживаемый склад — особый случай. Галочку «одинаково по
  // всем складам» в этом режиме не показывают (делить не с кем), а расчёт при
  // выключенной галочке берёт проценты складов и общий процент игнорирует.
  // Товар с выключённым флагом попадал в тупик: верхний ползунок стоял на 100%,
  // а в Wildberries уходила старая доля склада (свободно 5, доля склада 30% —
  // «1 шт уйдёт» при «100% — это 5 шт»), и включить флаг было негде. Поэтому
  // при одном складе черновик всегда считается по общему проценту: что оператор
  // видит на ползунке, то и уезжает.
  const [draft, setDraft] = useState<FbsRule>(
    { ...rule, ...(single ? { sameEverywhere: true } : {}), changedPublication: [] },
  )

  const many = products.length > 1
  // При нескольких товарах свободный остаток у каждого свой; показываем сумму,
  // чтобы процент не выглядел числом, взятым с потолка.
  const base = products.reduce((sum, product) => sum + freeStock(product), 0)
  const onHand = products.reduce((sum, product) => sum + onHandTotal(product), 0)
  const reserved = products.reduce((sum, product) => sum + reservedTotal(product), 0)

  const spent = served.filter((one) => publishesTo(draft, warehouseMarketplace(one))).reduce(
    (sum, warehouse) => sum + (draft.byWarehouse[warehouse.id] ?? 0),
    0,
  )
  const freePercent = Math.max(0, 100 - spent)
  const savedPublished = products.every((product) => product.savedPublishedNow !== undefined)
    ? products.reduce((sum, product) => sum + product.savedPublishedNow!, 0)
    : undefined
  const unbound = served.filter((one) => one.boundTo === null)
  // Сумма долей так, как её считает сервер. При галке «одинаково» доля идёт
  // КАЖДОМУ складу, поэтому 50% на четырёх складах — это 200%, и сохранение
  // отобьётся. Раньше окно про это не знало и узнавало от сервера уже отказом.
  const enabledServed = served.filter((one) => publishesTo(draft, warehouseMarketplace(one)))
  const enabledRule = { ...draft, byWarehouse: Object.fromEntries(
    enabledServed.map((one) => [one.id, draft.byWarehouse[one.id] ?? 0]),
  ) }
  const percentSum = totalPercent(enabledRule, enabledServed.length)
  const publishesAny = draft.publish || (draft.publishOzon ?? draft.publish)
  // В режиме штук ограничение то же самое, только в единицах: склады делят один
  // и тот же физический остаток, поэтому в сумме больше свободного не раздать.
  const unitsSum = totalUnits(draft, seller.warehouses)
  const enabledPlacesLabel = [
    draft.publish ? MARKETPLACE_NAMES.wb : null,
    (draft.publishOzon ?? draft.publish) ? MARKETPLACE_NAMES.ozon : null,
  ].filter(Boolean).join(" и ")
  // Existing caps can exceed free stock after an order or stock movement.
  // For bulk edits the server compares every product with its own saved rule.
  const increasesCap = Object.entries(draft.unitsByWarehouse).some(([key, value]) =>
    value > (rule.unitsByWarehouse[key] ?? 0),
  )
  const overAllocated = draft.unitsMode
    ? !many && increasesCap && unitsSum > base
    : publishesAny && percentSum > 100
  // Склады раскладываются по площадкам (WMS-350). Порядок фиксированный:
  // Wildberries первым, потому что он был здесь всегда, Ozon следом.
  // Заголовки появляются только когда площадок правда две — у продавца с одним
  // Wildberries окно остаётся ровно таким, каким было.
  const groups: Array<{ marketplace: MarketplaceCode; warehouses: SellerWarehouse[] }> = (
    ['wb', 'ozon'] as const
  )
    .map((marketplace) => ({
      marketplace,
      warehouses: seller.warehouses.filter((one) => warehouseMarketplace(one) === marketplace),
    }))
    .filter((group) => group.warehouses.length > 0)
  const manyMarketplaces = groups.length > 1
  // Товар живёт на Ozon, если так сказал каталог. Пустой список — источник
  // данных площадок не знает; тогда ведём себя как раньше и считаем товар
  // вайлдберрисовским.
  const someProductOnOzon = products.some((one) => (one.marketplaces ?? []).includes('ozon'))
  // Как назвать площадки в общих подписях окна. У продавца с одним только
  // Wildberries это по-прежнему «Wildberries», текст не меняется ни на букву.
  const placesLabel = manyMarketplaces
    ? `${MARKETPLACE_NAMES.wb} и ${MARKETPLACE_NAMES.ozon}`
    : MARKETPLACE_NAMES[groups[0]?.marketplace ?? 'wb']

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
          <PrimaryAction
            onClick={() => onSave(draft)}
            disabledReason={
              overAllocated
                ? draft.unitsMode
                  ? `По складам распределено ${unitsSum} шт, а свободно только ${base}`
                  : `В сумме по складам получается ${percentSum}% свободного остатка, а он у складов общий`
                : undefined
            }
            data-testid="fbs-stock-save"
          >
            Сохранить
          </PrimaryAction>
        </ActionGroup>
      }
    >
      <Stack spacing={2.5}>
        {/* Отказ сервера показываем здесь, а не наверху страницы: оператор
            смотрит в это окно и должен видеть, что именно не сошлось, не теряя
            уже введённого. */}
        {saveError ? <ErrorNotice testId="fbs-stock-error">{saveError}</ErrorNotice> : null}
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

        {noneServed ? (
          <WarningNotice testId="fbs-stock-none-served">
            {noWarehouses
              ? `Склады ${placesLabel} не загрузились. Выбор склада WMS появится здесь после загрузки хотя бы одного направления ${placesLabel}.`
              : `Ни один склад ${placesLabel} не выбран. Выберите ниже физический склад WMS хотя бы для одного направления — до этого доля не задаётся и остаток в ${placesLabel} не уйдёт.`}
          </WarningNotice>
        ) : null}

        <CheckboxInput
          label="Передавать остаток в Wildberries"
          checked={draft.publish}
          onChange={(publish) => setDraft((one) => ({
            ...one, publish,
            changedPublication: [...new Set([...(one.changedPublication ?? []), 'wb' as const])],
          }))}
          disabledReason={
            !served.some((one) => warehouseMarketplace(one) === 'wb') && !draft.publish
              ? 'Сначала выберите хотя бы один склад Wildberries' : undefined
          }
          testId="fbs-stock-publish"
        />
        <CheckboxInput
          label="Передавать остаток в Ozon"
          checked={draft.publishOzon ?? draft.publish}
          onChange={(publishOzon) => setDraft((one) => ({
            ...one, publishOzon,
            changedPublication: [...new Set([...(one.changedPublication ?? []), 'ozon' as const])],
          }))}
          disabledReason={
            !served.some((one) => warehouseMarketplace(one) === 'ozon')
              && !(draft.publishOzon ?? draft.publish)
              ? 'Сначала выберите хотя бы один склад Ozon' : undefined
          }
          testId="fbs-stock-publish-ozon"
        />

        {/* Режим. Доля хороша, когда остаток дышит: приехала партия — в кабинете
            стало больше само. Но если с продавцом согласована разбивка по
            направлениям в конкретных числах, в сетку кратных десяти процентов
            она не ложится, и тогда числа задаются руками. Квота при этом сама
            не растёт: приехала новая партия — числа прежние, пока их не
            поднимут. */}
        <CheckboxInput
          label="Остаток по штукам"
          checked={draft.unitsMode}
          onChange={(unitsMode) => setDraft((one) => ({ ...one, unitsMode }))}
          helperText={
            draft.unitsMode
              ? 'Доля отключена. Числа по складам не растут сами при приёмке — поднимайте руками'
              : 'Включите, чтобы задать количество по каждому складу числом, а не долей'
          }
          disabledReason={
            noneServed ? `Сначала выберите хотя бы один склад ${placesLabel}` : undefined
          }
          testId="fbs-stock-units-mode"
        />

        {draft.unitsMode ? (
          <Typography variant="body2" color="text.secondary" data-testid="fbs-stock-units-total">
            Задано по складам {unitsSum.toLocaleString('ru-RU')} шт при{' '}
            {base.toLocaleString('ru-RU')} свободных
            {overAllocated ? ' — это больше, чем есть на складе' : ''}
          </Typography>
        ) : null}

        <PercentSlider
          label="Доля свободного остатка"
          value={draft.percent}
          onChange={(percent) => setDraft((one) => ({ ...one, percent }))}
          disabled={noneServed || draft.unitsMode || (!single && !draft.sameEverywhere)}
          disabledReason={
            noneServed
              ? `Сначала выберите хотя бы один склад ${placesLabel}`
              : draft.unitsMode
                ? 'Включён остаток по штукам — количество задаётся числом под каждым складом'
                : 'Сейчас доля задаётся по каждому складу отдельно'
          }
          testId="fbs-stock-percent"
        />

        {single ? null : (
          <>
            <Divider />
            <CheckboxInput
              label="Одинаково по всем складам"
              checked={draft.sameEverywhere}
              onChange={(sameEverywhere) => setDraft((one) => ({ ...one, sameEverywhere }))}
              disabledReason={
                draft.unitsMode ? 'Включён остаток по штукам' : undefined
              }
              // Доля применяется к каждому складу отдельно, а не делится между
              // ними. Из старой подписи это не читалось, и оператор, поставив
              // «половину» на два склада, отдавал в WB весь остаток.
              helperText={`Доля уйдёт на КАЖДЫЙ из ${enabledServed.length} складов ${enabledPlacesLabel} — в сумме ${percentSum}%. Выключите, чтобы задать свою долю каждому`}
              testId="fbs-stock-same"
            />
          </>
        )}

        {overAllocated ? (
          <ErrorNotice testId="fbs-stock-over">
            {draft.unitsMode
              ? `По складам распределено ${unitsSum.toLocaleString('ru-RU')} шт, а свободно только ${base.toLocaleString('ru-RU')}. Товар лежит у нас один, а склады ${placesLabel} — это направления отгрузки: больше, чем есть, раздать нельзя.`
              : `В сумме по складам получается ${percentSum}% свободного остатка, а он у складов общий: товар лежит у нас один, а склады ${placesLabel} — это направления отгрузки. Больше 100% раздать нельзя, сервер такое правило не примет.`}
          </ErrorNotice>
        ) : null}

        {single || draft.sameEverywhere ? null : (
          <Typography variant="body2" color="text.secondary" data-testid="fbs-stock-rest">
            Нераспределено: {freePercent}%. Количество зависит от свободного остатка
            каждого физического склада WMS.
          </Typography>
        )}

        <Stack spacing={2}>
          {noWarehouses ? (
            <Typography color="text.secondary" data-testid="fbs-stock-no-warehouses">
              Нет направлений маркетплейсов, которые можно сопоставить со складом WMS.
            </Typography>
          ) : null}
          {/* Сто процентов — на все склады обеих площадок разом, а не на каждую
              отдельно: товар лежит у нас один. Сказать это надо один раз и до
              списка, иначе вторая площадка читается как второй остаток. */}
          {manyMarketplaces ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid="fbs-stock-shared-pool"
            >
              Общий лимит долей для обеих площадок — 100%. Количество для каждого
              направления рассчитывается по его физическому складу WMS.
            </Typography>
          ) : null}
          {groups.map((group) => (
            <Stack key={group.marketplace} spacing={2}>
              {manyMarketplaces ? (
                <Stack spacing={0.25}>
                  <Typography
                    variant="subtitle2"
                    data-testid={`fbs-stock-marketplace-${group.marketplace}`}
                  >
                    {MARKETPLACE_NAMES[group.marketplace]}
                  </Typography>
                  {group.marketplace === 'ozon' && !someProductOnOzon ? (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      data-testid="fbs-stock-ozon-unlinked"
                    >
                      Выбранный товар с карточкой Ozon не связан: туда с него ничего не
                      уедет, но склад всё равно считается в общих ста процентах.
                    </Typography>
                  ) : null}
                </Stack>
              ) : null}
              {/* Справочник кабинета не ответил. Причина нужна здесь, иначе
                  список складов Ozon выглядит просто коротким, и оператор идёт
                  искать несуществующую проблему у продавца. Уже сопоставленные
                  склады при этом остаются на месте — они взяты из привязок. */}
              {group.marketplace === 'ozon' && ozonWarehousesError ? (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  data-testid="fbs-stock-ozon-directory-error"
                >
                  {ozonWarehousesError}
                </Typography>
              ) : null}
              {group.warehouses.map((warehouse) => (
            <Stack key={warehouse.id} spacing={1}>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                {/* Галочка «обслуживаем» — свойство продавца, а не товара, но живёт
                    здесь же: оператор видит склады продавца именно в этом окне, и
                    гонять его на другой экран ради одной галки незачем. Она решает
                    сразу две вещи: чьи заказы наши и по каким складам раздаём
                    остаток. Снятая галка — склад чужого фулфилмента. */}
                <CheckboxInput
                  label={`Обслуживаем склад «${warehouse.name}»`}
                  checked={warehouse.fbsEnabled}
                  onChange={(checked) => onServedChange?.(warehouse.id, checked)}
                  disabledReason={
                    !onServedChange
                      ? 'Настройка доступна из каталога'
                      : warehouse.boundTo === null && !warehouse.fbsEnabled
                        ? 'Сначала выберите склад WMS'
                        : undefined
                  }
                  testId={`fbs-stock-served-${warehouse.id}`}
                />
                {!warehouse.fbsEnabled ? (
                  <StatusChip
                    label="не обслуживаем"
                    hint="Заказы с этого склада к нам не приходят, остаток на него не отправляется"
                  />
                ) : warehouse.boundTo === null ? (
                  <StatusChip
                    label="склад не сопоставлен"
                    tone="warn"
                    hint={`Пока направление ${MARKETPLACE_NAMES[warehouseMarketplace(warehouse)]} не сопоставлено с физическим складом WMS, остаток по нему не уйдёт`}
                  />
                ) : null}
                <Box sx={{ flexGrow: 1 }} />
                <Box sx={{ minWidth: 240 }}>
                  {/* У отключённого склада выбор заперт: сопоставление означает
                      «склад наш» и включило бы его обратно молча. Сначала галочка,
                      потом склад. */}
                  <SelectInput
                    label="Склад WMS"
                    value={warehouse.boundTo ?? ''}
                    onChange={(value) => onBind(warehouse.id, value)}
                    options={seller.wbWarehouses.map((one) => ({ value: one.id, label: one.name }))}
                    emptyLabel="не сопоставлен"
                    disabled={!warehouse.fbsEnabled && warehouse.boundTo !== null}
                    testId={`fbs-stock-bind-${warehouse.id}`}
                  />
                </Box>
              </Stack>
              {warehouse.fbsEnabled && draft.unitsMode ? (
                // Поле вместо ползунка. Максимум намеренно НЕ ставится: оператор
                // должен иметь возможность набрать больше и увидеть красное, а не
                // упереться в молча не принимающееся поле.
                <NumberInput
                  label="Потолок публикации, шт"
                  value={draft.unitsByWarehouse[warehouse.id] ?? 0}
                  onChange={(value) =>
                    setDraft((one) => ({
                      ...one,
                      unitsByWarehouse: {
                        ...one.unitsByWarehouse,
                        [warehouse.id]: Math.max(0, value ?? 0),
                      },
                    }))
                  }
                  min={0}
                  error={
                    overAllocated
                      ? `В сумме ${unitsSum} шт при свободных ${base}`
                      : undefined
                  }
                  helperText={
                    'Потолок публикации. В кабинет уйдёт не больше свободного остатка; число меняется только вручную'
                  }
                  testId={`fbs-stock-units-${warehouse.id}`}
                />
              ) : null}
              {warehouse.fbsEnabled && !single && !draft.unitsMode ? (
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
                          max={(draft.byWarehouse[warehouse.id] ?? 0) + freePercent}
                  disabled={draft.sameEverywhere}
                  disabledReason="Включено «одинаково по всем складам»"
                  testId={`fbs-stock-percent-${warehouse.id}`}
                />
              ) : null}
            </Stack>
              ))}
            </Stack>
          ))}
        </Stack>

        <Divider />

        <Stack spacing={0.5}>
          <Typography variant="h6" data-testid="fbs-stock-result">
            {savedPublished === undefined ? 'Расчёт публикации недоступен' : `${savedPublished.toLocaleString('ru-RU')} шт`}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {savedPublished === undefined
              ? 'Нет серверного расчёта по сохранённому правилу.'
              : 'Расчёт публикации по сохранённому правилу при последней загрузке.'}
            {' '}Изменения в этом окне ещё не учтены. После сохранения откройте правило
            снова: количество рассчитывается по каждому физическому складу WMS.
          </Typography>
        </Stack>

        {unbound.length > 0 && publishesAny ? (
          <Typography variant="body2" color="text.secondary">
            По складам {unbound.map((one) => one.name).join(', ')} остаток не уйдёт, пока они не
            сопоставлены с физическими складами WMS.
          </Typography>
        ) : null}
      </Stack>
    </AppDialog>
  )
}
