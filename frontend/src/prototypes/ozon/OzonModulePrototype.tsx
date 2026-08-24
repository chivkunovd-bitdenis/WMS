import { useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Radio,
  Select,
  Skeleton,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'
import { PageHeader } from '../../ui/PageHeader'
import { StatusChip, type StatusTone } from '../../ui-kit/StatusChip'

type AccountKey = 'loviana' | 'fashion'
type Posting = {
  id: string
  deadline: string
  goods: string
  seller: string
  warehouse: string
  handover: string
  next: string
  status: string
  tone: StatusTone
  detail: string
}

const accounts = {
  loviana: {
    title: 'Ozon Loviana', seller: 'Loviana', health: 'active_read_only',
    hint: 'Синхронизация: 24.08.2026, 10:42 · данные подтверждены',
  },
  fashion: {
    title: 'Ozon Fashion', seller: 'Fashion', health: 'pending_credentials',
    hint: 'Client-Id не указан · discovery не запускался',
  },
} as const

const postings: Posting[] = [
  { id: '4829-0001-1', deadline: 'Сегодня, 16:00', goods: '2 позиции · 3 шт.', seller: 'Loviana', warehouse: 'Основной · A-03-02', handover: 'По одному', next: 'Связать товар', status: 'Нет сопоставления', tone: 'stop', detail: 'Одна строка сопоставлена, вторая требует решения администратора.' },
  { id: '4829-0002-1', deadline: 'Сегодня, 17:30', goods: '1 позиция · 2 шт.', seller: 'Loviana', warehouse: 'Основной · B-01-04', handover: 'По одному', next: 'Продолжить маркировку', status: '1 код отклонён', tone: 'warn', detail: 'KIZ и IMEI обязательны; один экземпляр принят Ozon.' },
  { id: '4829-0003-1', deadline: 'Завтра, 11:00', goods: '2 позиции · 3 шт.', seller: 'Loviana', warehouse: 'Основной · A-04-01', handover: 'Carriage', next: 'Печатать', status: 'Этикетка ожидается', tone: 'warn', detail: 'Частичная упаковка создана; первая этикетка устарела.' },
  { id: '4829-0004-1', deadline: 'Отменено', goods: '1 позиция · 1 шт.', seller: 'Loviana', warehouse: 'Основной · C-02-01', handover: '—', next: 'Разобрать проблему', status: 'Отмена после подбора', tone: 'stop', detail: 'Нужен обратный scan ячейки, остаток ещё не освобождён.' },
  { id: '4829-0005-1', deadline: 'Сегодня, 15:30', goods: '1 позиция · 1 шт.', seller: 'Loviana', warehouse: 'Основной · A-02-05', handover: 'По одному', next: 'Подтвердить передачу', status: 'Ozon ещё не сканировал', tone: 'warn', detail: 'WMS передача зафиксирована; требуется арбитраж руководителя смены.' },
]

const fbsSteps = ['Проверка', 'Подбор', 'Данные единиц', 'Упаковка', 'Этикетка', 'Сдача', 'Подтверждение']
const fboSteps = ['Черновик', 'Таймслот', 'Состав', 'Подбор и упаковка', 'Грузоместа', 'ТГМ', 'Этикетки', 'Сдача', 'Приёмка и акт']

function Shell({ section, children }: { section: 'fbs' | 'fbo' | 'returns' | 'catalog' | 'connection'; children: ReactNode }) {
  const navigate = useNavigate()
  const [account, setAccount] = useState<AccountKey>('loviana')
  const accountInfo = accounts[account]
  const tabValue = ['fbs', 'fbo', 'returns', 'catalog', 'connection'].indexOf(section)
  const destinations = ['/app/ff/ozon/fbs', '/app/ff/ozon/fbo', '/app/ff/ozon/returns', '/app/ff/ozon/catalog', '/app/ff/ozon/connection']
  return (
    <Stack spacing={2.25} data-testid="ozon-module">
      <PageHeader title="Ozon" description="Кликабельный S0-прототип: только локальные fixtures, без API Ozon и без публикации остатков." />
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: { md: 'center' } }}>
          <FormControl size="small" sx={{ minWidth: 250 }}>
            <InputLabel id="ozon-account-select-label">Селлер и кабинет</InputLabel>
            <Select labelId="ozon-account-select-label" label="Селлер и кабинет" value={account} data-testid="ozon-account-select" onChange={(event) => setAccount(event.target.value as AccountKey)}>
              <MenuItem value="loviana">Loviana · Ozon Loviana · WB подключён</MenuItem>
              <MenuItem value="fashion">Fashion · Ozon Fashion · требуется Client-Id</MenuItem>
            </Select>
          </FormControl>
          <Typography variant="body2" color="text.secondary" data-testid="ozon-sync-health">{accountInfo.hint}</Typography>
          <StatusChip label={accountInfo.health === 'active_read_only' ? 'Read-only active' : 'Pending credentials'} tone={accountInfo.health === 'active_read_only' ? 'ok' : 'warn'} />
        </Stack>
        <Alert severity={account === 'loviana' ? 'warning' : 'error'} sx={{ mt: 2 }} data-testid="ozon-account-health">
          {account === 'loviana'
            ? 'Частичная пагинация: показаны последние подтверждённые данные. Повтор запроса назначен после 429.'
            : 'Кабинет Fashion изолирован: есть только Api-Key, discovery и операции не выполнялись.'}
        </Alert>
      </Paper>
      <Tabs value={tabValue} onChange={(_, value: number) => navigate(destinations[value])} variant="scrollable" data-testid="ozon-module-tabs">
        <Tab label="FBS" /><Tab label="FBO" /><Tab label="Возвраты" /><Tab label="Каталог и связи" /><Tab label="Подключение" />
      </Tabs>
      {children}
    </Stack>
  )
}

