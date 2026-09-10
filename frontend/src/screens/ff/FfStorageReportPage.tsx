import { useEffect, useRef, useState } from 'react'
import { Box, Stack } from '@mui/material'
import {
  DataTable,
  ErrorNotice,
  FilterBar,
  MoneyCell,
  MoscowDateRangeInput,
  ReportMetricStrip,
  ScreenHeader,
  SecondaryAction,
  SelectInput,
  TextCell,
  type Column,
} from '../../ui-kit'
import { apiUrl } from '../../api'
import { sellerQuickRange } from './FfBillingScreen'

type Seller = { id: string; name: string }

type ReportProduct = {
  product_id: string
  sku: string | null
  product_name: string
  seller_article: string | null
  category: string | null
  volume_liters: string | null
  liter_days: string
  period_rate_kopecks: string | null
  current_rate_kopecks: number | null
  amount_kopecks: number | null
}

type ReportSeller = {
  seller_id: string
  seller_name: string
  liter_days: string
  amount_kopecks: number | null
  products: ReportProduct[]
}

type Report = {
  date_from: string
  date_to: string
  total_liter_days: string
  total_amount_kopecks: number | null
  sellers: ReportSeller[]
}

const EMPTY_REPORT: Report = {
  date_from: '',
  date_to: '',
  total_liter_days: '0',
  total_amount_kopecks: null,
  sellers: [],
}

const QUICK_PERIODS = [
  ['today', 'Сегодня'],
  ['seven_days', '7 дней'],
  ['thirty_days', '30 дней'],
  ['current_month', 'Этот месяц'],
  ['previous_month', 'Прошлый месяц'],
] as const

