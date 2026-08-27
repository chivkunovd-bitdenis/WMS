import { useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import {
  DataTable,
  MoscowDateTimeInput,
  NumberInput,
  SecondaryAction,
  StatusChip,
  SelectInput,
  TextCell,
} from '../../ui-kit'
import type { Column } from '../../ui-kit'

export type SellerOption = { id: string; name: string }
export type ProductOption = {
  id: string
  seller_id: string | null
  name: string
  sku: string
  seller_name: string | null
  label: string
}
export type TariffVersionRow = {
  seller_id: string | null
  product_id: string | null
  employee_user_id: string | null
  service_code: string
  rate: number
  valid_from_at: string
  valid_to_at?: string | null
}

type RateState = 'active' | 'superseded' | 'planned'

/**
 * Состояние каждой версии ставки внутри своей области.
 *
 * Область — это пара «на что» + услуга: ставка селлера на приёмку и цена того
 * же селлера на приёмку конкретного товара живут отдельно и обе действуют, а
 * перебивает одна другую уже при расчёте. Внутри одной области действует
 * последняя версия, начавшаяся не позже сейчас; всё, что раньше неё, перебито.
 * Версия с будущей датой ещё не вступила в силу — это не то же самое, что
 * перебитая, и называть её «не действует» было бы враньём.
 */
export function withRateState(
  rows: TariffVersionRow[],
  now: Date,
): Array<TariffVersionRow & { state: RateState }> {
  const scope = (row: TariffVersionRow) => `${row.product_id ?? 'all'}::${row.service_code}`
  const activeStart = new Map<string, number>()
  for (const row of rows) {
    const startedAt = new Date(row.valid_from_at).getTime()
    if (startedAt > now.getTime()) continue
    if (row.valid_to_at && new Date(row.valid_to_at).getTime() <= now.getTime()) continue
    const key = scope(row)
    if (!activeStart.has(key) || startedAt > (activeStart.get(key) as number)) {
      activeStart.set(key, startedAt)
    }
  }
  return rows.map((row) => {
    const startedAt = new Date(row.valid_from_at).getTime()
    if (startedAt > now.getTime()) return { ...row, state: 'planned' as const }
    const active = activeStart.get(scope(row))
    return { ...row, state: active === startedAt ? ('active' as const) : ('superseded' as const) }
  })
}

/** Действующие — внизу: оператор ищет глазами то, что применяется сейчас. */
const STATE_ORDER: Record<RateState, number> = { superseded: 0, planned: 1, active: 2 }

export function sortRateRows<T extends { state: RateState; valid_from_at: string }>(rows: T[]): T[] {
  return [...rows].sort(
    (a, b) =>
      STATE_ORDER[a.state] - STATE_ORDER[b.state] ||
      new Date(a.valid_from_at).getTime() - new Date(b.valid_from_at).getTime(),
  )
}

const rubleFormatter = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const moscowDateFormatter = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

function formatRubles(rate: number) {
  // Панель переводит копейки в рубли один раз при загрузке матрицы
  // (`version.rate / 100`), поэтому здесь делить ещё раз нельзя: ставка 77,50 ₽
  // превращалась в 0,78 ₽.
  return rubleFormatter.format(rate)
}

function formatMoscowDate(value: string) {
  return moscowDateFormatter.format(new Date(value))
}

/**
 * Ставки одного селлера: его собственные ставки по услугам и его товарные цены.
 *
 * Раскрывается под строкой самого селлера. Плоские секции с выпадающим списком
 * селлера читались как «настройки вообще», и было непонятно, чьи это ставки;
 * здесь принадлежность видна из того, под чьей строкой лежит форма.
 */
function SellerRatesDetails({
  seller,
  services,
  products,
  versions,
  saving,
  onAddSellerRate,
  onAddProductRate,
  serviceName,
  defaultStartsAt,
  maxRate,
}: {
  seller: SellerOption
  services: Array<{ service_code: string; unit: 'item' | 'document' | null }>
  products: ProductOption[]
  versions: TariffVersionRow[]
  saving: boolean
  onAddSellerRate: (input: { sellerId: string; serviceCode: string; rate: number; startsAt: string }) => void
  onAddProductRate: (input: { productId: string; serviceCode: string; rate: number; startsAt: string }) => void
  serviceName: Record<string, string>
  defaultStartsAt: () => string
  maxRate: number
}) {
  // «Все товары» — это ставка самого селлера, конкретный товар — цена на товар.
  // Раздельные формы под каждый случай давали внутри одной раскрывашки два
  // заголовка, две таблицы и восемь полей; для оператора это одно действие.
  const ALL_PRODUCTS = ''
  const [target, setTarget] = useState(ALL_PRODUCTS)
  const [service, setService] = useState(services[0]?.service_code ?? 'inbound')
  const [rate, setRate] = useState<number | null>(null)
  const [startsAt, setStartsAt] = useState<string | null>(defaultStartsAt())

  const sellerProducts = products.filter((product) => product.seller_id === seller.id)
  const productById = new Map(sellerProducts.map((product) => [product.id, product]))
  const productLabel = (product: ProductOption) =>
    [product.sku, product.name].filter(Boolean).join(' · ')

  const rows = sortRateRows(
    withRateState(
      versions.filter((row) => row.seller_id === seller.id && row.employee_user_id == null),
      new Date(),
    ),
  )
  const unitAllowsProduct =
    (services.find((item) => item.service_code === service)?.unit ?? 'item') === 'item'
  const label = (code: string) => serviceName[code] ?? code

  type Row = (typeof rows)[number]
  const columns: Column<Row>[] = [
    {
      key: 'state',
      header: '',
      width: 130,
      // Подпись только у действующей строки. Придумывать слово для остальных
      // незачем: дата в соседней колонке сама говорит, прошлая она или будущая,
      // а лишний ярлык на каждой строке — шум.
      render: (row) => (row.state === 'active' ? <StatusChip label="✓ Действует" tone="ok" /> : null),
    },
    {
      key: 'target',
      header: 'На что',
      width: 300,
      render: (row) => (
        <TextCell
          value={
            row.product_id == null
              ? 'Все товары'
              : (() => {
                  const product = productById.get(row.product_id)
                  return product ? productLabel(product) : 'Товар недоступен'
                })()
          }
          width={280}
        />
      ),
    },
    { key: 'service', header: 'Услуга', width: 190, render: (row) => <TextCell value={label(row.service_code)} /> },
    {
      key: 'rate',
      header: 'Ставка, ₽',
      width: 160,
      align: 'right',
      render: (row) => <TextCell value={formatRubles(row.rate)} />,
    },
    {
      key: 'start',
      header: 'Действует с',
      width: 210,
      render: (row) => <TextCell value={formatMoscowDate(row.valid_from_at)} />,
    },
  ]

  const blockedReason = saving
    ? 'Матрица тарифов сохраняется'
    : rate == null || !startsAt
      ? 'Укажите ставку и время начала'
      : target !== ALL_PRODUCTS && !unitAllowsProduct
        ? 'Цена на товар возможна только когда услуга считается за единицу'
        : undefined

  return (
    <Box sx={{ px: 2, py: 1.5 }} data-testid={`ff-settings-tariff-seller-panel-${seller.id}`}>
      <Stack spacing={1.5}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1.5}
          sx={{ alignItems: { md: 'center' }, flexWrap: 'wrap' }}
        >
          <SelectInput
            label="На что"
            value={target}
            onChange={setTarget}
            options={[
              { value: ALL_PRODUCTS, label: 'Все товары' },
              ...sellerProducts.map((product) => ({ value: product.id, label: productLabel(product) })),
            ]}
            disabled={saving}
            testId={`ff-settings-tariff-target-${seller.id}`}
          />
          <SelectInput
            label="Услуга"
            value={service}
            onChange={setService}
            options={services.map((item) => ({ value: item.service_code, label: label(item.service_code) }))}
            disabled={saving}
            testId={`ff-settings-tariff-service-${seller.id}`}
          />
          <NumberInput
            label="Ставка, ₽"
            value={rate}
            onChange={setRate}
            min={0}
            max={maxRate}
            step={0.01}
            disabled={saving}
            testId={`ff-settings-tariff-rate-${seller.id}`}
          />
          <MoscowDateTimeInput
            label="Действует с"
            value={startsAt}
            onChange={setStartsAt}
            disabled={saving}
            testId={`ff-settings-tariff-start-${seller.id}`}
          />
          <SecondaryAction
            disabledReason={blockedReason}
            onClick={() => {
              if (rate == null || !startsAt) return
              if (target === ALL_PRODUCTS) {
                onAddSellerRate({ sellerId: seller.id, serviceCode: service, rate, startsAt })
                return
              }
              onAddProductRate({ productId: target, serviceCode: service, rate, startsAt })
            }}
            data-testid={`ff-settings-tariff-add-${seller.id}`}
          >
            Добавить
          </SecondaryAction>
        </Stack>
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => `${row.product_id ?? 'all'}-${row.service_code}-${row.valid_from_at}`}
          empty={{ title: 'Своих ставок нет', hint: 'Селлер считается по общим ставкам.' }}
          testId={`ff-settings-tariff-seller-own-${seller.id}`}
        />
      </Stack>
    </Box>
  )
}