function QueueTable({ columns, children, testId }: { columns: string[]; children: ReactNode; testId: string }) {
  return <TableContainer component={Paper} variant="outlined" data-testid={testId}><Table size="small"><TableHead><TableRow>{columns.map((column) => <TableCell key={column}>{column}</TableCell>)}</TableRow></TableHead><TableBody>{children}</TableBody></Table></TableContainer>
}

export function OzonFbsPrototype() {
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)
  const [mode, setMode] = useState<'live' | 'loading' | 'empty' | 'error'>('live')
  const rows = mode === 'live' ? postings : []
  return <Shell section="fbs"><Stack spacing={2}>
    <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1} sx={{ alignItems: { lg: 'center' } }}>
      <Tabs value={tab} onChange={(_, value) => setTab(value)}><Tab label="К сборке" /><Tab label="В работе" /><Tab label="К сдаче" /><Tab label="Переданы" /><Tab label="Проблемы" /></Tabs>
      <Box sx={{ flex: 1 }} /><TextField size="small" label="Поиск" placeholder="Отправление, SKU" /><Select size="small" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><MenuItem value="live">Fixtures: очередь</MenuItem><MenuItem value="loading">Fixtures: загрузка</MenuItem><MenuItem value="empty">Fixtures: пусто</MenuItem><MenuItem value="error">Fixtures: ошибка</MenuItem></Select>
    </Stack>
    {mode === 'error' ? <Alert severity="error">Очередь не обновилась после 429. Оставлены данные последней успешной синхронизации; безопасное действие — повторить позже.</Alert> : null}
    <QueueTable testId="ozon-fbs-queue" columns={['Отправление и срок', 'Товары', 'Селлер и склад', 'Сдача', 'Следующий шаг']}>
      {mode === 'loading' ? Array.from({ length: 4 }).map((_, index) => <TableRow key={index}><TableCell colSpan={5}><Skeleton height={24} /></TableCell></TableRow>) : null}
      {mode === 'empty' ? <TableRow><TableCell colSpan={5}><Stack sx={{ py: 3 }} spacing={1}><Typography variant="subtitle2">В этой вкладке нет отправлений</Typography><Typography variant="body2" color="text.secondary">Новые postings появятся после следующего безопасного read-only обновления.</Typography></Stack></TableCell></TableRow> : null}
      {rows.map((posting) => <TableRow key={posting.id} hover><TableCell><Typography sx={{ fontWeight: 700 }}>{posting.id}</Typography><Typography variant="body2" color="text.secondary">{posting.deadline}</Typography></TableCell><TableCell>{posting.goods}</TableCell><TableCell>{posting.seller}<br />{posting.warehouse}</TableCell><TableCell>{posting.handover}</TableCell><TableCell><Stack spacing={.5} sx={{ alignItems: 'flex-start' }}><StatusChip label={posting.status} tone={posting.tone} /><Button size="small" variant="contained" data-testid={`ozon-posting-next-action-${posting.id}`} onClick={() => navigate(`/app/ff/ozon/fbs/${posting.id}`)}>{posting.next}</Button></Stack></TableCell></TableRow>)}
    </QueueTable>
    <Alert severity="info">Неизвестный внешний status сохраняется как «требует внимания»: работа не теряется, но итог не подменяется успехом.</Alert>
  </Stack></Shell>
}

