import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiUrl } from '../../api'
import {
  ActionGroup,
  DataTable,
  ErrorNotice,
  MoscowDateTimeInput,
  NumberInput,
  PrimaryAction,
  SecondaryAction,
  SelectInput,
  StatusChip,
} from '../../ui-kit'
import type { Column } from '../../ui-kit'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Unit = 'item' | 'document'
type TariffServiceState = { service_code: string; enabled: boolean; unit: Unit | null; rate: number | null; valid_from_at: string | null }
type TariffVersion = {
  seller_id: string | null
  product_id: string | null
  employee_user_id: string | null
  service_code: string
  unit: Unit
  enabled: boolean
  rate: number
  valid_from_at: string
  valid_to_at: string | null
}
type ProductOption = { id: string; seller_id: string | null; name: string; sku: string; seller_name: string | null; label: string }
type TariffMatrix = { revision: number; services: TariffServiceState[]; versions: TariffVersion[]; products: ProductOption[]; storage: { mode: string; editable_in_matrix: boolean } }
type Employee = { id: string; email: string; packaging_rate_rub?: string }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  focusTariffs: boolean
  onSaved: () => void
  employees?: Employee[]
}

const MAX_TARIFF_RATE_KOPECKS = 2_147_483_647
const MAX_TARIFF_RATE_RUBLES = MAX_TARIFF_RATE_KOPECKS / 100
const RATE_VALIDATION_MESSAGE = 'Ставка указывается в рублях, не более 21 474 836,47 ₽ и двух знаков после запятой.'
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
  return rubleFormatter.format(rate)
}

function formatMoscowDate(value: string) {
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) return '—'
  const parts = Object.fromEntries(
    moscowDateFormatter
      .formatToParts(instant)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]),
  )
  return `${parts.day}.${parts.month}.${parts.year}, ${parts.hour}:${parts.minute}`
}

function rublesFromKopecks(rate: number | null) {
  return rate == null ? null : rate / 100
}

function kopecksFromRubles(rate: number | null) {
  if (rate == null) return null
  const calculatedKopecks = rate * 100
  const kopecks = Math.round(calculatedKopecks)
  // NumberInput gives us an IEEE-754 number: 0.29 * 100 can be
  // 28.999999999999996.  Accept only that representation noise, never a real
  // third decimal such as 33.501.
  return (
    Number.isSafeInteger(kopecks)
    && kopecks >= 0
    && kopecks <= MAX_TARIFF_RATE_KOPECKS
    && Math.abs(calculatedKopecks - kopecks) < 1e-8
  )
    ? kopecks
    : null
}

function matrixForDisplay(matrix: TariffMatrix): TariffMatrix {
  return {
    ...matrix,
    services: matrix.services.map((service) => ({ ...service, rate: rublesFromKopecks(service.rate) })),
    versions: matrix.versions.map((version) => ({ ...version, rate: version.rate / 100 })),
  }
}

function matrixForSave(matrix: TariffMatrix) {
  if (
    matrix.services.some((service) => service.rate != null && kopecksFromRubles(service.rate) == null) ||
    matrix.versions.some((version) => kopecksFromRubles(version.rate) == null)
  ) return null
  const services = matrix.services.map((service) => ({
    ...service,
    rate: kopecksFromRubles(service.rate),
  }))
  const versions = matrix.versions.map((version) => ({
    ...version,
    rate: kopecksFromRubles(version.rate),
  }))
  return { revision: matrix.revision, services, versions }
}

const serviceName: Record<string, string> = {
  inbound: 'Приёмка', marketplace_outbound: 'Отгрузка', packing: 'Упаковка', return: 'Возврат', picking: 'Комплектация',
}
const employeeServices = ['inbound', 'picking', 'marketplace_outbound', 'return']
const employeeServiceName: Record<string, string> = { ...serviceName, picking: 'Подбор' }
const defaultStartsAt = () => new Date().toISOString().replace(/:\d{2}\.\d{3}Z$/, ':00Z')

export function humanTariffMatrixError(message: string) {
  if (message.trim() === 'billing_tariff_matrix_stale_revision') {
    return 'Конфигурация тарифов уже изменилась. Обновите данные и повторите сохранение.'
  }
  return message
}

function nextVersionStart() {
  return defaultStartsAt()
}

