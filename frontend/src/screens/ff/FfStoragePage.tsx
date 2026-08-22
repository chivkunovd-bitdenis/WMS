import { useMemo, useState } from 'react'
import { Box, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { ActionGroup, DataTable, EmptyState, ErrorNotice, FilterBar, IconAction, PrimaryAction, PrintAction, ProductCell, ScreenHeader, SecondaryAction, StatusChip, TextCell } from '../../ui-kit'

type Seller = { id: string; name: string; status: 'Черновик' | 'Требует исправления' | 'Зафиксирован'; liters: string; total: string; problems: number }
type Sku = { id: string; sku: string; vendor: string; volume: string; source: string; liters: string; total: string; missing?: boolean }

const initialSellers: Seller[] = [
  { id: 'beauty', name: 'Красотка', status: 'Требует исправления', liters: '12 840,50', total: '8 988,35', problems: 1 },
  { id: 'north', name: 'Норд', status: 'Черновик', liters: '6 432,00', total: '4 502,40', problems: 0 },
  { id: 'vector', name: 'Вектор', status: 'Зафиксирован', liters: '0', total: '0,00', problems: 0 },
]
const skus: Sku[] = [
  { id: '10432', sku: 'SKU-10432', vendor: 'KRS-44-BLK', volume: '2,40', source: 'Ручной обмер', liters: '8 928,00', total: '6 249,60' },
  { id: '10433', sku: 'SKU-10433', vendor: 'KRS-44-WHT', volume: '1,18', source: 'Wildberries', liters: '3 912,50', total: '2 738,75' },
  { id: '11890', sku: 'SKU-11890', vendor: 'NRD-2XL-LONG', volume: '—', source: 'Неизвестно', liters: '—', total: '—', missing: true },
]

export function FfStoragePage({ isFulfillmentAdmin }: { isFulfillmentAdmin: boolean }) {
  const [search, setSearch] = useState('')
  const [month, setMonth] = useState('2026-07')
  const [expanded, setExpanded] = useState<string | null>('beauty')
  const [sellers, setSellers] = useState(initialSellers)
  const [measureOpen, setMeasureOpen] = useState(false)
  const [rateOpen, setRateOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [printOpen, setPrintOpen] = useState(false)
  const [measured, setMeasured] = useState(false)
  const visible = useMemo(() => sellers.filter((s) => s.name.toLowerCase().includes(search.toLowerCase()) || (expanded === s.id && skus.some((x) => `${x.sku} ${x.vendor}`.toLowerCase().includes(search.toLowerCase())))), [search, sellers, expanded])
  const detailRows = measured ? skus.map((s) => s.id === '11890' ? { ...s, volume: '13,44', source: 'Ручной обмер', liters: '4 000,00', total: '2 800,00', missing: false } : s) : skus
  const canFix = isFulfillmentAdmin && measured
  const fix = () => { setSellers((rows) => rows.map((s) => s.id === 'beauty' ? { ...s, status: 'Зафиксирован', problems: 0 } : s)); setPrintOpen(true) }

  return <Box data-testid="ff-storage-page"><ScreenHeader title="Хранение" purpose="Рассчитайте фактическое хранение по селлерам и зафиксируйте месяц для начисления" />
    <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Селлер, SKU или артикул продавца" testId="storage-filters">
      <TextField label="Месяц" type="month" value={month} onChange={(e) => setMonth(e.target.value)} size="small" inputProps={{ 'data-testid': 'storage-month' }} />
      <TextField label="Склад" value="Основной склад" size="small" disabled />
    </FilterBar>
    <ActionGroup><PrimaryAction onClick={() => setSellers(initialSellers)} data-testid="storage-generate">Сформировать за месяц</PrimaryAction>{isFulfillmentAdmin && <SecondaryAction onClick={() => setRateOpen(true)} data-testid="storage-rate">Изменить тариф</SecondaryAction>}</ActionGroup>
    <Box sx={{ mt: 2 }}><DataTable columns={[
      { key: 'seller', header: 'Селлер', width: 240, render: (r: Seller) => <TextCell>{r.name}</TextCell> },
      { key: 'status', header: 'Статус', width: 180, render: (r: Seller) => <StatusChip tone={r.status === 'Зафиксирован' ? 'ok' : r.status === 'Требует исправления' ? 'stop' : 'neutral'}>{r.status}</StatusChip> },
      { key: 'liters', header: 'Литро-дни', width: 140, align: 'right', render: (r: Seller) => r.liters }, { key: 'total', header: 'Сумма, ₽', width: 140, align: 'right', render: (r: Seller) => r.total }, { key: 'problems', header: 'Проблемы', width: 110, align: 'right', render: (r: Seller) => r.problems },
      { key: 'actions', header: 'Действия', width: 120, align: 'center', render: (r: Seller) => <Stack direction="row"><IconAction title={expanded === r.id ? 'Закрыть расчёт селлера' : 'Открыть расчёт селлера'} onClick={() => setExpanded(expanded === r.id ? null : r.id)} testId={`storage-expand-${r.id}`}><ExpandMoreIcon /></IconAction>{r.status === 'Зафиксирован' && <PrintAction what="накладную" placement="row" onClick={() => setPrintOpen(true)} testId={`storage-print-${r.id}`} />}</Stack> },
    ]} rows={visible} getRowKey={(r) => r.id} empty={{ title: search ? 'Ничего не найдено — измените поиск или фильтры' : 'Тариф хранения ещё не задан', hint: 'Задайте цену за литр-день и дату начала, чтобы сформировать первый расчёт', action: isFulfillmentAdmin ? <PrimaryAction onClick={() => setRateOpen(true)}>Задать тариф</PrimaryAction> : undefined }} testId="storage-seller-table" />
      {expanded === 'beauty' && visible.some((r) => r.id === 'beauty') && <Box sx={{ p: 2, border: '1px solid', borderColor: 'divider' }}><Typography variant="h6">Красотка · {month}</Typography><Typography color="text.secondary">Основной склад · ставка 0,70 ₽/л·день</Typography>{!measured && <ErrorNotice>Расчёт нельзя зафиксировать: устраните проблемы в строках ниже</ErrorNotice>}<DataTable columns={[{ key: 'sku', header: 'Товар', width: 150, render: (r: Sku) => <ProductCell>{r.sku}</ProductCell> }, { key: 'vendor', header: 'Артикул продавца', width: 180, render: (r: Sku) => <TextCell>{r.vendor}</TextCell> }, { key: 'volume', header: 'Объём, л', width: 110, align: 'right', render: (r: Sku) => r.volume }, { key: 'source', header: 'Источник', width: 150, render: (r: Sku) => r.source }, { key: 'liters', header: 'Литро-дни', width: 130, align: 'right', render: (r: Sku) => r.liters }, { key: 'total', header: 'Сумма, ₽', width: 120, align: 'right', render: (r: Sku) => r.total }, { key: 'status', header: 'Статус', width: 150, render: (r: Sku) => <StatusChip tone={r.missing ? 'stop' : 'ok'}>{r.missing ? 'Нет габаритов' : 'Рассчитано'}</StatusChip> }, { key: 'actions', header: 'Действия', width: 160, render: (r: Sku) => r.missing ? <PrimaryAction onClick={() => setMeasureOpen(true)}>Внести обмер</PrimaryAction> : <IconAction title="История габаритов" onClick={() => setHistoryOpen(true)}>↻</IconAction> }]} rows={detailRows} getRowKey={(r) => r.id} testId="storage-sku-table" /></Box>}
    </Box>
    {expanded === 'beauty' && <ActionGroup><PrimaryAction disabledReason={!canFix ? 'Нет габаритов у 1 товара' : undefined} onClick={fix} data-testid="storage-fix">Зафиксировать</PrimaryAction></ActionGroup>}
    <Dialog open={measureOpen} onClose={() => setMeasureOpen(false)}><DialogTitle>Внести габариты</DialogTitle><DialogContent><Typography>SKU-11890 · NRD-2XL-LONG</Typography><Stack direction="row" spacing={1} sx={{ mt: 2 }}><TextField label="Длина, см" defaultValue="40" /><TextField label="Ширина, см" defaultValue="28" /><TextField label="Высота, см" defaultValue="12" /></Stack><Typography sx={{ mt: 2 }}>Объём: 13,44 л</Typography></DialogContent><DialogActions><SecondaryAction onClick={() => setMeasureOpen(false)}>Отмена</SecondaryAction><PrimaryAction onClick={() => { setMeasured(true); setMeasureOpen(false) }}>Сохранить</PrimaryAction></DialogActions></Dialog>
    <Dialog open={rateOpen} onClose={() => setRateOpen(false)}><DialogTitle>Тариф хранения</DialogTitle><DialogContent><Stack spacing={2} sx={{ mt: 1 }}><TextField label="Ставка, ₽/л·день" defaultValue="0,70" /><TextField label="Дата начала" type="date" defaultValue={`${month}-01`} /></Stack></DialogContent><DialogActions><SecondaryAction onClick={() => setRateOpen(false)}>Отмена</SecondaryAction><PrimaryAction onClick={() => setRateOpen(false)}>Сохранить</PrimaryAction></DialogActions></Dialog>
    <Dialog open={historyOpen} onClose={() => setHistoryOpen(false)}><DialogTitle>История габаритов</DialogTitle><DialogContent><Typography>18.07.2026 · Ручной обмер · 40 × 25 × 24 см · Действует</Typography><Typography sx={{ mt: 1 }}>02.07.2026 · Wildberries · 39 × 25 × 23 см · История</Typography></DialogContent><DialogActions><SecondaryAction onClick={() => setHistoryOpen(false)}>Закрыть</SecondaryAction></DialogActions></Dialog>
    <Dialog open={printOpen} onClose={() => setPrintOpen(false)}><DialogTitle>Расчёт хранения за {month}</DialogTitle><DialogContent><Typography>Селлер: Красотка</Typography><Typography>Склад: Основной склад</Typography><Typography sx={{ mt: 2, fontWeight: 700 }}>Итого: 11 788,35 ₽</Typography></DialogContent><DialogActions><SecondaryAction onClick={() => setPrintOpen(false)}>Закрыть</SecondaryAction><PrintAction what="накладную" placement="panel" onClick={() => window.print()} /></DialogActions></Dialog>
  </Box>
}