function FbsWorkspace() {
  const { postingId = '4829-0001-1' } = useParams()
  const posting = postings.find((item) => item.id === postingId) ?? postings[0]
  const [step, setStep] = useState(postingId === '4829-0004-1' ? 1 : 0)
  const [location, setLocation] = useState('')
  const [product, setProduct] = useState('')
  const [unitStatus, setUnitStatus] = useState(postingId === '4829-0002-1' ? 'Отклонён Ozon' : 'Требует данных')
  const [partial, setPartial] = useState(false)
  const [label, setLabel] = useState<'pending' | 'ready' | 'error'>('pending')
  const [preflight, setPreflight] = useState(false)
  const [handover, setHandover] = useState('one')
  const [recovery, setRecovery] = useState(false)
  const [mappingOpen, setMappingOpen] = useState(false)
  const [correctionOpen, setCorrectionOpen] = useState(false)
  const [labelNotice, setLabelNotice] = useState('')
  const [arbitration, setArbitration] = useState(false)
  const isCancelled = postingId === '4829-0004-1'
  const nextStep = () => setStep((value) => Math.min(value + 1, fbsSteps.length - 1))
  return <Shell section="fbs"><Stack spacing={2}>
    <Paper variant="outlined" sx={{ p: 2, position: 'sticky', top: 8, zIndex: 1, bgcolor: 'background.paper' }}><Stack direction={{ xs: 'column', md: 'row' }} spacing={2}><Box sx={{ flex: 1 }}><Typography variant="h6">{posting.id}</Typography><Typography variant="body2" color="text.secondary">Срок: {posting.deadline} · Маршрут: {posting.handover} · Ozon: {posting.status} · WMS: {isCancelled ? 'обратная работа' : 'в обработке'}</Typography></Box><StatusChip label="2 позиции / 3 единицы" /><Typography variant="body2">Обновлено Ozon: 10:42</Typography></Stack></Paper>
    <Stepper activeStep={step} alternativeLabel sx={{ overflowX: 'auto' }}>{fbsSteps.map((labelText) => <Step key={labelText}><StepLabel>{labelText}</StepLabel></Step>)}</Stepper>
    {step === 0 ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Проверка строк</Typography><QueueTable testId="ozon-check-lines" columns={['Товар', 'Нужно', 'Резерв', 'Склад', 'Сопоставление']}><TableRow><TableCell>Платье «Margo», OZ-2201</TableCell><TableCell>2</TableCell><TableCell>2</TableCell><TableCell>A-03-02</TableCell><TableCell><StatusChip label="Связано" tone="ok" /></TableCell></TableRow><TableRow><TableCell>Сумка «Luna», OZ-2202</TableCell><TableCell>1</TableCell><TableCell>0</TableCell><TableCell>—</TableCell><TableCell><Button size="small" onClick={() => setMappingOpen(true)}>Связать товар</Button></TableCell></TableRow></QueueTable><Stack direction="row" sx={{ mt: 2, justifyContent: 'flex-end' }}><Button variant="contained" onClick={nextStep}>Начать подбор</Button></Stack></Paper> : null}
    {step === 1 ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Подбор из ячейки</Typography><Alert severity={isCancelled ? 'warning' : 'info'} sx={{ my: 1.5 }}>{isCancelled ? 'Отменено после подбора. Просканируйте подтверждённую ячейку для обратного движения; остаток не освободится автоматически.' : 'Сначала сканируйте ячейку, затем товар. Другой seller или лишняя line будут отклонены.'}</Alert><Stack direction={{ xs: 'column', md: 'row' }} spacing={1}><TextField autoFocus value={location} onChange={(event) => setLocation(event.target.value)} label={isCancelled ? 'Ячейка возврата' : 'Скан ячейки'} data-testid="ozon-scan-location" /><TextField disabled={!location} value={product} onChange={(event) => setProduct(event.target.value)} label="Скан товара" data-testid="ozon-scan-product" /><Button variant="contained" disabled={!location || (!isCancelled && !product)} onClick={() => { setRecovery(isCancelled); if (!isCancelled) nextStep() }}>{isCancelled ? 'Вернуть в ячейку' : 'Принять единицу'}</Button></Stack>{recovery ? <Alert severity="success" sx={{ mt: 2 }}>Обратное движение проведено в {location}; резерв освобождён после физического подтверждения.</Alert> : null}<Typography variant="body2" sx={{ mt: 2 }}>Подобрано: {isCancelled && recovery ? '0 / 1' : '1 / 3'} · Последний scan: {location || 'ещё нет'} <Button size="small" onClick={() => { setLocation(''); setProduct('') }}>Отменить последний scan</Button></Typography></Paper> : null}
    {step === 2 ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Данные экземпляров</Typography><Stack spacing={1.5} sx={{ mt: 1 }}><Paper variant="outlined" sx={{ p: 1.5 }} data-testid="ozon-unit-identifier-1"><Typography sx={{ fontWeight: 700 }}>Экземпляр 1 · Платье «Margo»</Typography><Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}><TextField label="KIZ" defaultValue="010460123456789021abc" /><TextField label="IMEI" defaultValue="356938035643809" /><StatusChip label="Принят Ozon" tone="ok" /></Stack></Paper><Paper variant="outlined" sx={{ p: 1.5 }} data-testid="ozon-unit-identifier-2"><Typography sx={{ fontWeight: 700 }}>Экземпляр 2 · Платье «Margo»</Typography><Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}><TextField label="KIZ" error={unitStatus === 'Отклонён Ozon'} defaultValue="010460123456789021bad" /><StatusChip label={unitStatus} tone={unitStatus === 'Принят Ozon' ? 'ok' : 'stop'} /><Button onClick={() => setCorrectionOpen(true)}>Исправить до фиксации</Button></Stack></Paper></Stack><Button variant="contained" sx={{ mt: 2 }} disabled={unitStatus !== 'Принят Ozon'} onClick={nextStep}>Перейти к упаковке</Button></Paper> : null}
    {step === 3 ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Упаковка</Typography><Alert severity="warning" sx={{ my: 1 }}>Ограничения Ozon: вес до 20 кг, упаковка фиксирует количество, а не всю строку.</Alert><QueueTable testId="ozon-package-lines" columns={['WMS короб', 'Товар', 'Подобрано', 'В package']}><TableRow><TableCell>BOX-048</TableCell><TableCell>Платье «Margo»</TableCell><TableCell>2</TableCell><TableCell>{partial ? '1' : '2'}</TableCell></TableRow><TableRow><TableCell>BOX-049</TableCell><TableCell>Сумка «Luna»</TableCell><TableCell>1</TableCell><TableCell>{partial ? '1' : '0'}</TableCell></TableRow></QueueTable><Stack direction="row" spacing={1} sx={{ mt: 2 }}><Button onClick={() => setPartial(true)}>Создать частичный package</Button><Button variant="contained" onClick={nextStep}>Подтвердить состав</Button></Stack>{partial ? <Alert severity="info" sx={{ mt: 2 }}>Создан второй package: первая строка не стала целиком упакованной.</Alert> : null}</Paper> : null}
    {step === 4 ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Этикетка package</Typography><Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} data-testid="ozon-label-status"><StatusChip label={label === 'pending' ? 'Запрашивается асинхронно' : label === 'ready' ? 'Готова v2' : 'Ошибка генерации'} tone={label === 'ready' ? 'ok' : label === 'error' ? 'stop' : 'warn'} /><Button onClick={() => setLabel('ready')}>Проверить readback</Button><Button onClick={() => setLabel('error')}>Показать ошибку fixture</Button></Stack>{label === 'ready' ? <Stack direction="row" spacing={1} sx={{ mt: 2 }}><Button variant="outlined" onClick={() => setLabelNotice('Предпросмотр v2 открыт в fixture.')}>Предпросмотр</Button><Button variant="contained" onClick={() => setLabelNotice('Этикетка v2 отправлена на fixture-печать.')}>Печать</Button><FormControlLabel control={<Checkbox />} label="Этикетка нанесена" /></Stack> : null}{labelNotice ? <Alert severity="success" sx={{ mt: 1 }}>{labelNotice}</Alert> : null}<Alert severity="warning" sx={{ mt: 2 }}>Этикетка v1 superseded: её нельзя выбрать основной для печати.</Alert><Button variant="contained" sx={{ mt: 2 }} disabled={label !== 'ready'} onClick={nextStep}>К сдаче</Button></Paper> : null}
    {step === 5 ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Сдача</Typography><Stack spacing={1} sx={{ mt: 1 }}><Paper variant="outlined" sx={{ p: 1 }}><FormControlLabel control={<Radio checked={handover === 'one'} onChange={() => setHandover('one')} />} label="По одному — физически сканировать barcode каждого posting" /></Paper><Paper variant="outlined" sx={{ p: 1 }}><FormControlLabel control={<Radio checked={handover === 'carriage'} onChange={() => setHandover('carriage')} />} label="Carriage — только совместимые postings, акт отдельно" /></Paper><Paper variant="outlined" sx={{ p: 1 }}><FormControlLabel control={<Radio checked={handover === 'manual'} onChange={() => setHandover('manual')} />} label="Вручную в кабинете — затем readback, статус не ставится руками" /></Paper></Stack><Button variant="contained" sx={{ mt: 2 }} onClick={() => setPreflight(true)} data-testid="ozon-handover-preflight">Проверить перед передачей</Button></Paper> : null}
    {step === 6 ? <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Подтверждение</Typography><Stepper activeStep={postingId === '4829-0005-1' ? 1 : 0}><Step><StepLabel>Передано WMS</StepLabel></Step><Step><StepLabel>Ozon сканирует</StepLabel></Step><Step><StepLabel>Доставляется</StepLabel></Step><Step><StepLabel>Доставлено</StepLabel></Step></Stepper>{postingId === '4829-0005-1' ? <Alert severity="warning" sx={{ mt: 2 }}>Внешний scan не подтверждён. Только руководитель смены может открыть арбитраж.</Alert> : null}<Button sx={{ mt: 2 }} disabled={postingId !== '4829-0005-1'} onClick={() => setArbitration(true)}>Открыть арбитраж (руководитель смены)</Button>{arbitration ? <Alert severity="info" sx={{ mt: 1 }}>Fixture арбитража открыт: приложите акт и ждите внешнего readback.</Alert> : null}</Paper> : null}
    <Dialog open={mappingOpen} onClose={() => setMappingOpen(false)}><DialogTitle>Связать товар Ozon</DialogTitle><DialogContent><Typography>Кандидат: «Сумка Luna» — точный seller SKU, подтвердите account-scoped связь.</Typography></DialogContent><DialogActions><Button onClick={() => setMappingOpen(false)}>Отмена</Button><Button variant="contained" onClick={() => setMappingOpen(false)}>Подтвердить связь</Button></DialogActions></Dialog>
    <Dialog open={correctionOpen} onClose={() => setCorrectionOpen(false)}><DialogTitle>Исправить идентификатор</DialogTitle><DialogContent><TextField fullWidth label="Исправленный KIZ" defaultValue="010460123456789021ok" sx={{ mt: 1 }} /></DialogContent><DialogActions><Button onClick={() => setCorrectionOpen(false)}>Отмена</Button><Button variant="contained" onClick={() => { setUnitStatus('Принят Ozon'); setCorrectionOpen(false) }}>Сохранить и проверить</Button></DialogActions></Dialog>
    <Dialog open={preflight} onClose={() => setPreflight(false)}><DialogTitle>Preflight передачи</DialogTitle><DialogContent><Stack spacing={1}><Alert severity="success">Пройдены: актуальная этикетка, состав package, accepted exemplars.</Alert><Alert severity={handover === 'carriage' ? 'warning' : 'success'}>{handover === 'carriage' ? 'Акт carriage ещё ожидается — передача останется uncertain.' : 'Физический способ сдачи подтверждён.'}</Alert></Stack></DialogContent><DialogActions><Button onClick={() => setPreflight(false)}>Назад</Button><Button variant="contained" onClick={() => { setPreflight(false); nextStep() }}>Зафиксировать передачу WMS</Button></DialogActions></Dialog>
  </Stack></Shell>
}

