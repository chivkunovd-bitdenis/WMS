import { useCallback, useEffect, useMemo, useState } from 'react'
import { Box, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Radio, RadioGroup, Stack, TextField, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import HistoryOutlinedIcon from '@mui/icons-material/HistoryOutlined'
import { apiUrl } from '../../api'
import { ActionGroup, DataTable, ErrorNotice, FilterBar, IconAction, PrimaryAction, PrintAction, ProductCell, ScreenHeader, SecondaryAction, StatusChip, TextCell } from '../../ui-kit'
import { getMoscowDateString } from '../../utils/moscowDate'

type Measurement = {
  product_id: string
  sku: string
  seller_article: string | null
  volume_liters: string | null
  dimensions_source: string | null
  liter_days: string
  rate_snapshot: string | null
  amount: string | null
  status?: 'calculated' | 'missing_dimensions'
}
type Statement = {
  id: string
  seller_id: string
  seller_name: string
  warehouse_id: string
  warehouse_name: string
  status: 'draft' | 'fixed'
  fixed_at: string | null
  total_liter_days: string
  total_amount: string
  problem_count: number
  measurements: Measurement[]
}
type StorageResponse = { tariff_configured: boolean; warehouses: { id: string; name: string }[]; statements: Statement[] }
type TariffCreateResponse = { recalculated_statements: Statement[] }
type HistoryRow = { id: string; created_at: string; source: string; length_mm: number | null; width_mm: number | null; height_mm: number | null; volume_liters: string | null; author_name: string | null; is_current: boolean }
type BackgroundJob = { id: string; status: string; error_message?: string | null }

const previousMonth = (now = new Date()) => {
  const [year, month] = getMoscowDateString(now).slice(0, 7).split('-').map(Number)
  const previousYear = month === 1 ? year - 1 : year
  const previousMonth = month === 1 ? 12 : month - 1
  return `${previousYear}-${String(previousMonth).padStart(2, '0')}`
}
const currentMonth = () => getMoscowDateString().slice(0, 7)
const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' })
const MINIMUM_RATE_BEFORE_CURRENCY_ROUNDING = 0.005
const MINIMUM_STORAGE_RATE_MESSAGE = 'Минимальная сохраняемая ставка — 0,01 ₽/л·день'
const statusLabel = (statement: Statement) => statement.status === 'fixed' ? 'Зафиксирован' : statement.problem_count ? 'Требует исправления' : 'Черновик'
const statusTone = (statement: Statement) => statement.status === 'fixed' ? 'ok' as const : statement.problem_count ? 'stop' as const : 'neutral' as const
const sourceLabel = (source: string | null) => ({ manual: 'Ручной обмер', wb: 'Wildberries', wildberries: 'Wildberries', container: 'Объём тары', container_override: 'Объём тары' }[source ?? ''] ?? 'Неизвестно')
const formatMonth = (month: string) => new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' }).format(new Date(`${month}-01T12:00:00`))

export function isStorageRateStartDateAllowed(validFrom: string, moscowToday: string) {
  return Boolean(validFrom) && validFrom >= moscowToday
}

export function mergeRecalculatedStorageStatements<T extends { id: string }>(current: readonly T[], recalculated: readonly T[]) {
  const recalculatedById = new Map(recalculated.map((statement) => [statement.id, statement]))
  return current.map((statement) => recalculatedById.get(statement.id) ?? statement)
}

export function mergeRecalculatedStorageData<T extends { statements: readonly { id: string }[] }>(
  current: T,
  recalculated: readonly T['statements'][number][],
): T & { statements: T['statements'][number][] } {
  return {
    ...current,
    statements: mergeRecalculatedStorageStatements(current.statements, recalculated),
  }
}

export function FfStoragePage({ isFulfillmentAdmin, token }: { isFulfillmentAdmin: boolean; token: string }) {
  const [search, setSearch] = useState('')
  const [month, setMonth] = useState(previousMonth())
  const [data, setData] = useState<StorageResponse | null>(null)
  const [selectedWarehouse, setSelectedWarehouse] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [measure, setMeasure] = useState<Measurement | null>(null)
  const [measureMode, setMeasureMode] = useState<'dimensions' | 'container'>('dimensions')
  const [length, setLength] = useState('')
  const [width, setWidth] = useState('')
  const [height, setHeight] = useState('')
  const [containerVolume, setContainerVolume] = useState('')
  const [containerBasis, setContainerBasis] = useState('')
  const [historyProductId, setHistoryProductId] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [rateOpen, setRateOpen] = useState(false)
  const [rateWarehouseId, setRateWarehouseId] = useState('')
  const [rateAmount, setRateAmount] = useState('')
  const [rateValidFrom, setRateValidFrom] = useState(getMoscowDateString())
  const [sellerRateEnabled, setSellerRateEnabled] = useState(false)
  const [rateSellerId, setRateSellerId] = useState('')
  const [sellerRateAmount, setSellerRateAmount] = useState('')
  const [sellerRateValidFrom, setSellerRateValidFrom] = useState(getMoscowDateString())
  const [rateError, setRateError] = useState<string | null>(null)
  const [rateRefreshFailed, setRateRefreshFailed] = useState(false)
  const [printStatement, setPrintStatement] = useState<Statement | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ year: month.slice(0, 4), month: String(Number(month.slice(5, 7))) })
      if (selectedWarehouse) params.set('warehouse_id', selectedWarehouse)
      const response = await fetch(apiUrl(`/operations/storage/statements?${params}`), { headers: authHeaders(token) })
      if (!response.ok) throw new Error('load_failed')
      const result = await response.json() as StorageResponse
      setData(result)
      setSelectedWarehouse((current) => current || (result.warehouses.length === 1 ? result.warehouses[0].id : ''))
      return true
    } catch {
      setError('Не удалось загрузить расчёты хранения. Повторите попытку')
      return false
    } finally {
      setLoading(false)
    }
  }, [month, selectedWarehouse, token])

  useEffect(() => { void load() }, [load])

  const statements = useMemo(() => (data?.statements ?? []).filter((statement) => {
    const needle = search.trim().toLowerCase()
    return !needle || [statement.seller_name, ...statement.measurements.flatMap((row) => [row.sku, row.seller_article ?? ''])].join(' ').toLowerCase().includes(needle)
  }), [data, search])
  const expanded = data?.statements.find((statement) => statement.id === expandedId) ?? null
  const missingCount = expanded?.measurements.filter((row) => row.status === 'missing_dimensions').length ?? 0
  const computedVolume = Number(length.replace(',', '.')) * Number(width.replace(',', '.')) * Number(height.replace(',', '.')) / 1000
  const sellers = useMemo(() => Array.from(new Map((data?.statements ?? []).map((statement) => [statement.seller_id, { id: statement.seller_id, name: statement.seller_name }])).values()), [data])
  const parsedRate = Number(rateAmount.replace(',', '.'))
  const parsedSellerRate = Number(sellerRateAmount.replace(',', '.'))
  const moscowToday = getMoscowDateString()
  const rateDisabledReason = !rateWarehouseId
    ? 'Выберите склад'
    : !Number.isFinite(parsedRate) || parsedRate <= 0
      ? 'Введите положительную ставку'
      : parsedRate < MINIMUM_RATE_BEFORE_CURRENCY_ROUNDING
        ? MINIMUM_STORAGE_RATE_MESSAGE
      : !rateValidFrom
        ? 'Укажите дату начала'
        : !isStorageRateStartDateAllowed(rateValidFrom, moscowToday)
          ? 'Дата начала не может быть в прошлом'
          : sellerRateEnabled && (!rateSellerId || !Number.isFinite(parsedSellerRate) || parsedSellerRate <= 0 || !sellerRateValidFrom)
            ? 'Заполните индивидуальную ставку селлера'
            : sellerRateEnabled && parsedSellerRate < MINIMUM_RATE_BEFORE_CURRENCY_ROUNDING
              ? MINIMUM_STORAGE_RATE_MESSAGE
            : sellerRateEnabled && !isStorageRateStartDateAllowed(sellerRateValidFrom, moscowToday)
              ? 'Дата индивидуальной ставки не может быть в прошлом'
              : undefined

  async function request(path: string, init: RequestInit) {
    const response = await fetch(apiUrl(path), { ...init, headers: authHeaders(token) })
    if (!response.ok) throw new Error('request_failed')
    return response.json().catch(() => null)
  }
  async function waitForJob(started: BackgroundJob) {
    if (started.status === 'done') return
    if (started.status === 'failed') throw new Error(started.error_message ?? 'job_failed')
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 200))
      const job = await request(`/operations/background-jobs/${started.id}`, { method: 'GET' }) as BackgroundJob
      if (job.status === 'done') return
      if (job.status === 'failed') throw new Error(job.error_message ?? 'job_failed')
    }
    throw new Error('job_timeout')
  }
  async function generate() {
    setActionLoading(true); setError(null)
    try {
      const started = await request('/operations/storage/measurements/rebuild', { method: 'POST', body: JSON.stringify({ year: Number(month.slice(0, 4)), month: Number(month.slice(5, 7)), warehouse_id: selectedWarehouse || undefined }) }) as BackgroundJob
      await waitForJob(started)
      await load()
    }
    catch { setError('Не удалось пересчитать хранение. Последний расчёт сохранён.') }
    finally { setActionLoading(false) }
  }
  async function saveMeasure() {
    if (!measure) return
    setActionLoading(true); setError(null)
    try {
      if (measureMode === 'dimensions') {
        await request(`/products/${measure.product_id}/dimensions`, { method: 'PATCH', body: JSON.stringify({ length_mm: Number(length) * 10, width_mm: Number(width) * 10, height_mm: Number(height) * 10 }) })
      } else {
        await request(`/products/${measure.product_id}/dimensions/container`, { method: 'POST', body: JSON.stringify({ volume_liters: Number(containerVolume.replace(',', '.')), container_basis: containerBasis }) })
      }
      setMeasure(null); await generate()
    } catch { setError('Не удалось сохранить обмер. Проверьте заполненные поля.') }
    finally { setActionLoading(false) }
  }
  async function openHistory(productId: string) {
    setHistoryProductId(productId); setHistoryError(null)
    try { setHistory(await request(`/products/${productId}/dimensions/history`, { method: 'GET' }) as HistoryRow[]) }
    catch { setHistory([]); setHistoryError('Не удалось загрузить историю габаритов. Повторите попытку') }
  }
  async function restoreWb() {
    if (!historyProductId) return
    setActionLoading(true)
    try { await request(`/products/${historyProductId}/dimensions/restore-wb`, { method: 'POST' }); setHistoryProductId(null); await generate() }
    catch { setHistoryError('Не удалось вернуть данные Wildberries. Повторите попытку') }
    finally { setActionLoading(false) }
  }
  async function fix() {
    if (!expanded) return
    setActionLoading(true); setError(null)
    try { const result = await request(`/operations/storage/statements/${expanded.id}/fix`, { method: 'POST' }) as Statement; setPrintStatement(result); await load() }
    catch { setError('Не удалось зафиксировать расчёт. Повторите попытку') }
    finally { setActionLoading(false) }
  }
  async function openPrint(statement: Statement) {
    setActionLoading(true)
    try { setPrintStatement(await request(`/operations/storage/statements/${statement.id}/print`, { method: 'GET' }) as Statement) }
    catch { setError('Не удалось открыть печатную форму. Повторите попытку') }
    finally { setActionLoading(false) }
  }
  function openRate() {
    setRateWarehouseId(selectedWarehouse || data?.warehouses[0]?.id || '')
    if (!rateRefreshFailed) setRateError(null)
    setRateOpen(true)
  }
  async function refreshRateData() {
    setActionLoading(true)
    setRateError(null)
    try {
      if (await load()) {
        setRateRefreshFailed(false)
        setRateOpen(false)
      } else {
        setRateError('Тариф сохранён, но расчёты не обновлены. Повторите обновление.')
      }
    } finally {
      setActionLoading(false)
    }
  }
  async function saveRate() {
    if (rateDisabledReason || rateRefreshFailed) return
    setActionLoading(true); setRateError(null)
    try {
      const tariffBody: Record<string, unknown> = { warehouse_id: rateWarehouseId, amount: parsedRate, valid_from: rateValidFrom }
      if (sellerRateEnabled) {
        tariffBody.seller_exception = { seller_id: rateSellerId, amount: parsedSellerRate, valid_from: sellerRateValidFrom }
      }
      const result = await request('/operations/storage/tariffs', { method: 'POST', body: JSON.stringify(tariffBody) }) as TariffCreateResponse
      if (!Array.isArray(result?.recalculated_statements)) throw new Error('recalculation_result_missing')
      setData(null)
      if (await load()) {
        setRateOpen(false)
      } else {
        setRateRefreshFailed(true)
        setRateError('Тариф сохранён, но расчёты не обновлены. Повторите обновление.')
      }
    } catch { setRateError('Не удалось сохранить тариф и пересчитать хранение. Последний успешный расчёт сохранён.') }
    finally { setActionLoading(false) }
  }

  return <Box data-testid="ff-storage-page">
    <ScreenHeader title="Хранение" purpose="Рассчитайте фактическое хранение по селлерам и зафиксируйте месяц для начисления" />
    <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Селлер, SKU или артикул продавца" testId="storage-filters">
      <TextField label="Месяц" type="month" value={month} onChange={(event) => setMonth(event.target.value)} size="small" helperText="Будущие месяцы недоступны: расчёт ещё не начался" slotProps={{ htmlInput: { 'data-testid': 'storage-month', max: currentMonth() } }} />
      {(data?.warehouses.length ?? 0) >= 2 && <TextField select label="Склад" value={selectedWarehouse} onChange={(event) => setSelectedWarehouse(event.target.value)} size="small" slotProps={{ htmlInput: { 'data-testid': 'storage-warehouse' } }}>{data?.warehouses.map((warehouse) => <MenuItem key={warehouse.id} value={warehouse.id}>{warehouse.name}</MenuItem>)}</TextField>}
    </FilterBar>
    {error && <ErrorNotice testId="storage-error">{error}</ErrorNotice>}
    <ActionGroup>
      <PrimaryAction data-testid="storage-generate" disabledReason={actionLoading ? 'Формирование уже запущено' : undefined} onClick={() => void generate()}>{actionLoading ? 'Формируем…' : 'Сформировать за месяц'}</PrimaryAction>
      {isFulfillmentAdmin && data?.tariff_configured && <SecondaryAction data-testid="storage-rate" onClick={openRate}>Изменить тариф</SecondaryAction>}
    </ActionGroup>
    <Box sx={{ mt: 2 }}>
      <DataTable columns={[
        { key: 'seller', header: 'Селлер', width: 240, render: (row: Statement) => <TextCell value={row.seller_name} /> },
        { key: 'status', header: 'Статус', width: 180, render: (row: Statement) => <StatusChip tone={statusTone(row)} label={statusLabel(row)} /> },
        { key: 'liter-days', header: 'Литро-дни', width: 140, align: 'right', render: (row: Statement) => row.total_liter_days },
        { key: 'total', header: 'Сумма, ₽', width: 140, align: 'right', render: (row: Statement) => row.total_amount },
        { key: 'problems', header: 'Проблемы', width: 110, align: 'right', render: (row: Statement) => row.problem_count },
        { key: 'actions', header: 'Действия', width: 120, align: 'center', render: (row: Statement) => <Stack direction="row"><IconAction title={expandedId === row.id ? 'Закрыть расчёт селлера' : 'Открыть расчёт селлера'} onClick={() => setExpandedId(expandedId === row.id ? null : row.id)} testId={`storage-expand-${row.id}`}><ExpandMoreIcon /></IconAction>{row.status === 'fixed' && <PrintAction what="накладную" placement="row" onClick={() => void openPrint(row)} testId={`storage-print-${row.id}`} />}</Stack> },
      ]} rows={statements} getRowKey={(row) => row.id} loading={loading} empty={data?.tariff_configured === false ? { title: 'Тариф хранения ещё не задан', hint: isFulfillmentAdmin ? 'Задайте цену за литр-день и дату начала, чтобы сформировать первый расчёт' : 'Обратитесь к администратору ФФ, чтобы задать тариф хранения.', action: isFulfillmentAdmin ? <PrimaryAction onClick={openRate}>Задать тариф</PrimaryAction> : undefined } : { title: 'Ничего не найдено — измените поиск или фильтры' }} testId="storage-seller-table" />
      {expanded && <Box sx={{ p: 2, mt: 1, borderLeft: 4, borderColor: 'primary.main' }} data-testid="storage-detail">
        <Typography variant="h6">{expanded.seller_name} · {formatMonth(month)}</Typography><Typography color="text.secondary">{expanded.warehouse_name} · ставка снимка</Typography>
        {missingCount > 0 && <ErrorNotice>Расчёт нельзя зафиксировать: устраните проблемы в строках ниже</ErrorNotice>}
        <DataTable columns={[
          { key: 'sku', header: 'Товар', width: 150, render: (row: Measurement) => <ProductCell sku={row.sku} /> },
          { key: 'article', header: 'Артикул продавца', width: 180, render: (row: Measurement) => <TextCell value={row.seller_article} /> },
          { key: 'volume', header: 'Объём, л', width: 110, align: 'right', render: (row: Measurement) => row.volume_liters ?? '—' },
          { key: 'source', header: 'Источник', width: 150, render: (row: Measurement) => <TextCell value={sourceLabel(row.dimensions_source)} /> },
          { key: 'liter-days', header: 'Литро-дни', width: 130, align: 'right', render: (row: Measurement) => row.status === 'missing_dimensions' ? '—' : row.liter_days },
          { key: 'rate', header: 'Ставка, ₽/л·день', width: 150, align: 'right', render: (row: Measurement) => row.rate_snapshot ?? '—' },
          { key: 'amount', header: 'Сумма, ₽', width: 120, align: 'right', render: (row: Measurement) => row.status === 'missing_dimensions' ? '—' : row.amount ?? '—' },
          { key: 'status', header: 'Статус', width: 150, render: (row: Measurement) => <StatusChip tone={row.status === 'missing_dimensions' ? 'stop' : 'neutral'} label={row.status === 'missing_dimensions' ? 'Нет габаритов' : 'Рассчитано'} /> },
          { key: 'actions', header: 'Действия', width: 160, render: (row: Measurement) => row.status === 'missing_dimensions' ? <PrimaryAction onClick={() => setMeasure(row)}>Внести обмер</PrimaryAction> : <IconAction title="История габаритов" onClick={() => void openHistory(row.product_id)}><HistoryOutlinedIcon /></IconAction> },
        ]} rows={expanded.measurements} getRowKey={(row) => row.product_id} testId="storage-sku-table" />
        {isFulfillmentAdmin && expanded.status === 'draft' && <ActionGroup><PrimaryAction data-testid="storage-fix" disabledReason={missingCount ? `Нет габаритов у ${missingCount} товара` : actionLoading ? 'Фиксация выполняется' : undefined} onClick={() => void fix()}>Зафиксировать</PrimaryAction></ActionGroup>}
      </Box>}
    </Box>
    <Dialog open={Boolean(measure)} onClose={() => setMeasure(null)}><DialogTitle>Внести обмер</DialogTitle><DialogContent><Typography sx={{ mb: 1 }}>{measure?.sku} · {measure?.seller_article}</Typography><RadioGroup row value={measureMode} onChange={(event) => setMeasureMode(event.target.value as 'dimensions' | 'container')}><FormControlLabel value="dimensions" control={<Radio />} label="Габариты товара" /><FormControlLabel value="container" control={<Radio />} label="Объём тары" /></RadioGroup>{measureMode === 'dimensions' ? <><Stack direction="row" spacing={1}><TextField label="Длина, см" value={length} onChange={(event) => setLength(event.target.value)} /><TextField label="Ширина, см" value={width} onChange={(event) => setWidth(event.target.value)} /><TextField label="Высота, см" value={height} onChange={(event) => setHeight(event.target.value)} /></Stack><Typography sx={{ mt: 2 }}>Объём: {Number.isFinite(computedVolume) && computedVolume > 0 ? computedVolume.toFixed(2).replace('.', ',') : '—'} л</Typography></> : <Stack spacing={1}><TextField label="Объём тары, л" value={containerVolume} onChange={(event) => setContainerVolume(event.target.value)} /><TextField label="Комментарий" value={containerBasis} onChange={(event) => setContainerBasis(event.target.value)} /></Stack>}</DialogContent><DialogActions><SecondaryAction onClick={() => setMeasure(null)}>Отмена</SecondaryAction><PrimaryAction disabledReason={measureMode === 'dimensions' ? !Number.isFinite(computedVolume) || computedVolume <= 0 ? 'Введите положительные габариты' : undefined : !Number(containerVolume.replace(',', '.')) || !containerBasis.trim() ? 'Укажите объём и причину' : undefined} onClick={() => void saveMeasure()}>Сохранить</PrimaryAction></DialogActions></Dialog>
    <Dialog open={rateOpen} onClose={() => !actionLoading && setRateOpen(false)} fullWidth maxWidth="sm"><DialogTitle>Тариф хранения</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}>{rateError && <ErrorNotice>{rateError}</ErrorNotice>}{(data?.warehouses.length ?? 0) > 1 ? <TextField select label="Операционный склад" value={rateWarehouseId} onChange={(event) => setRateWarehouseId(event.target.value)} size="small" required>{data?.warehouses.map((warehouse) => <MenuItem key={warehouse.id} value={warehouse.id}>{warehouse.name}</MenuItem>)}</TextField> : <Typography color="text.secondary">{data?.warehouses[0]?.name ?? 'Операционный склад не выбран'}</Typography>}<Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}><TextField label="Ставка, ₽/л·день" value={rateAmount} onChange={(event) => setRateAmount(event.target.value)} inputMode="decimal" required fullWidth slotProps={{ htmlInput: { 'data-testid': 'storage-rate-amount' } }} /><TextField label="Дата начала" type="date" value={rateValidFrom} onChange={(event) => setRateValidFrom(event.target.value)} required fullWidth slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'data-testid': 'storage-rate-valid-from', min: moscowToday } }} /></Stack><Box component="details" open={sellerRateEnabled} onToggle={(event) => setSellerRateEnabled((event.currentTarget as HTMLDetailsElement).open)}><Typography component="summary" color="primary" sx={{ cursor: 'pointer', fontWeight: 700 }}>Индивидуальная ставка селлера</Typography><Stack spacing={2} sx={{ pt: 2 }}><TextField select label="Селлер" value={rateSellerId} onChange={(event) => setRateSellerId(event.target.value)} size="small" required>{sellers.map((seller) => <MenuItem key={seller.id} value={seller.id}>{seller.name}</MenuItem>)}</TextField><Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}><TextField label="Ставка, ₽/л·день" value={sellerRateAmount} onChange={(event) => setSellerRateAmount(event.target.value)} inputMode="decimal" required fullWidth slotProps={{ htmlInput: { 'data-testid': 'storage-seller-rate-amount' } }} /><TextField label="Дата начала" type="date" value={sellerRateValidFrom} onChange={(event) => setSellerRateValidFrom(event.target.value)} required fullWidth slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'data-testid': 'storage-seller-rate-valid-from', min: moscowToday } }} /></Stack></Stack></Box></Stack></DialogContent><DialogActions><SecondaryAction onClick={() => setRateOpen(false)}>Отмена</SecondaryAction>{rateRefreshFailed && <SecondaryAction data-testid="storage-rate-refresh" disabledReason={actionLoading ? 'Обновление расчётов выполняется' : undefined} onClick={() => void refreshRateData()}>Повторить</SecondaryAction>}<PrimaryAction data-testid="storage-rate-save" disabledReason={actionLoading ? 'Сохранение тарифа выполняется' : rateRefreshFailed ? 'Тариф уже сохранён. Повторите обновление расчётов.' : rateDisabledReason} onClick={() => void saveRate()}>Сохранить</PrimaryAction></DialogActions></Dialog>
    <Dialog open={Boolean(historyProductId)} onClose={() => setHistoryProductId(null)} maxWidth="md" fullWidth><DialogTitle>История габаритов</DialogTitle><DialogContent>{historyError && <ErrorNotice>{historyError}</ErrorNotice>}<DataTable columns={[{ key: 'date', header: 'Дата', width: 170, render: (row: HistoryRow) => new Date(row.created_at).toLocaleString('ru-RU') }, { key: 'source', header: 'Источник', width: 140, render: (row: HistoryRow) => sourceLabel(row.source) }, { key: 'value', header: 'Габариты / объём', width: 250, render: (row: HistoryRow) => row.volume_liters ? `${row.length_mm ?? '—'} × ${row.width_mm ?? '—'} × ${row.height_mm ?? '—'} мм · ${row.volume_liters} л` : '—' }, { key: 'author', header: 'Автор', width: 180, render: (row: HistoryRow) => row.author_name ?? 'Импорт' }, { key: 'current', header: 'Применено', width: 140, render: (row: HistoryRow) => <StatusChip tone={row.is_current ? 'ok' : 'neutral'} label={row.is_current ? 'Действует' : 'История'} /> }]} rows={history} getRowKey={(row) => row.id} empty={{ title: 'История габаритов пока пуста' }} /></DialogContent><DialogActions><SecondaryAction onClick={() => setHistoryProductId(null)}>Закрыть</SecondaryAction>{isFulfillmentAdmin && <PrimaryAction onClick={() => void restoreWb()}>Вернуть данные WB</PrimaryAction>}</DialogActions></Dialog>
    <Dialog open={Boolean(printStatement)} onClose={() => setPrintStatement(null)} maxWidth="md" fullWidth><DialogTitle>Расчёт хранения за {formatMonth(month)}</DialogTitle><DialogContent>{printStatement && <Box data-testid="storage-print-preview"><Typography>Селлер: {printStatement.seller_name}</Typography><Typography>Склад: {printStatement.warehouse_name}</Typography><Typography>Зафиксирован: {printStatement.fixed_at ? new Date(printStatement.fixed_at).toLocaleString('ru-RU') : '—'}</Typography><DataTable columns={[{ key: 'sku', header: 'SKU', width: 150, render: (row: Measurement) => row.sku }, { key: 'article', header: 'Артикул продавца', width: 180, render: (row: Measurement) => row.seller_article ?? '—' }, { key: 'volume', header: 'Объём, л', width: 110, align: 'right', render: (row: Measurement) => row.volume_liters ?? '—' }, { key: 'source', header: 'Источник', width: 150, render: (row: Measurement) => sourceLabel(row.dimensions_source) }, { key: 'days', header: 'Литро-дни', width: 130, align: 'right', render: (row: Measurement) => row.liter_days }, { key: 'rate', header: 'Ставка, ₽/л·день', width: 150, align: 'right', render: (row: Measurement) => row.rate_snapshot ?? '—' }, { key: 'amount', header: 'Сумма, ₽', width: 120, align: 'right', render: (row: Measurement) => row.amount ?? '0' }]} rows={printStatement.measurements} getRowKey={(row) => row.product_id} empty={{ title: 'В выбранном месяце хранения не было' }} /><Typography sx={{ mt: 2, fontWeight: 700, textAlign: 'right' }}>Итого: {printStatement.total_amount} ₽</Typography></Box>}</DialogContent><DialogActions><SecondaryAction onClick={() => setPrintStatement(null)}>Закрыть</SecondaryAction><PrintAction what="накладную" placement="panel" onClick={() => window.print()} /></DialogActions></Dialog>
  </Box>
}
