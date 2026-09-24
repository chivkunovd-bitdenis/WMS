import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  Link,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Switch,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  CheckCircleOutlined,
  CloseOutlined,
  InsertDriveFileOutlined,
  KeyOutlined,
  OpenInNewOutlined,
  RefreshOutlined,
  SearchOutlined,
} from '@mui/icons-material'

type WithdrawalStatus = 'pending' | 'withdrawn' | 'error'
type CodeSource = 'printed' | 'scanned'
type ProductGroup = 'light_industry' | 'shoes'

type DemoRow = {
  id: string
  transferDate: string
  documentNumber: string
  sku: string
  product: string
  size: string
  productGroup: ProductGroup
  kiz: string
  source: CodeSource
  status: WithdrawalStatus
  statusDetail: string
  submitFailure?: 'price_missing'
  withdrawnAt?: string
  crptDocument?: string
}

const RECOGNIZABLE_ROWS: DemoRow[] = [
  {
    id: 'kiz-001', transferDate: '2026-09-22', documentNumber: '1849067421', sku: 'WB-TSHIRT-BASE-WHITE-M',
    product: 'Футболка базовая хлопковая, белая, мужская — длинное название для проверки таблицы', size: 'M',
    productGroup: 'light_industry', kiz: '0104601234567890215pQdL8K2cP9xmR7GS', source: 'printed', status: 'pending',
    statusDetail: 'Готов к выводу после подтверждённой передачи WB',
  },
  {
    id: 'kiz-002', transferDate: '2026-09-22', documentNumber: '1849067427', sku: 'WB-HOODIE-OVERSIZE-GR-L',
    product: 'Худи оверсайз с начёсом', size: 'L', productGroup: 'light_industry', kiz: '010460123456781421R8kaM2nQ5vLcT0GS',
    source: 'scanned', status: 'pending', statusDetail: 'Готов к выводу после подтверждённой передачи WB',
  },
  {
    id: 'kiz-003', transferDate: '2026-09-21', documentNumber: '1848933018', sku: 'WB-SOCKS-SPORT-3-BLK',
    product: 'Носки спортивные, 3 пары', size: '39–42', productGroup: 'light_industry', kiz: '010460123456782121mLFx7bW4jDqS11GS',
    source: 'printed', status: 'error', statusDetail: 'ЧЗ не принял документ: цена продажи не указана',
    submitFailure: 'price_missing',
  },
  {
    id: 'kiz-005', transferDate: '2026-09-20', documentNumber: '1848810023', sku: 'WB-SNEAKERS-RUN-42',
    product: 'Кроссовки беговые', size: '42', productGroup: 'shoes', kiz: '0104601234567845212NaaP8sE4mXc33GS',
    source: 'printed', status: 'withdrawn', statusDetail: 'Выведен из оборота: дистанционная продажа',
    withdrawnAt: '21.09.2026, 10:42', crptDocument: '4c5da815-2d49-4a45-a167-8231bf342810',
  },
  {
    id: 'kiz-007', transferDate: '2026-09-18', documentNumber: '1848421130', sku: 'WB-JACKET-WIND-NAVY-XL',
    product: 'Ветровка непромокаемая', size: 'XL', productGroup: 'light_industry', kiz: '010460123456786921K1vGf5zB7pMhA5GS',
    source: 'scanned', status: 'withdrawn', statusDetail: 'Выведен из оборота: дистанционная продажа',
    withdrawnAt: '19.09.2026, 09:14', crptDocument: '3bfb950a-617b-4864-96fd-9325d5ab0f44',
  },
  {
    id: 'kiz-009', transferDate: '2026-09-22', documentNumber: '1849067455', sku: 'WB-SNEAKERS-CITY-41',
    product: 'Кеды городские из натуральной кожи', size: '41', productGroup: 'shoes',
    kiz: '010460123456788321z4WsL7cR2vBnM8GS', source: 'scanned', status: 'pending',
    statusDetail: 'Готов к выводу после подтверждённой передачи WB',
  },
]

const PRODUCT_NAMES = [
  'Футболка хлопковая',
  'Худи оверсайз',
  'Носки спортивные, 3 пары',
  'Кроссовки беговые',
  'Ветровка непромокаемая',
  'Кеды городские',
  'Лонгслив базовый',
  'Брюки спортивные',
] as const