export function OzonFboPrototype() {
  const navigate = useNavigate(); const [tab, setTab] = useState(0); const [state, setState] = useState<'rows'|'loading'|'empty'|'error'>('rows'); const [wizard, setWizard] = useState(false)
  return <Shell section="fbo"><Stack spacing={2}><Stack direction={{ xs: 'column', md: 'row' }} spacing={1}><Tabs value={tab} onChange={(_, value) => setTab(value)}><Tab label="Черновики" /><Tab label="Таймслот" /><Tab label="Готовим груз" /><Tab label="К сдаче" /><Tab label="Приёмка Ozon" /><Tab label="Расхождения" /><Tab label="Завершены" /></Tabs><Box sx={{ flex: 1 }} /><Select size="small" value={state} onChange={(event) => setState(event.target.value as typeof state)}><MenuItem value="rows">Fixtures: данные</MenuItem><MenuItem value="loading">Загрузка</MenuItem><MenuItem value="empty">Пусто</MenuItem><MenuItem value="error">Ошибка async</MenuItem></Select><Button variant="contained" onClick={() => setWizard(true)}>Создать поставку FBO</Button></Stack>{state === 'error' ? <Alert severity="error">Операция создания draft uncertain: сначала выполните readback, новый draft не создаётся.</Alert> : null}<QueueTable testId="ozon-fbo-queue" columns={['Заявка', 'Маршрут и таймслот', 'Состав', 'Грузоместа', 'Приёмка', 'Следующий шаг']}>{state === 'loading' ? <TableRow><TableCell colSpan={6}><Skeleton height={32} /></TableCell></TableRow> : null}{state === 'empty' ? <TableRow><TableCell colSpan={6}><Typography sx={{ py: 3 }}>В этой вкладке нет заявок. Создайте FBO plan только для доступного маршрута.</Typography></TableCell></TableRow> : null}{state === 'rows' ? <TableRow><TableCell>SO-80931<br /><StatusChip label="Таймслот ожидает" tone="warn" /></TableCell><TableCell>Direct · Хоругвино<br />26.08, 10:00–12:00</TableCell><TableCell>3 строки · план 10 / упаковано 10</TableCell><TableCell>2 cargo · 1 ТГМ</TableCell><TableCell>9 принято · 1 отклонено</TableCell><TableCell><Button variant="contained" size="small" onClick={() => navigate('/app/ff/ozon/fbo/SO-80931')}>Продолжить</Button></TableCell></TableRow> : null}</QueueTable><Alert severity="warning">Последняя успешная pagination частична: неизвестная следующая страница не скрывает подтверждённые plans.</Alert>
    <Dialog open={wizard} onClose={() => setWizard(false)} maxWidth="sm" fullWidth><DialogTitle>Новая поставка FBO</DialogTitle><DialogContent><Stepper activeStep={2} alternativeLabel sx={{ my: 2 }}><Step><StepLabel>Кабинет</StepLabel></Step><Step><StepLabel>Склад</StepLabel></Step><Step><StepLabel>Маршрут</StepLabel></Step><Step><StepLabel>Состав</StepLabel></Step></Stepper><Stack spacing={1.5}><TextField select label="Селлер / account" defaultValue="loviana"><MenuItem value="loviana">Loviana · Ozon Loviana</MenuItem></TextField><TextField select label="Физический WMS склад" defaultValue="main"><MenuItem value="main">Основной склад</MenuItem></TextField><Paper variant="outlined" sx={{ p: 1 }}><FormControlLabel control={<Radio checked />} label="Direct · доступен для этого account" /></Paper><Paper variant="outlined" sx={{ p: 1 }}><FormControlLabel disabled control={<Radio />} label="Multi-cluster · capability не обнаружена" /></Paper><TextField label="Платье Margo, количество" defaultValue="10" type="number" /><Alert severity="info">Capability summary: draft/supply — async с readback; остатки Ozon не публикуются.</Alert></Stack></DialogContent><DialogActions><Button onClick={() => setWizard(false)}>Отмена</Button><Button variant="contained" onClick={() => { setWizard(false); navigate('/app/ff/ozon/fbo/SO-80931') }}>Создать intent</Button></DialogActions></Dialog>
  </Stack></Shell>
}

