// Development-only fixture. Not a production build entry; no real auth, API or Trello calls.
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { Alert, Box, Button, Stack, Table, TableBody, TableCell, TableHead, TableRow, ThemeProvider, Typography } from '@mui/material'
import { muiTheme } from '../src/mui/theme'
import { AuthedAppLayout } from '../src/layouts/AuthedAppLayout'
import { SellerLayout } from '../src/apps/seller/SellerLayout'
import { SelectInput } from '../src/ui-kit'
import { emptySellerPermissions } from '../src/utils/sellerPermissions'
import type { RequestPayload, RequestRecord, RequestStatus } from '../src/components/developer-requests/draft'
import '../src/index.css'

let identity = { id: 'fixture-author-a', tenant_id: 'fixture-tenant-a', seller_id: 'fixture-shop-a' }
let behavior = 'ok'
const key = 'wms624.fixture.requests'
type Stored = { owner: string; payload: RequestPayload; record: RequestRecord }
const rows = (): Stored[] => JSON.parse(localStorage.getItem(key) || '[]')
const owner = () => `${identity.tenant_id}/${identity.id}`
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
window.fetch = async (input, init) => {
  const url = String(input)
  if (!url.includes('/developer-requests')) return json({ items: [], unread_count: 0 })
  const records = rows()
  if (init?.method === 'POST') {
    if (behavior === '500') return json({}, 500)
    // Inject a known pre-save rejection; this fixture does not duplicate the server's length calculation.
    if (behavior === '422') return json({ detail: {
      code: 'developer_request_description_too_long',
      message: 'Обращение слишком длинное для передачи разработчикам. Сократите текст и отправьте ещё раз.',
      max_length: 16384,
      actual_length: 18100,
    } }, 422)
    const payload: RequestPayload = JSON.parse(String(init.body))
    const existing = records.find((item) => item.owner === owner() && item.payload.idempotency_key === payload.idempotency_key)
    if (existing) return JSON.stringify(existing.payload) === JSON.stringify(payload) ? json(existing.record) : json({}, 409)
    const now = new Date().toISOString()
    const record: RequestRecord = { id: crypto.randomUUID(), type: payload.type, title: (payload.description || payload.screen || '').slice(0, 160), description: payload.description || null, screen: payload.screen || null, problem: payload.problem || null, proposal: payload.proposal || null, status: 'review', created_at: now, updated_at: now }
    records.push({ owner: owner(), payload, record }); localStorage.setItem(key, JSON.stringify(records))
    if (behavior === 'lost') throw new TypeError('Fixture: response lost after save')
    return json(record)
  }
  const id = url.split('/developer-requests/')[1]
  const own = records.filter((item) => item.owner === owner())
  if (id) return own.some((item) => item.record.id === id) ? json(own.find((item) => item.record.id === id)!.record) : json({}, 404)
  return json(own.map((item) => item.record).sort((a, b) => b.created_at.localeCompare(a.created_at)))
}

function Preview() {
  const [portal, setPortal] = useState('ff')
  const [author, setAuthor] = useState('a')
  const [tenant, setTenant] = useState('a')
  const [shop, setShop] = useState('a')
  const [mode, setMode] = useState('ok')
  const [status, setStatus] = useState('review')
  const [actionBar, setActionBar] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  identity = { id: `fixture-author-${author}`, tenant_id: `fixture-tenant-${tenant}`, seller_id: `fixture-shop-${shop}` }
  behavior = mode
  const props = { onLogout: () => undefined, userLabel: 'Тестовый пользователь', developerRequests: { me: identity, token: 'local-fixture-not-a-real-token' } }
  const content = <Stack spacing={2}>
    <Alert severity="info">Локальная проверка WMS-624. Данные тестовые, внешние запросы отключены. Таблица ниже — образец рабочего контекста.</Alert>
    <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 2, '& > div': { minWidth: 170, flex: '1 1 170px' } }}>
      <SelectInput label="Портал" value={portal} onChange={setPortal} options={[{ value: 'ff', label: 'Фулфилмент' }, { value: 'seller', label: 'Селлер' }]} />
      <SelectInput label="Пользователь" value={author} onChange={setAuthor} options={['a','b'].map((value) => ({ value, label: `Автор ${value}` }))} />
      <SelectInput label="Организация" value={tenant} onChange={setTenant} options={['a','b'].map((value) => ({ value, label: `Организация ${value}` }))} />
      <SelectInput label="Магазин" value={shop} onChange={setShop} options={['a','b'].map((value) => ({ value, label: `Магазин ${value}` }))} />
      <SelectInput label="Ответ API" value={mode} onChange={setMode} options={[{ value: 'ok', label: 'Успех' }, { value: '500', label: '500 до сохранения' }, { value: '422', label: '422: слишком длинное обращение' }, { value: 'lost', label: 'Потеря ответа после сохранения' }]} />
      <SelectInput label="Стадия всех тестовых заявок" value={status} onChange={(value) => { setStatus(value); localStorage.setItem(key, JSON.stringify(rows().map((item) => ({ ...item, record: { ...item.record, status: value as RequestStatus } })))) }} options={[{value:'review', label:'На рассмотрении'}, {value:'queued',label:'В очереди'},{value:'in_progress',label:'В работе'},{value:'completed',label:'Готово'}]} />
    </Stack>
    <Stack direction="row" spacing={1}><Button onClick={() => navigate('/app/ff/fbs?private=fixture#fragment')}>FBS</Button><Button onClick={() => navigate('/app/ff/billing')}>Расчёты</Button><Button onClick={() => setActionBar(!actionBar)}>Панель действий</Button></Stack>
    <Typography variant="h5">{location.pathname.includes('fbs') ? 'FBS' : 'Расчёты'}</Typography>
    <Typography data-testid="fixture-path">{location.pathname + location.search + location.hash}</Typography>
    <Box sx={{ overflowX: 'auto' }}><Table><TableHead><TableRow>{['Товар','Селлер','Маршрут сдачи','Отгрузить до','Статус'].map((value) => <TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead><TableBody><TableRow><TableCell>Тестовый товар с длинным названием для проверки рабочего экрана</TableCell><TableCell>Тестовый селлер</TableCell><TableCell>WB · Склад</TableCell><TableCell>02.10.2026</TableCell><TableCell>В сборке</TableCell></TableRow></TableBody></Table></Box>
    {actionBar && <Box data-testid="fixture-action-bar" sx={{ position:'fixed', bottom:18, right:20, bgcolor:'background.paper', p:2, zIndex:1200, boxShadow:3 }}><Button variant="contained">Упаковать</Button></Box>}
  </Stack>
  return portal === 'ff' ? <AuthedAppLayout {...props} portal="ff" meRole="fulfillment_admin">{content}</AuthedAppLayout> : <SellerLayout {...props} permissions={{...emptySellerPermissions(), documents:true, products:true, settings:true}}>{content}</SellerLayout>
}
createRoot(document.getElementById('root')!).render(<ThemeProvider theme={muiTheme}><MemoryRouter initialEntries={['/app/ff/fbs?private=fixture#fragment']}><Preview /></MemoryRouter></ThemeProvider>)