const decimal = (value: string | null | undefined, digits: number) => {
  const parsed = Number(value)
  if (value == null || !Number.isFinite(parsed)) return '—'
  return parsed.toLocaleString('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/**
 * Отчёт хранения за период: селлеры, по раскрытию — их товары.
 *
 * Экран ничего не считает: литро-дни и деньги берутся из ночных начислений за
 * хранение — тех же проводок, из которых собрана плашка хранения на «Расчётах»
 * и счёт селлеру. Поэтому цифра здесь не может разойтись с выставленной.
 *
 * Страница намеренно плоская: обмеры, ставки, история габаритов и печать живут
 * на экране «Хранение». Отчёт отвечает на один вопрос — сколько и на сколько
 * лежало, — и второй операционки на нём нет.
 */
export function FfStorageReportPage({ token, sellers = [] }: { token: string; sellers?: Seller[] }) {
  const today = sellerQuickRange('today').start
  // Начисление за сутки пишет ночная задача, поэтому на «сегодня» отчёт почти
  // всегда пуст. Месяц назад — первый период, на котором экран сразу показывает
  // работу склада, а не пустую таблицу.
  const [range, setRange] = useState(() => sellerQuickRange('thirty_days', today))
  const [sellerId, setSellerId] = useState('all')
  const [category, setCategory] = useState('')
  const [categories, setCategories] = useState<string[]>([])
  const [report, setReport] = useState<Report>(EMPTY_REPORT)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedSeller, setExpandedSeller] = useState<string | null>(null)
  const requestId = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch(apiUrl('/products/categories'), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('categories')
        return response.json() as Promise<string[]>
      })
      .then(setCategories)
      .catch(() => undefined)
    return () => controller.abort()
  }, [token])

  useEffect(() => {
    const controller = new AbortController()
    const currentRequest = ++requestId.current
    setLoading(true)
    setError(null)
    setExpandedSeller(null)
    const params = new URLSearchParams({ date_from: range.start, date_to: range.end })
    if (sellerId !== 'all') params.set('seller_id', sellerId)
    if (category) params.set('category', category)
    fetch(apiUrl(`/operations/storage/report?${params}`), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status))
        return response.json() as Promise<Report>
      })
      .then((data) => {
        if (currentRequest === requestId.current) setReport(data)
      })
      .catch((reason: unknown) => {
        if (currentRequest !== requestId.current || (reason as Error).name === 'AbortError') return
        setReport(EMPTY_REPORT)
        setError(
          (reason as Error).message === '422'
            ? 'Период задан неверно: проверьте даты, он не может быть в будущем и длиннее года.'
            : 'Не удалось загрузить отчёт хранения. Повторите попытку.',
        )
      })
      .finally(() => {
        if (currentRequest === requestId.current) setLoading(false)
      })
    return () => controller.abort()
  }, [category, range, sellerId, token])

  const sellerColumns: Column<ReportSeller>[] = [
    {
      key: 'seller',
      header: 'Селлер',
      width: 320,
      render: (row) => <TextCell value={row.seller_name} width={300} />,
    },
    {
      key: 'liter-days',
      header: 'Литро-дни',
      width: 160,
      align: 'right',
      render: (row) => decimal(row.liter_days, 2),
    },
    {
      key: 'amount',
      header: 'Сумма хранения',
      width: 180,
      align: 'right',
      render: (row) => <MoneyCell minor={row.amount_kopecks} />,
    },
  ]

  const productColumns: Column<ReportProduct>[] = [
    {
      key: 'product',
      header: 'Товар',
      render: (row) => <TextCell value={row.product_name} width={260} />,
    },
    { key: 'sku', header: 'SKU', width: 150, render: (row) => <TextCell value={row.sku} width={140} /> },
    {
      key: 'article',
      header: 'Артикул продавца',
      width: 170,
      render: (row) => <TextCell value={row.seller_article} width={155} />,
    },
    {
      key: 'volume',
      header: 'Объём, л',
      width: 100,
      align: 'right',
      render: (row) => decimal(row.volume_liters, 2),
    },
    {
      key: 'liter-days',
      header: 'Литро-дни',
      width: 120,
      align: 'right',
      render: (row) => decimal(row.liter_days, 2),
    },
    // Ставка за период — фактическая: начисленные деньги на начисленный литро-день.
    // Если внутри периода ставку меняли, заведённой «ставки периода» не
    // существует, а эта сходится с суммой в строке.
    {
      key: 'period-rate',
      header: 'Ставка за период, ₽/л·д.',
      width: 175,
      align: 'right',
      render: (row) => <MoneyCell minor={row.period_rate_kopecks} />,
    },
    {
      key: 'current-rate',
      header: 'Текущая ставка, ₽/л·д.',
      width: 175,
      align: 'right',
      render: (row) => <MoneyCell minor={row.current_rate_kopecks} muted />,
    },
    {
      key: 'amount',
      header: 'Сумма, ₽',
      width: 140,
      align: 'right',
      render: (row) => <MoneyCell minor={row.amount_kopecks} />,
    },
  ]

  return (
    <Box data-testid="ff-storage-report-page" sx={{ width: '100%', maxWidth: '100%', minWidth: 0 }}>
      <ScreenHeader
        title="Отчёт хранения"
        purpose="Литро-дни и стоимость хранения за выбранный период по ночным начислениям."
      />
      <FilterBar testId="storage-report-filter-bar">
        <>
          <MoscowDateRangeInput
            label="Период"
            startLabel="с"
            endLabel="по"
            value={range}
            onChange={(value) => setRange({ start: value.start ?? today, end: value.end ?? today })}
            maxDate={today}
            maxDays={366}
            testId="storage-report-range"
          />
          <Stack
            direction="row"
            spacing={0.5}
            sx={{ flexWrap: 'wrap', alignSelf: { sm: 'flex-end' }, pb: { sm: 0.25 } }}
            aria-label="Быстрый период"
          >
            {QUICK_PERIODS.map(([period, label]) => (
              <SecondaryAction key={period} onClick={() => setRange(sellerQuickRange(period, today))}>
                {label}
              </SecondaryAction>
            ))}
          </Stack>
        </>
        <SelectInput
          label="Селлер"
          value={sellerId}
          onChange={setSellerId}
          options={[
            { value: 'all', label: 'Все селлеры' },
            ...sellers.map((seller) => ({ value: seller.id, label: seller.name })),
          ]}
          testId="storage-report-seller"
        />
        <SelectInput
          label="Категория"
          value={category}
          onChange={setCategory}
          emptyLabel="Все категории"
          options={categories.map((name) => ({ value: name, label: name }))}
          testId="storage-report-category"
        />
      </FilterBar>
      {error ? <ErrorNotice testId="storage-report-error">{error}</ErrorNotice> : null}
      <ReportMetricStrip
        items={[
          {
            key: 'liter_days',
            label: 'Хранение',
            value: Math.round(Number(report.total_liter_days)),
            unit: 'л·дн',
          },
          {
            key: 'amount',
            label: 'Стоимость хранения',
            moneyMinor: report.total_amount_kopecks,
          },
        ]}
        loading={loading}
        testId="storage-report-metrics"
      />
      <DataTable
        columns={sellerColumns}
        rows={report.sellers}
        getRowKey={(row) => row.seller_id}
        loading={loading}
        testId="storage-report-sellers"
        empty={{
          title: 'За выбранный период хранение не начислялось',
          hint: 'Измените период или фильтры. Начисление за сутки пишет ночная задача.',
        }}
        expand={{
          isExpanded: (row) => row.seller_id === expandedSeller,
          label: (row) => `Показать товары селлера ${row.seller_name}`,
          onToggle: (row) =>
            setExpandedSeller((current) => (current === row.seller_id ? null : row.seller_id)),
          render: (row) => (
            <DataTable
              columns={productColumns}
              rows={row.products}
              getRowKey={(product) => product.product_id}
              fixedLayout
              testId={`storage-report-products-${row.seller_id}`}
              empty={{ title: 'По товарам этого селлера начислений в периоде нет' }}
            />
          ),
        }}
      />
    </Box>
  )
}