function FboWorkspace() {
  const [step, setStep] = useState(1); const [readback, setReadback] = useState(false); const [linked, setLinked] = useState(false); const [tgm, setTgm] = useState(false); const [label, setLabel] = useState(false)
  return <Shell section="fbo"><Stack spacing={2}><Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">SO-80931 · Direct в Хоругвино</Typography><Typography variant="body2" color="text.secondary">FBO supply: локальный plan и внешний supply order показываются отдельно.</Typography></Paper><Stepper activeStep={step} alternativeLabel sx={{ overflowX: 'auto' }}>{fboSteps.map((labelText) => <Step key={labelText}><StepLabel>{labelText}</StepLabel></Step>)}</Stepper><Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Async draft и таймслот</Typography><Stack direction="row" spacing={1} sx={{ my: 1 }}><StatusChip label={readback ? 'Подтверждено readback' : 'Operation pending / uncertain'} tone={readback ? 'ok' : 'warn'} /><Button variant="outlined" onClick={() => setReadback(true)}>Прочитать статус операции</Button></Stack><LinearProgress variant={readback ? 'determinate' : 'indeterminate'} value={readback ? 100 : undefined} /><Button variant="contained" sx={{ mt: 2 }} disabled={!readback} onClick={() => setStep(4)}>Перейти к грузоместам</Button></Paper><Paper variant="outlined" sx={{ p: 2 }} data-testid="ozon-cargo-zone"><Typography variant="h6">Cargo: WMS boxes → Ozon cargo</Typography><Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 1 }}><Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}><Typography sx={{ fontWeight: 700 }}>WMS boxes</Typography><FormControlLabel control={<Checkbox checked={linked} onChange={(_, value) => setLinked(value)} />} label="BOX-201 · 6 шт. → Cargo C-01" /><FormControlLabel control={<Checkbox checked={linked} onChange={(_, value) => setLinked(value)} />} label="BOX-202 · 4 шт. → Cargo C-02" /></Paper><Paper variant="outlined" sx={{ p: 1.5, flex: 1 }}><Typography sx={{ fontWeight: 700 }}>Ozon cargo</Typography><Typography>C-01: 6 шт. · label ready</Typography><Typography>C-02: 4 шт. · label failed (частичное состояние)</Typography><Button size="small" disabled={!linked}>Связать выбранное</Button></Paper></Stack>{linked ? <Alert severity="success" sx={{ mt: 1 }}>Связь сохранена по явному действию; WMS box не был автоматически объявлен cargo.</Alert> : null}</Paper><Paper variant="outlined" sx={{ p: 2 }} data-testid="ozon-tgm-zone"><Typography variant="h6">ТГМ отдельно от cargo</Typography><FormControlLabel control={<Checkbox checked={tgm} onChange={(_, value) => setTgm(value)} />} label="TGM-01 содержит C-01 и C-02" /><Typography variant="body2" color="text.secondary">Один ТГМ может содержать несколько cargo.</Typography></Paper><Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Этикетки cargo / ТГМ</Typography><QueueTable testId="ozon-fbo-labels" columns={['Объект', 'Версия', 'Статус', 'Действие']}><TableRow><TableCell>C-01</TableCell><TableCell>v1</TableCell><TableCell><StatusChip label="Готова" tone="ok" /></TableCell><TableCell><FormControlLabel control={<Checkbox checked={label} onChange={(_, value) => setLabel(value)} />} label="Нанесена" /></TableCell></TableRow><TableRow><TableCell>C-02</TableCell><TableCell>v1</TableCell><TableCell><StatusChip label="Ошибка async" tone="stop" /></TableCell><TableCell><Button size="small">Повторить после readback</Button></TableCell></TableRow><TableRow><TableCell>TGM-01</TableCell><TableCell>v2</TableCell><TableCell><StatusChip label="Superseded v1" tone="warn" /></TableCell><TableCell><Button size="small" disabled={!tgm}>Печать v2</Button></TableCell></TableRow></QueueTable></Paper><Paper variant="outlined" sx={{ p: 2 }} data-testid="ozon-acceptance-act"><Typography variant="h6">Приёмка и акт</Typography><QueueTable testId="ozon-acceptance-table" columns={['Товар', 'План', 'Принято', 'Отклонено', 'Причина']}><TableRow><TableCell>Платье «Margo»</TableCell><TableCell>10</TableCell><TableCell>9</TableCell><TableCell>1</TableCell><TableCell>Повреждена упаковка</TableCell></TableRow></QueueTable><Stack direction="row" spacing={1} sx={{ mt: 2 }}><Button variant="contained" disabled={!label}>Согласовать акт</Button><Button>Открыть инструкцию ручной проверки</Button></Stack></Paper></Stack></Shell>
}