export function FfBillingTariffSellerRates({
  sellers,
  products,
  services,
  versions,
  loading,
  saving,
  expandedSellerId,
  onToggleSeller,
  onAddSellerRate,
  onAddProductRate,
  serviceName,
  defaultStartsAt,
  maxRate,
}: {
  sellers: SellerOption[]
  products: ProductOption[]
  services: Array<{ service_code: string; unit: 'item' | 'document' | null }>
  versions: TariffVersionRow[]
  loading: boolean
  saving: boolean
  expandedSellerId: string | null
  onToggleSeller: (sellerId: string) => void
  onAddSellerRate: (input: { sellerId: string; serviceCode: string; rate: number; startsAt: string }) => void
  onAddProductRate: (input: { productId: string; serviceCode: string; rate: number; startsAt: string }) => void
  serviceName: Record<string, string>
  defaultStartsAt: () => string
  maxRate: number
}) {

  const columns: Column<SellerOption>[] = [
    {
      key: 'seller',
      header: 'Селлер',
      render: (row) => (
        <Typography sx={{ fontWeight: 600 }}>{row.name}</Typography>
      ),
    },
  ]

  return (
    <DataTable
      columns={columns}
      rows={sellers}
      getRowKey={(row) => row.id}
      loading={loading}
      testId="ff-settings-tariff-sellers"
      hideHeader
      empty={{ title: 'Селлеров пока нет', hint: 'Добавьте селлера, чтобы задать ему свою ставку.' }}
      expand={{
        isExpanded: (row) => row.id === expandedSellerId,
        onToggle: (row) => onToggleSeller(row.id),
        label: (row) => `Показать ставки селлера ${row.name}`,
        render: (row) => (
          <SellerRatesDetails
            seller={row}
            services={services}
            products={products}
            versions={versions}
            saving={saving}
            onAddSellerRate={onAddSellerRate}
            onAddProductRate={onAddProductRate}
            serviceName={serviceName}
            defaultStartsAt={defaultStartsAt}
            maxRate={maxRate}
          />
        ),
      }}
    />
  )
}