const COLORS = ['белый', 'чёрный', 'серый', 'синий', 'зелёный', 'бежевый'] as const
const SIZES = ['XS', 'S', 'M', 'L', 'XL', '40', '41', '42'] as const

const GENERATED_ROWS: DemoRow[] = Array.from({ length: 318 }, (_, offset) => {
  const sequence = offset + 10
  const status: WithdrawalStatus = sequence % 61 === 0 ? 'error' : sequence % 19 === 0 ? 'withdrawn' : 'pending'
  const productGroup: ProductGroup = sequence % 4 === 0 ? 'shoes' : 'light_industry'
  const model = String(1000 + sequence)
  const day = 17 + (sequence % 7)
  const serial = `${sequence.toString(36).padStart(5, '0')}WmsDemo${String(sequence).padStart(5, '0')}`

  return {
    id: `kiz-${String(sequence).padStart(4, '0')}`,
    transferDate: `2026-09-${String(day).padStart(2, '0')}`,
    documentNumber: String(1849100000 + sequence),
    sku: `WB-${productGroup === 'shoes' ? 'SHOES' : 'APPAREL'}-${model}-${SIZES[sequence % SIZES.length]}`,
    product: `${PRODUCT_NAMES[sequence % PRODUCT_NAMES.length]}, ${COLORS[sequence % COLORS.length]} · модель ${model}`,
    size: SIZES[sequence % SIZES.length],
    productGroup,
    kiz: `01${String(4601234500000 + sequence).padStart(14, '0')}21${serial}GS`,
    source: sequence % 2 === 0 ? 'printed' : 'scanned',
    status,
    statusDetail: status === 'error' ? 'ЧЗ не принял документ: цена продажи не указана' : '',
    submitFailure: status === 'error' ? 'price_missing' : undefined,
    withdrawnAt: status === 'withdrawn' ? '22.09.2026, 16:20' : undefined,
    crptDocument: status === 'withdrawn' ? `demo-lk-receipt-${sequence}` : undefined,
  }
})

const EMPIRE_ROWS: DemoRow[] = [...RECOGNIZABLE_ROWS, ...GENERATED_ROWS]

const statusView: Record<WithdrawalStatus, { label: string; color: 'default' | 'warning' | 'info' | 'success' | 'error' }> = {
  pending: { label: 'Не выведен', color: 'warning' },
  withdrawn: { label: 'Выведен', color: 'success' },
  error: { label: 'Ошибка', color: 'error' },
}

const formatDate = (value: string) => new Intl.DateTimeFormat('ru-RU').format(new Date(`${value}T12:00:00`))
const isEligible = (row: DemoRow) => row.status === 'pending' || row.status === 'error'
const compactKiz = (value: string) => `${value.slice(0, 18)}…${value.slice(-4)}`
function RowStatus({ row }: { row: DemoRow }) {
  const view = statusView[row.status]
  return (
    <Stack spacing={0.25} sx={{ minWidth: 116 }}>
      <Chip size="small" color={view.color} label={view.label} sx={{ alignSelf: 'flex-start', height: 22 }} />
      {row.status === 'error' ? <Typography variant="caption" color="error.dark" sx={{ lineHeight: 1.2 }}>{row.statusDetail}</Typography> : null}
    </Stack>
  )
}

function CertificateCard({ selected, onSelect }: { selected: boolean; onSelect: () => void }) {
  return (
    <Paper
      component="button"
      type="button"
      variant="outlined"
      onClick={onSelect}
      aria-pressed={selected}
      sx={{
        width: '100%', p: 2, textAlign: 'left', bgcolor: 'background.paper', cursor: 'pointer',
        borderColor: selected ? 'primary.main' : 'divider', borderWidth: selected ? 2 : 1,
        display: 'flex', alignItems: 'flex-start', gap: 1.5,
      }}
    >
      {selected ? <CheckCircleOutlined color="success" sx={{ mt: 0.5 }} /> : <Box sx={{ width: 24, height: 24, mt: 0.5, borderRadius: '50%', border: '2px solid', borderColor: 'divider' }} />}
      <Avatar sx={{ bgcolor: 'primary.50', color: 'primary.main' }}><KeyOutlined /></Avatar>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="subtitle2">ИП Фадин Алексей Сергеевич</Typography>
        <Typography variant="body2" color="text.secondary">ИНН 771234567890 · ГОСТ 2012</Typography>
        <Typography variant="caption" color="success.dark">Действителен до 18.06.2027 · Рутокен ЭЦП 3.0</Typography>
      </Box>
    </Paper>
  )
}