type ReturnRow = { id: string; source: string; product: string; point: string; action: string; status: StatusTone }
const returnRows: ReturnRow[] = [
  { id: 'RET-7781', source: 'FBS · 4829-0002-1', product: 'Платье Margo · 1 шт.', point: 'ПВЗ Ozon · до 25.08', action: 'Принять в карантин', status: 'warn' },
  { id: 'RET-7782', source: 'FBO · SO-80931', product: 'Сумка Luna · 1 шт.', point: 'Склад Ozon · до 26.08', action: 'Осмотреть', status: 'warn' },
  { id: 'RET-7783', source: 'Не сопоставлен', product: 'Внешний SKU OZ-unknown · 1 шт.', point: 'ПВЗ Ozon · сегодня', action: 'Принять в карантин', status: 'stop' },
]

export function OzonReturnsPrototype() { const navigate = useNavigate(); const [tab, setTab] = useState(0); const [empty, setEmpty] = useState(false); return <Shell section="returns"><Stack spacing={2}><Stack direction="row" spacing={1}><Tabs value={tab} onChange={(_, value) => setTab(value)}><Tab label="Ожидаются" /><Tab label="К получению" /><Tab label="На осмотре" /><Tab label="Решение" /><Tab label="Закрыты" /><Tab label="Не сопоставлены" /></Tabs><Box sx={{ flex: 1 }} /><Button onClick={() => setEmpty(!empty)}>{empty ? 'Показать fixtures' : 'Показать пустоту'}</Button></Stack><QueueTable testId="ozon-returns-queue" columns={['Возврат', 'Источник FBS/FBO', 'Товар и количество', 'Точка/срок', 'Следующий шаг']}>{empty ? <TableRow><TableCell colSpan={5}>Нет возвратов в этой вкладке. Внешний статус не создаёт остаток.</TableCell></TableRow> : returnRows.map((row) => <TableRow key={row.id}><TableCell>{row.id}</TableCell><TableCell>{row.source}</TableCell><TableCell>{row.product}</TableCell><TableCell>{row.point}</TableCell><TableCell><StatusChip label={row.source === 'Не сопоставлен' ? 'Нужна связь' : 'Карантин'} tone={row.status} /><Button size="small" sx={{ display: 'block', mt: 1 }} variant="contained" onClick={() => navigate(`/app/ff/ozon/returns/${row.id}`)}>{row.action}</Button></TableCell></TableRow>)}</QueueTable><Alert severity="info">Каждый FBS/FBO return сначала создаёт quarantine intake. Авто-возврата в доступный остаток нет.</Alert></Stack></Shell> }