function replaceVersion(versions: TariffVersion[], next: TariffVersion) {
  const sameScope = (item: TariffVersion) => item.service_code === next.service_code && item.seller_id === next.seller_id &&
    item.product_id === next.product_id && item.employee_user_id === next.employee_user_id && item.valid_from_at === next.valid_from_at
  const previous = versions.filter((item) => !sameScope(item))
  return [...previous, next]
}

export function FfBillingTariffMatrixPanel({ token, authHeaders, focusTariffs, onSaved, employees = [] }: Props) {
  const [matrix, setMatrix] = useState<TariffMatrix | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [productId, setProductId] = useState('')
  const [productService, setProductService] = useState('inbound')
  const [productRate, setProductRate] = useState<number | null>(null)
  const [productStart, setProductStart] = useState<string | null>(defaultStartsAt())
  const anchorRef = useRef<HTMLElement>(null)

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(apiUrl('/billing/tariff-matrix'), { headers: authHeaders(token) })
      if (!response.ok) throw new Error(humanTariffMatrixError(await readApiErrorMessage(response)))
      setMatrix(matrixForDisplay((await response.json()) as TariffMatrix))
      setDirty(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить тарифы.')
    } finally {
      setLoading(false)
    }
  }, [authHeaders, token])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (!focusTariffs) return
    anchorRef.current?.scrollIntoView({ block: 'start' })
    anchorRef.current?.focus()
  }, [focusTariffs, loading, matrix])

  function mutate(change: (current: TariffMatrix) => TariffMatrix) {
    setMatrix((current) => current ? change(current) : current)
    setDirty(true)
    setSaved(false)
  }

  function setService(row: TariffServiceState, patch: Partial<TariffServiceState>) {
    mutate((current) => {
      const changesPricing = patch.rate !== undefined || patch.unit !== undefined
      const start = patch.valid_from_at ?? (changesPricing ? nextVersionStart() : row.valid_from_at ?? defaultStartsAt())
      const nextRow = { ...row, ...patch, valid_from_at: start }
      const unit = nextRow.unit ?? 'item'
      const rate = nextRow.rate ?? 0
      const version: TariffVersion = {
        seller_id: null, product_id: null, employee_user_id: null, service_code: row.service_code,
        unit, enabled: nextRow.enabled, rate, valid_from_at: start, valid_to_at: null,
      }
      return {
        ...current,
        services: current.services.map((item) => item.service_code === row.service_code ? nextRow : item),
        versions: replaceVersion(current.versions, version),
      }
    })
  }

  function addProductOverride() {
    const product = matrix?.products.find((item) => item.id === productId)
    const service = matrix?.services.find((item) => item.service_code === productService)
    if (!matrix || !product || !product.seller_id || productRate == null || !productStart) {
      setError('Для товарной цены выберите товар, ставку и время Москвы.')
      return
    }
    if (service?.unit !== 'item') {
      setError('Товарная цена доступна только для тарифа за единицу.')
      return
    }
    mutate((current) => ({
      ...current,
      versions: replaceVersion(current.versions, {
        seller_id: product.seller_id, product_id: product.id, employee_user_id: null, service_code: productService,
        unit: 'item', enabled: true, rate: productRate, valid_from_at: productStart, valid_to_at: null,
      }),
    }))
    setError(null)
  }

  function setEmployeeRate(employeeId: string, serviceCode: string, rate: number | null) {
    if (rate == null) return
    mutate((current) => ({
      ...current,
      versions: replaceVersion(current.versions, {
        seller_id: null, product_id: null, employee_user_id: employeeId, service_code: serviceCode,
        unit: 'item', enabled: true, rate, valid_from_at: defaultStartsAt(), valid_to_at: null,
      }),
    }))
  }

  async function save() {
    if (!matrix) return
    if ([...anchorRef.current?.querySelectorAll<HTMLInputElement>('input[type="number"]') ?? []]
      .some((input) => input.validity.rangeOverflow)) {
      setError(RATE_VALIDATION_MESSAGE)
      return
    }
    const payload = matrixForSave(matrix)
    if (!payload) {
      setError(RATE_VALIDATION_MESSAGE)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const response = await fetch(apiUrl('/billing/tariff-matrix'), {
        method: 'PUT',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(humanTariffMatrixError(await readApiErrorMessage(response)))
      setMatrix(matrixForDisplay((await response.json()) as TariffMatrix))
      setDirty(false)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить тарифы.')
    } finally {
      setSaving(false)
    }
  }

  const productRows = matrix?.versions.filter((item) => item.product_id != null) ?? []
  const productById = new Map((matrix?.products ?? []).map((product) => [product.id, product]))
  const productOverrideAllowed = (matrix?.services.find((service) => service.service_code === productService)?.unit ?? 'item') === 'item'
  const employeeRows = useMemo(() => {
    const known = new Map(employees.map((employee) => [employee.id, employee]))
    matrix?.versions.filter((item) => item.employee_user_id).forEach((item) => {
      if (item.employee_user_id && !known.has(item.employee_user_id)) known.set(item.employee_user_id, { id: item.employee_user_id, email: item.employee_user_id })
    })
    return [...known.values()]
  }, [employees, matrix?.versions])

  const serviceColumns: Column<TariffServiceState>[] = [
    { key: 'service', header: 'Услуга', width: 150, render: (row) => serviceName[row.service_code] ?? row.service_code },
    { key: 'basis', header: 'Считается', width: 150, render: (row) => row.unit === 'document' ? 'За документ' : 'За единицу' },
    { key: 'unit', header: 'Единица', width: 170, render: (row) => <SelectInput label="Единица" value={row.unit ?? 'item'} onChange={(value) => setService(row, { unit: value as Unit })} options={[{ value: 'item', label: 'За единицу' }, { value: 'document', label: 'За документ' }]} disabled={saving} testId={`ff-settings-tariff-unit-${row.service_code}`} /> },
    { key: 'rate', header: 'Ставка, ₽', width: 150, align: 'right', render: (row) => <NumberInput label="Ставка" value={row.rate} onChange={(value) => setService(row, { rate: value })} min={0} max={MAX_TARIFF_RATE_RUBLES} step={0.01} disabled={saving} testId={`ff-settings-tariff-rate-${row.service_code}`} /> },
    { key: 'start', header: 'Действует с', width: 205, render: (row) => <MoscowDateTimeInput label="Начало" value={row.valid_from_at} onChange={(value) => value && setService(row, { valid_from_at: value })} disabled={saving} testId={`ff-settings-tariff-start-${row.service_code}`} /> },
    { key: 'products', header: 'Товарные цены', width: 150, align: 'right', render: (row) => productRows.filter((item) => item.service_code === row.service_code).length || '—' },
    { key: 'state', header: 'Состояние', width: 155, render: (row) => <StatusChip label={row.enabled ? 'Тарифицируется' : 'Не тарифицируется'} tone={row.enabled ? 'ok' : 'neutral'} testId={`ff-settings-tariff-state-${row.service_code}`} /> },
    { key: 'action', header: 'Действие', width: 145, render: (row) => <SecondaryAction aria-pressed={row.enabled} disabledReason={saving ? 'Матрица тарифов сохраняется' : undefined} onClick={() => setService(row, { enabled: !row.enabled })} data-testid={`ff-settings-tariff-${row.service_code}`}>{row.enabled ? 'Выключить' : 'Включить'}</SecondaryAction> },
  ]
  const productColumns: Column<TariffVersion>[] = [
    { key: 'product', header: 'Товар', width: 280, render: (row) => productById.get(row.product_id ?? '')?.label ?? 'Товар недоступен' },
    { key: 'seller', header: 'Селлер', width: 220, render: (row) => productById.get(row.product_id ?? '')?.seller_name ?? 'Селлер недоступен' },
    { key: 'service', header: 'Услуга', width: 160, render: (row) => serviceName[row.service_code] ?? row.service_code },
    { key: 'rate', header: 'Ставка, ₽', align: 'right', width: 140, render: (row) => formatRubles(row.rate) },
    { key: 'start', header: 'Действует с', width: 205, render: (row) => formatMoscowDate(row.valid_from_at) },
  ]
  const employeeColumns: Column<Employee>[] = [
    { key: 'employee', header: 'Сотрудник', width: 260, render: (row) => row.email },
    ...employeeServices.map((serviceCode): Column<Employee> => ({ key: serviceCode, header: employeeServiceName[serviceCode], align: 'right', width: 160, render: (row) => <NumberInput label={employeeServiceName[serviceCode]} value={matrix?.versions.find((item) => item.employee_user_id === row.id && item.service_code === serviceCode)?.rate ?? null} onChange={(value) => setEmployeeRate(row.id, serviceCode, value)} min={0} max={MAX_TARIFF_RATE_RUBLES} step={0.01} disabled={saving} testId={`ff-settings-tariff-employee-${row.id}-${serviceCode}`} /> })),
    { key: 'packing', header: 'Упаковка', width: 200, render: (row) => row.packaging_rate_rub != null ? `Ставка сотрудника: ${row.packaging_rate_rub} ₽` : 'Ставка — в карточке сотрудника' },
  ]

  return (
    <section
      ref={anchorRef}
      id="ff-settings-tariffs-panel"
      tabIndex={-1}
      data-testid="ff-settings-tariffs-panel"
      style={{ boxSizing: 'border-box', contain: 'inline-size', minWidth: 0, width: '100%', maxWidth: '100%' }}
    >
      <h2>Тарифы</h2>
      {error ? <ErrorNotice testId="ff-settings-tariffs-error">{error}</ErrorNotice> : null}
      {saved ? <StatusChip label="Матрица сохранена" tone="ok" testId="ff-settings-tariffs-success" /> : null}
      <DataTable columns={serviceColumns} rows={matrix?.services ?? []} getRowKey={(row) => row.service_code} loading={loading} empty={{ title: 'Тарифы пока не настроены', hint: 'Сначала загрузите матрицу тарифов.' }} testId="ff-settings-tariffs-services" />
      <h3>Товарные цены</h3>
      <SelectInput label="Товар" value={productId} onChange={setProductId} options={(matrix?.products ?? []).map((product) => ({ value: product.id, label: product.label }))} emptyLabel="Выберите товар" disabled={saving} testId="ff-settings-tariff-product-id" />
      <SelectInput label="Услуга для товара" value={productService} onChange={setProductService} options={(matrix?.services ?? []).map((service) => ({ value: service.service_code, label: serviceName[service.service_code] ?? service.service_code }))} disabled={saving} testId="ff-settings-tariff-product-service" />
      <NumberInput label="Товарная ставка, ₽" value={productRate} onChange={setProductRate} min={0} max={MAX_TARIFF_RATE_RUBLES} step={0.01} disabled={saving} testId="ff-settings-tariff-product-rate" />
      <MoscowDateTimeInput label="Товарная цена действует с" value={productStart} onChange={setProductStart} disabled={saving} testId="ff-settings-tariff-product-start" />
      {!productOverrideAllowed ? <StatusChip label="Товарная цена доступна только для тарифа за единицу" tone="warn" testId="ff-settings-tariff-product-unit-boundary" /> : null}
      <ActionGroup><SecondaryAction disabledReason={saving ? 'Матрица тарифов сохраняется' : !productOverrideAllowed ? 'Для товарной цены выберите единицу «За единицу»' : undefined} onClick={addProductOverride} data-testid="ff-settings-tariff-product-add">Добавить товарную цену</SecondaryAction></ActionGroup>
      <DataTable columns={productColumns} rows={productRows} getRowKey={(row) => `${row.product_id}-${row.service_code}-${row.valid_from_at}`} loading={loading} empty={{ title: 'Товарных цен пока нет', hint: 'Добавьте ставку для товара, если она отличается от общей.' }} testId="ff-settings-tariff-product-overrides" />
      <h3>Ставки сотрудников</h3>
      <DataTable columns={employeeColumns} rows={employeeRows} getRowKey={(row) => row.id} loading={loading} empty={{ title: 'Сотрудников пока нет', hint: 'Ставки появятся после добавления сотрудников.' }} testId="ff-settings-tariff-employee-rates" />
      <h3>Хранение</h3>
      <StatusChip label="Отдельно" tone="neutral" testId="ff-settings-tariff-storage-state" />
      <a href="/app/ff/inventory" data-testid="ff-settings-tariff-storage-link">Открыть суточное хранение</a>
      <ActionGroup><PrimaryAction disabledReason={saving || !matrix || !dirty ? 'Нет несохранённых изменений' : undefined} onClick={() => void save()} data-testid="ff-settings-tariffs-save">{saving ? 'Сохранение' : 'Сохранить матрицу'}</PrimaryAction></ActionGroup>
    </section>
  )
}