export function SellerKizWithdrawalDemoScreen() {
  const [rows, setRows] = useState<DemoRow[]>(EMPIRE_ROWS)
  const [dateFrom, setDateFrom] = useState('2026-09-17')
  const [dateTo, setDateTo] = useState('2026-09-23')
  const [query, setQuery] = useState('')
  const [product, setProduct] = useState('all')
  const [onlyPending, setOnlyPending] = useState(true)
  const [selected, setSelected] = useState<string[]>([])
  const [details, setDetails] = useState<DemoRow | null>(null)
  const [certificateOpen, setCertificateOpen] = useState(false)
  const [certificateSelected, setCertificateSelected] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [operationRows, setOperationRows] = useState<DemoRow[]>([])
  const [failedRows, setFailedRows] = useState<DemoRow[]>([])
  const [toast, setToast] = useState('')
  const [activeHonestSignTab, setActiveHonestSignTab] = useState(1)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(50)

  const products = useMemo(() => Array.from(new Map(rows.map((row) => [row.sku, row.product])).entries()), [rows])
  const filteredRows = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('ru')
    return rows.filter((row) => {
      if (row.transferDate < dateFrom || row.transferDate > dateTo) return false
      if (product !== 'all' && row.sku !== product) return false
      if (onlyPending && row.status === 'withdrawn') return false
      if (needle && !`${row.product} ${row.sku} ${row.documentNumber} ${row.kiz}`.toLocaleLowerCase('ru').includes(needle)) return false
      return true
    })
  }, [dateFrom, dateTo, onlyPending, product, query, rows])

  const maxPage = Math.max(0, Math.ceil(filteredRows.length / rowsPerPage) - 1)
  const currentPage = Math.min(page, maxPage)
  const visibleRows = filteredRows.slice(currentPage * rowsPerPage, currentPage * rowsPerPage + rowsPerPage)
  const eligibleVisibleIds = visibleRows.filter(isEligible).map((row) => row.id)
  const selectedRows = visibleRows.filter((row) => selected.includes(row.id) && isEligible(row))
  const allVisibleSelected = eligibleVisibleIds.length > 0 && eligibleVisibleIds.every((id) => selected.includes(id))
  const someVisibleSelected = eligibleVisibleIds.some((id) => selected.includes(id)) && !allVisibleSelected
  const toggleAllVisible = () => {
    setSelected((current) => allVisibleSelected
      ? current.filter((id) => !eligibleVisibleIds.includes(id))
      : Array.from(new Set([...current, ...eligibleVisibleIds])))
  }

  useEffect(() => {
    setPage((current) => Math.min(current, maxPage))
  }, [maxPage])

  const closeCertificate = () => {
    if (submitting) return
    setCertificateOpen(false)
    setCertificateSelected(false)
    setOperationRows([])
  }

  const openOperation = () => {
    setOperationRows(selectedRows)
    setCertificateSelected(false)
    setCertificateOpen(true)
  }

  const submitOperation = () => {
    setSubmitting(true)
    window.setTimeout(() => {
      const rejected = operationRows.filter((row) => Boolean(row.submitFailure))
      const successful = operationRows.filter((row) => !row.submitFailure)
      const successfulIds = new Set(successful.map((row) => row.id))
      const operationIds = new Set(operationRows.map((row) => row.id))

      setRows((current) => current.map((row) => successfulIds.has(row.id) ? {
        ...row,
        status: 'withdrawn',
        statusDetail: '',
        withdrawnAt: '23.09.2026, 14:28',
        crptDocument: `demo-lk-receipt-${row.productGroup}-1428`,
      } : row))
      setSelected((current) => current.filter((id) => !operationIds.has(id)))
      setSubmitting(false)
      setCertificateOpen(false)
      setCertificateSelected(false)
      setOperationRows([])
      setFailedRows(rejected)
      setToast(rejected.length > 0
        ? `Выведено: ${successful.length}. Ошибок: ${rejected.length}`
        : `КИЗ выведены из оборота: ${successful.length}`)
    }, 900)
  }

  return (
    <Stack spacing={2.5} sx={{ minWidth: 0, maxWidth: '100%' }} data-testid="wms517-kiz-withdrawal-demo">
      <Alert severity="info" icon={<InsertDriveFileOutlined />}>
        <strong>Интерактивный макет · данные демонстрационные.</strong> Здесь нет запросов к WMS или «Честному знаку», а подпись только имитируется.
      </Alert>

      <Paper variant="outlined">
        <Tabs value={activeHonestSignTab} onChange={(_, value: number) => setActiveHonestSignTab(value)} aria-label="Разделы Честного знака" variant="scrollable" scrollButtons="auto">
          <Tab label="Пулы КИЗ" />
          <Tab label="Вывод из оборота" />
        </Tabs>
      </Paper>

      {activeHonestSignTab === 0 ? (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6">Пулы КИЗ</Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>В этом демонстрационном экране пулы не изменяются. Переключитесь обратно, чтобы продолжить сценарий вывода из оборота.</Typography>
          <Button sx={{ mt: 2 }} variant="contained" onClick={() => setActiveHonestSignTab(1)}>Вернуться к выводу из оборота</Button>
        </Paper>
      ) : <>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { md: 'flex-start' } }}>
        <Box>
          <Typography variant="overline" color="text.secondary">Честный знак</Typography>
          <Typography variant="h5">Вывод КИЗ из оборота</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 760 }}>
            Только КИЗ FBS-заказов, по которым в WMS уже зафиксирована передача Wildberries. Период считается по дате передачи.
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<RefreshOutlined />} onClick={() => {
          setRows(EMPIRE_ROWS); setSelected([]); setOperationRows([]); setFailedRows([]); setToast('')
          setDateFrom('2026-09-17'); setDateTo('2026-09-23'); setQuery(''); setProduct('all'); setOnlyPending(true); setPage(0); setRowsPerPage(50)
          setCertificateSelected(false); setCertificateOpen(false)
        }}>
          Сбросить демо
        </Button>
      </Stack>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1.5} sx={{ alignItems: { lg: 'center' } }}>
            <TextField
              label="Передано WB с" type="date" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setSelected([]); setPage(0) }}
              slotProps={{ inputLabel: { shrink: true } }} sx={{ minWidth: 168 }}
            />
            <TextField
              label="по" type="date" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setSelected([]); setPage(0) }}
              slotProps={{ inputLabel: { shrink: true } }} sx={{ minWidth: 168 }}
            />
            <FormControl sx={{ minWidth: 0, width: { xs: '100%', lg: 'auto' }, flex: { xs: '0 0 auto', lg: '1 1 240px' } }}>
              <InputLabel id="product-filter-label">Товар</InputLabel>
              <Select labelId="product-filter-label" label="Товар" value={product} onChange={(event) => { setProduct(event.target.value); setSelected([]); setPage(0) }}>
                <MenuItem value="all">Все товары</MenuItem>
                {products.map(([sku, name]) => <MenuItem key={sku} value={sku}>{name}</MenuItem>)}
              </Select>
            </FormControl>
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ alignItems: { md: 'center' } }}>
            <TextField
              value={query} onChange={(event) => { setQuery(event.target.value); setSelected([]); setPage(0) }}
              label="Поиск" placeholder="КИЗ, заказ, артикул или товар"
              slotProps={{ input: { startAdornment: <SearchOutlined color="action" sx={{ mr: 1 }} /> } }}
              sx={{ flex: 1 }}
            />
            <FormControlLabel
              control={<Switch checked={onlyPending} onChange={(event) => { setOnlyPending(event.target.checked); setSelected([]); setPage(0) }} />}
              label="Только не выведенные"
            />
          </Stack>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ minWidth: 0, overflow: 'hidden' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={0.5} sx={{ px: 1.5, py: 1, justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>Найдено: {filteredRows.length}</Typography>
          <Typography variant="caption" color="text.secondary">Показывается только текущая страница; выбор не переносится между страницами</Typography>
        </Stack>
        <Divider />
        <TableContainer sx={{ maxWidth: '100%', maxHeight: { xs: '62vh', md: 560 }, overflow: 'auto' }}>
        <Table stickyHeader size="small" aria-label="КИЗ для вывода из оборота" sx={{ minWidth: 980, '& .MuiTableCell-root': { py: 0.5, px: 1, fontSize: '0.78rem' } }}>
          <TableHead sx={{ '& .MuiTableCell-head': { bgcolor: 'background.paper', zIndex: 3 } }}>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  checked={allVisibleSelected}
                  indeterminate={someVisibleSelected}
                  disabled={eligibleVisibleIds.length === 0}
                  onChange={toggleAllVisible}
                  slotProps={{ input: { 'aria-label': 'Выбрать все доступные КИЗ в таблице' } }}
                />
              </TableCell>
              <TableCell sx={{ width: 112, whiteSpace: 'nowrap' }}>Передано WB</TableCell>
              <TableCell sx={{ width: 122, whiteSpace: 'nowrap' }}>Заказ WB</TableCell>
              <TableCell sx={{ minWidth: 176, whiteSpace: 'nowrap' }}>Артикул</TableCell>
              <TableCell sx={{ minWidth: 230 }}>Наименование</TableCell>
              <TableCell sx={{ minWidth: 205, whiteSpace: 'nowrap' }}>КИЗ</TableCell>
              <TableCell sx={{ minWidth: 150 }}>Статус</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleRows.length === 0 ? (
              <TableRow><TableCell colSpan={7} sx={{ py: 5, textAlign: 'center' }}>
                <Typography variant="subtitle2">По выбранным фильтрам ничего не найдено</Typography>
                <Button size="small" sx={{ mt: 1 }} onClick={() => { setQuery(''); setProduct('all'); setOnlyPending(false); setSelected([]); setPage(0) }}>Сбросить фильтры</Button>
              </TableCell></TableRow>
            ) : visibleRows.map((row) => {
              const eligible = isEligible(row)
              const checked = selected.includes(row.id)
              return (
                <TableRow key={row.id} hover selected={checked}>
                  <TableCell padding="checkbox">
                    <Tooltip title={eligible ? 'Выбрать КИЗ' : 'КИЗ уже выведен'}>
                      <span>
                        <Checkbox
                          checked={checked} disabled={!eligible}
                          onChange={() => setSelected((current) => checked ? current.filter((id) => id !== row.id) : [...current, row.id])}
                          slotProps={{ input: { 'aria-label': `Выбрать КИЗ товара ${row.product}` } }}
                        />
                      </span>
                    </Tooltip>
                  </TableCell>
                  <TableCell>{formatDate(row.transferDate)}</TableCell>
                  <TableCell>
                    <Link component="button" type="button" underline="hover" onClick={() => setDetails(row)} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25, whiteSpace: 'nowrap', fontSize: '0.78rem' }}>
                      {row.documentNumber}<OpenInNewOutlined sx={{ fontSize: 13 }} />
                    </Link>
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{row.sku}</TableCell>
                  <TableCell>
                    <Typography variant="caption" sx={{ display: 'block', lineHeight: 1.25 }}>{row.product} · {row.size}</Typography>
                  </TableCell>
                  <TableCell>
                    <Tooltip title="Полный КИЗ доступен в деталях заказа">
                      <Typography component="code" variant="body2" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', overflowWrap: 'anywhere' }}>{compactKiz(row.kiz)}</Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell><RowStatus row={row} /></TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={filteredRows.length}
          page={currentPage}
          onPageChange={(_, nextPage) => { setPage(nextPage); setSelected([]) }}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(event) => { setRowsPerPage(Number(event.target.value)); setPage(0); setSelected([]) }}
          rowsPerPageOptions={[50, 100, 250]}
          labelRowsPerPage="На странице"
          labelDisplayedRows={({ from, to, count }) => `${from}–${to} из ${count}`}
          sx={{ '& .MuiTablePagination-toolbar': { minHeight: 44, flexWrap: 'wrap', justifyContent: 'flex-end' } }}
        />
      </Paper>

      <Paper
        variant="outlined"
        sx={{ position: 'sticky', bottom: 12, zIndex: 2, p: 1.5, boxShadow: '0 10px 30px rgba(15,23,42,.14)' }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
          <Typography variant="subtitle2">Выбрано КИЗ: {selectedRows.length}</Typography>
          <Button variant="contained" disabled={selectedRows.length === 0} onClick={openOperation} startIcon={<KeyOutlined />}>
            Вывести из оборота ({selectedRows.length})
          </Button>
        </Stack>
      </Paper>

      </>}

      <Dialog open={Boolean(details)} onClose={() => setDetails(null)} fullWidth maxWidth="sm" aria-labelledby="document-details-title">
        {details ? <>
          <DialogTitle id="document-details-title" sx={{ pr: 6 }}>
            Заказ WB № {details.documentNumber}
            <IconButton aria-label="Закрыть" onClick={() => setDetails(null)} sx={{ position: 'absolute', right: 12, top: 12 }}><CloseOutlined /></IconButton>
          </DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <Chip variant="outlined" label={`Передано WB ${formatDate(details.transferDate)}`} sx={{ alignSelf: 'flex-start' }} />
              <Box><Typography variant="caption" color="text.secondary">Товар</Typography><Typography>{details.product}, {details.size}</Typography><Typography variant="body2" color="text.secondary">{details.sku}</Typography></Box>
              <Box><Typography variant="caption" color="text.secondary">Привязанный КИЗ</Typography><Typography component="code" sx={{ display: 'block', overflowWrap: 'anywhere' }}>{details.kiz}</Typography></Box>
              <Divider />
              <RowStatus row={details} />
              {details.withdrawnAt ? <Typography variant="body2">Дата вывода: {details.withdrawnAt}</Typography> : null}
              {details.crptDocument ? <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>Документ ЧЗ: {details.crptDocument}</Typography> : null}
            </Stack>
          </DialogContent>
          <DialogActions><Button onClick={() => setDetails(null)}>Закрыть</Button></DialogActions>
        </> : null}
      </Dialog>

<Dialog open={certificateOpen} onClose={closeCertificate} fullWidth maxWidth="sm" aria-labelledby="certificate-dialog-title">
        <DialogTitle id="certificate-dialog-title" sx={{ pr: 6 }}>
          Выберите сертификат
          <IconButton aria-label="Закрыть" disabled={submitting} onClick={closeCertificate} sx={{ position: 'absolute', right: 12, top: 12 }}>
            <CloseOutlined />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <CertificateCard selected={certificateSelected} onSelect={() => setCertificateSelected(true)} />
            <Typography variant="body2" color="text.secondary">
              Закрытый ключ и PIN остаются на этом компьютере.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button disabled={submitting} onClick={closeCertificate}>Отмена</Button>
          <Button
            variant="contained"
            disabled={!certificateSelected || submitting}
            startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <KeyOutlined />}
            onClick={submitOperation}
          >
            {submitting ? 'Подписываем и отправляем…' : 'Подписать и отправить'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={failedRows.length > 0} onClose={() => setFailedRows([])} fullWidth maxWidth="md" aria-labelledby="withdrawal-error-dialog-title">
        <DialogTitle id="withdrawal-error-dialog-title" sx={{ pr: 6 }}>
          Честный знак не принял часть КИЗ
          <IconButton aria-label="Закрыть" onClick={() => setFailedRows([])} sx={{ position: 'absolute', right: 12, top: 12 }}>
            <CloseOutlined />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ p: { xs: 1, sm: 2 } }}>
          <TableContainer sx={{ maxWidth: '100%', overflowX: 'auto' }}>
            <Table size="small" aria-label="Ошибки Честного знака" sx={{ minWidth: 680 }}>
              <TableHead>
                <TableRow>
                  <TableCell>КИЗ</TableCell>
                  <TableCell>Заказ WB</TableCell>
                  <TableCell>Причина</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {failedRows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <Tooltip title={row.kiz}>
                        <Typography component="code" variant="caption" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                          {compactKiz(row.kiz)}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>№ {row.documentNumber}</TableCell>
                    <TableCell>{row.statusDetail}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
        <DialogActions>
          <Button variant="contained" onClick={() => setFailedRows([])}>Закрыть</Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={3200}
        onClose={() => setToast('')}
        message={toast}
      />
    </Stack>
  )
}