function ReturnWorkspace() { const { id = 'RET-7783' } = useParams(); const [scan, setScan] = useState(''); const [quarantine, setQuarantine] = useState(false); const [inspection, setInspection] = useState(false); const [disposition, setDisposition] = useState(''); return <Shell section="returns"><Stack spacing={2}><Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Возврат {id}</Typography><Typography variant="body2" color="text.secondary">Маскированный exemplar: 01046••••••89021 · связь с исходной единицей {id === 'RET-7783' ? 'не найдена' : 'найдена'}.</Typography></Paper><Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Фактическое получение</Typography><Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}><TextField label="Скан posting / return / товара" value={scan} onChange={(event) => setScan(event.target.value)} /><Button variant="contained" disabled={!scan} onClick={() => setQuarantine(true)}>Создать приёмку в карантине</Button></Stack>{quarantine ? <Alert severity="success" sx={{ mt: 2 }}>Inbound request создана в зоне QUARANTINE. Доступный остаток не изменён.</Alert> : null}</Paper><Paper variant="outlined" sx={{ p: 2 }} data-testid="ozon-return-disposition"><Typography variant="h6">Осмотр и решение</Typography><Alert severity="warning" sx={{ my: 1 }}>Решение по умолчанию отсутствует: сотрудник обязан осмотреть единицу.</Alert><Button variant="contained" disabled={!quarantine} onClick={() => setInspection(true)}>Открыть осмотр</Button>{disposition ? <Alert severity={disposition === 'В продажу' ? 'success' : 'info'} sx={{ mt: 1 }}>Зафиксировано: {disposition}. До проведённой приёмки остаток не меняется.</Alert> : null}</Paper><Dialog open={inspection} onClose={() => setInspection(false)}><DialogTitle>Осмотр возврата</DialogTitle><DialogContent><Stack spacing={1} sx={{ pt: 1 }}><FormControlLabel control={<Checkbox />} label="Упаковка цела" /><FormControlLabel control={<Checkbox />} label="Состояние товара подтверждено" /><FormControlLabel control={<Checkbox />} label="Маркировка совпала" /><Button variant="outlined">Добавить фото (placeholder)</Button><TextField select label="Решение" value={disposition} onChange={(event) => setDisposition(event.target.value)}><MenuItem value="В продажу">В продажу после проведённой приёмки</MenuItem><MenuItem value="Карантин">Оставить в карантине</MenuItem><MenuItem value="Брак">Брак</MenuItem><MenuItem value="Вернуть селлеру">Вернуть селлеру</MenuItem></TextField></Stack></DialogContent><DialogActions><Button onClick={() => setInspection(false)}>Отмена</Button><Button variant="contained" disabled={!disposition} onClick={() => setInspection(false)}>Зафиксировать осмотр</Button></DialogActions></Dialog></Stack></Shell> }

export function OzonCatalogPrototype() { const [tab, setTab] = useState(0); const [linkOpen, setLinkOpen] = useState(false); const [linked, setLinked] = useState(false); const [bindingSaved, setBindingSaved] = useState(false); return <Shell section="catalog"><Stack spacing={2}><Tabs value={tab} onChange={(_, value) => setTab(value)}><Tab label="Товары" /><Tab label="Склады и доставка" /></Tabs>{tab === 0 ? <><QueueTable testId="ozon-catalog-mappings" columns={['Ozon товар / offer / SKU', 'Штрихкод', 'Ozon status / requirements', 'WMS товар', 'Связь', 'Действие']}><TableRow><TableCell>Платье Margo<br />OFFER-MARGO / 2201</TableCell><TableCell>4601234567890</TableCell><TableCell>active · KIZ, IMEI</TableCell><TableCell>{linked ? 'Платье Margo · SKU-204' : '—'}</TableCell><TableCell><StatusChip label={linked ? 'Подтверждена' : 'Не сопоставлен'} tone={linked ? 'ok' : 'stop'} /></TableCell><TableCell><Button onClick={() => setLinkOpen(true)}>{linked ? 'Изменить связь' : 'Связать'}</Button></TableCell></TableRow><TableRow><TableCell>Сумка Luna<br />OFFER-LUNA / 2202</TableCell><TableCell>4601234567906</TableCell><TableCell>active · нет маркировки</TableCell><TableCell>Сумка Luna · SKU-231</TableCell><TableCell><StatusChip label="Точный seller SKU" tone="ok" /></TableCell><TableCell>—</TableCell></TableRow></QueueTable><Alert severity="info">Все external IDs и mappings scoped кабинетом Ozon Loviana. WB badge у Loviana показан только в selector и не меняет WB экран.</Alert></> : <Paper variant="outlined" sx={{ p: 2 }} data-testid="ozon-warehouse-binding"><Typography variant="h6">Связь складов и доставки</Typography><Stack spacing={1.5} sx={{ mt: 2 }}><TextField select label="Физический WMS склад" defaultValue="main"><MenuItem value="main">Основной склад</MenuItem></TextField><TextField select label="Схема" defaultValue="fbs"><MenuItem value="fbs">FBS</MenuItem><MenuItem value="fbo">FBO</MenuItem></TextField><TextField select label="Склад селлера" defaultValue="seller"><MenuItem value="seller">Loviana warehouse</MenuItem></TextField><TextField select label="Destination / cluster" defaultValue="cluster"><MenuItem value="cluster">Москва · Хоругвино</MenuItem></TextField><TextField select label="Delivery method" defaultValue="one"><MenuItem value="one">По одному</MenuItem><MenuItem value="carriage">Carriage</MenuItem></TextField><TextField select label="Return point" defaultValue="point"><MenuItem value="point">ПВЗ Ozon · Москва</MenuItem></TextField><Alert severity="info">Итог: Основной WMS → Loviana warehouse → Москва / Хоругвино, FBS по одному; возвраты в ПВЗ Ozon Москва.</Alert><Button variant="contained" onClick={() => setBindingSaved(true)}>Сохранить связь</Button>{bindingSaved ? <Alert severity="success">Полная FBS binding сохранена в local fixture.</Alert> : null}</Stack></Paper>}</Stack><Dialog open={linkOpen} onClose={() => setLinkOpen(false)}><DialogTitle>Подтвердить mapping</DialogTitle><DialogContent><Typography>Кандидат «Платье Margo · SKU-204» выбран по точному уникальному barcode 4601234567890. Связь действует только для Ozon Loviana.</Typography></DialogContent><DialogActions><Button onClick={() => setLinkOpen(false)}>Отмена</Button><Button variant="contained" onClick={() => { setLinked(true); setLinkOpen(false) }}>Подтвердить</Button></DialogActions></Dialog></Shell> }

export function OzonConnectionPrototype() { const [dialog, setDialog] = useState(false); const [clientId, setClientId] = useState('1234••••'); const [apiKey, setApiKey] = useState(''); const canCheck = clientId.length > 4 && apiKey.length > 0; return <Shell section="connection"><Stack spacing={2}><Alert severity="info">Остатки Ozon в этой версии только читаются; публикации из WMS нет.</Alert><Stack direction={{ xs: 'column', lg: 'row' }} spacing={2}><Paper variant="outlined" sx={{ p: 2, flex: 1 }} data-testid="ozon-account-health"><Typography variant="h6">Loviana · Ozon Loviana</Typography><Typography variant="body2">Client-Id: 1234•••• · Api-Key: присутствует · direct API</Typography><Typography variant="body2">Identity: Loviana Ozon Store · roles: FBS, FBO · expiry: 31.12.2026</Typography><Typography variant="body2">Последний discovery: 10:40 · sync: 10:42</Typography><StatusChip label="active_read_only" tone="ok" /></Paper><Paper variant="outlined" sx={{ p: 2, flex: 1 }}><Typography variant="h6">Fashion · Ozon Fashion</Typography><Typography variant="body2">Client-Id: отсутствует · Api-Key: присутствует · direct API</Typography><StatusChip label="pending_credentials" tone="warn" /><Button sx={{ display: 'block', mt: 1 }} onClick={() => setDialog(true)}>Проверить подключение</Button></Paper></Stack><Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">Возможности кабинета</Typography><QueueTable testId="ozon-capability-matrix" columns={['Группа', 'Возможность', 'Состояние']}><TableRow><TableCell>Чтение</TableCell><TableCell>Товары, postings, nodes, returns</TableCell><TableCell><StatusChip label="Обнаружено" tone="ok" /></TableCell></TableRow><TableRow><TableCell>FBS операции</TableCell><TableCell>Package label, handover readback</TableCell><TableCell><StatusChip label="Частично" tone="warn" /></TableCell></TableRow><TableRow><TableCell>FBO операции</TableCell><TableCell>Draft, supply, cargo, labels</TableCell><TableCell><StatusChip label="Обнаружено" tone="ok" /></TableCell></TableRow><TableRow><TableCell>Документы</TableCell><TableCell>Label assets, acts</TableCell><TableCell><StatusChip label="Read-only fixture" tone="neutral" /></TableCell></TableRow></QueueTable><Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Строки stock publishing здесь намеренно нет: capability, control, route и скрытое действие не существуют в прототипе.</Typography></Paper><Dialog open={dialog} onClose={() => setDialog(false)}><DialogTitle>Проверить подключение Fashion</DialogTitle><DialogContent><Alert severity="warning" sx={{ mb: 2 }}>В prototype нет сети и не используются credentials.</Alert><Stack spacing={1}><TextField label="Client-Id" value={clientId} onChange={(event) => setClientId(event.target.value)} /><TextField label="Api-Key" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></Stack></DialogContent><DialogActions><Button onClick={() => setDialog(false)}>Отмена</Button><Button variant="contained" disabled={!canCheck} onClick={() => setDialog(false)}>Проверить (fixture)</Button></DialogActions></Dialog></Stack></Shell> }

export function OzonModulePrototypeRoute() {
  const path = window.location.pathname
  if (path.includes('/fbs/')) return <FbsWorkspace />
  if (path.endsWith('/fbs') || path.endsWith('/ozon')) return <OzonFbsPrototype />
  if (path.includes('/fbo/')) return <FboWorkspace />
  if (path.endsWith('/fbo')) return <OzonFboPrototype />
  if (path.includes('/returns/')) return <ReturnWorkspace />
  if (path.endsWith('/returns')) return <OzonReturnsPrototype />
  if (path.endsWith('/catalog')) return <OzonCatalogPrototype />
  return <OzonConnectionPrototype />
}
