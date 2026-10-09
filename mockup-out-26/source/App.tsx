import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, CssBaseline, Dialog, DialogActions, DialogContent, DialogTitle, Divider, IconButton, Menu, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, Tab, TextField, ThemeProvider, Tooltip, Typography } from '@mui/material'
import DownloadOutlined from '@mui/icons-material/DownloadOutlined'
import SendOutlined from '@mui/icons-material/SendOutlined'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined'
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined'
import MoreVertOutlined from '@mui/icons-material/MoreVertOutlined'
import DeleteOutlineOutlined from '@mui/icons-material/DeleteOutlineOutlined'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import JsBarcode from 'jsbarcode'
import { muiTheme } from '../../frontend/src/mui/theme'
import { BoxLabelPrintDialog } from '../../frontend/src/components/BoxLabelPrintDialog'
import { FfProductLineCells, FfProductTableHeadCells } from '../../frontend/src/components/FfProductLineCells'
import { MarketplaceChip } from '../../frontend/src/ui-kit/MarketplaceChip'
import type { ProductLineDisplayMeta } from '../../frontend/src/types/wbProductCatalog'
import type { LabelSize } from '../../frontend/src/utils/labelSize'
import { download, packingXlsx, type Snapshot } from './export'

type Product = { id: number; plan: number; picked: number; meta: ProductLineDisplayMeta }
type ShippingBox = { id: string; internal_barcode: string; box_preset: string; lines: { product: number; quantity: number }[] }
const shipment = 'ОТГ-000126', seller = 'ООО «Демо Текстиль»', supply = '56000126'
const products: Product[] = [
  { id: 1, plan: 40, picked: 40, meta: { sku_code: 'DEMO-TEE-01', product_name: 'Футболка базовая из хлопка, молочная', wb_vendor_code: 'DEMO-TEE-MILK', wb_nm_id: 900000101, wb_primary_barcode: '2900000000012', wb_barcodes: ['2900000000012'], wb_primary_image_url: './assets/tshirt.svg', wb_size: 'M', wb_color: 'Молочный' } },
  { id: 2, plan: 30, picked: 30, meta: { sku_code: 'DEMO-TEE-02', product_name: 'Футболка свободного кроя из хлопка с принтом «Линии города», графитовая', wb_vendor_code: 'DEMO-TEE-GRAPHITE', wb_nm_id: 900000102, wb_primary_barcode: '2900000000029', wb_barcodes: ['2900000000029'], wb_primary_image_url: './assets/graphite.svg', wb_size: 'L', wb_color: 'Графитовый' } },
  { id: 3, plan: 20, picked: 20, meta: { sku_code: 'DEMO-SOCK-03', product_name: 'Носки хлопковые, набор 3 пары, светло-серые', wb_vendor_code: 'DEMO-SOCK-3-GREY', wb_nm_id: 900000103, wb_primary_barcode: '2900000000036', wb_barcodes: ['2900000000036'], wb_primary_image_url: './assets/socks.svg', wb_size: '39–42', wb_color: 'Серый' } },
]
const initialBoxes = (): ShippingBox[] => [
  { id: 'demo-box-1', internal_barcode: 'WHB-7K2M8N4P6R9T3V', box_preset: '60_40_40', lines: [{ product: 1, quantity: 20 }, { product: 2, quantity: 10 }] },
  { id: 'demo-box-2', internal_barcode: 'WHB-8N3P5R7T9V2X4Z', box_preset: '60_40_40', lines: [{ product: 1, quantity: 20 }, { product: 2, quantity: 20 }] },
  { id: 'demo-box-3', internal_barcode: 'WHB-9P4R6T8V2X3Z5K', box_preset: '30_20_30', lines: [{ product: 3, quantity: 20 }] },
]
const descriptions = ['Два действия рядом со списком коробов: выгрузка файла и передача состава в WB.', 'Передача состава в WB и выгрузка файла в меню шапки отгрузки.']
const sizeLabel = (preset: string) => preset === '60_40_40' ? '60 × 40 × 40 см' : '30 × 20 × 30 см'
const rowTotal = (box: ShippingBox) => box.lines.reduce((n, row) => n + row.quantity, 0)

function Barcode({ value, width = 300 }: { value: string; width?: number }) {
  return <Box component="svg" ref={(node: SVGSVGElement | null) => { if (node) JsBarcode(node, value, { format: 'CODE128', width: 1.3, height: 52, fontSize: 12, margin: 12 }) }} role="img" aria-label={`Штрихкод ${value}`} sx={{ width, maxWidth: '100%', height: 'auto', display: 'block' }} />
}
function Gallery() {
  return <Box sx={{ minHeight: '100vh', p: { xs: 2, md: 6 }, maxWidth: 1150, mx: 'auto' }}>
    <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 5 }}><Box component="img" src="./assets/logo.png" alt="" sx={{ width: 48, height: 48, borderRadius: '50%' }} /><Typography variant="h5">Короб ВМС</Typography><Typography color="text.secondary">Макеты</Typography></Stack>
    <Typography variant="overline" color="primary">WB FBO · WMS-679</Typography>
    <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: '-0.025em', mt: 1 }}>Короба и передача состава в WB</Typography>
    <Typography color="text.secondary" sx={{ mt: 2, mb: 4, maxWidth: 740 }}>Два расположения действий в существующей отгрузке. Во всех вариантах код короба, этикетка, файл и передаваемый состав используют одни данные.</Typography>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3 }}>
      {descriptions.map((text, i) => <Paper key={i} variant="outlined" sx={{ overflow: 'hidden' }}>
        <Box sx={{ p: 3, bgcolor: 'rgba(91,33,182,.05)', borderBottom: 1, borderColor: 'divider', height: 190 }}>
          <Typography variant="subtitle2">Отгрузка {shipment}</Typography>
          <Box sx={{ display: 'flex', gap: 2, mt: 2, mb: 1.5, fontSize: 12 }}><span>Товары</span><span>Подбор</span><Box component="span" sx={{ color: 'primary.main', borderBottom: '2px solid' }}>Упаковка</Box></Box>
          <Box sx={{ p: 1.25, border: '1px solid rgba(91,33,182,.2)', borderRadius: 1, bgcolor: 'white' }}>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>Короба · 3 короба · 90 единиц</Typography>
            <Divider sx={{ my: 1 }} /><Typography variant="caption" color="text.secondary">Короб 1 · WHB-7K2M8N4P6R9T3V</Typography>
          </Box>
        </Box>
        <Box sx={{ p: 3 }}><Typography variant="overline" color="text.secondary">Вариант {i + 1}</Typography><Typography variant="h6" sx={{ mt: .5 }}>{i === 0 ? 'Действия в разделе «Короба»' : 'Действия в шапке документа'}</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 3, minHeight: 42 }}>{text}</Typography><Button component="a" href={`./variant-${i + 1}.html`} variant="contained" endIcon={<ArrowBackOutlined sx={{ transform: 'rotate(180deg)' }} />}>Открыть вариант {i + 1}</Button></Box>
      </Paper>)}
    </Box>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 4 }}>Вымышленные данные. Передача в WB и её ответы моделируются локально. Формат демонстрационной выгрузки и приём кодов WB не проверены.</Typography>
  </Box>
}

function Workspace({ variant }: { variant: number }) {
  const [tab, setTab] = useState('packaging'), [boxes, setBoxes] = useState(initialBoxes)
  const [scenario, setScenario] = useState('normal'), [expanded, setExpanded] = useState(true)
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'warning'; text: string } | null>(null)
  const [transmitting, setTransmitting] = useState(false), [unknown, setUnknown] = useState(false)
  const [fillBox, setFillBox] = useState<string | null>(null), [qty, setQty] = useState<Record<number, string>>({})
  const [scan, setScan] = useState(''), [formError, setFormError] = useState<string | null>(null)
  const [printTarget, setPrintTarget] = useState<ShippingBox[] | null>(null)
  const [labelPreview, setLabelPreview] = useState<{ boxes: ShippingBox[]; size: LabelSize } | null>(null)
  const [menu, setMenu] = useState<HTMLElement | null>(null), [batchCount, setBatchCount] = useState('1'), [preset, setPreset] = useState('60_40_40')
  const [lastSnapshot, setLastSnapshot] = useState<Snapshot | null>(null)
  const [sentSnapshot, setSentSnapshot] = useState<Snapshot | null>(null)
  const packed = boxes.reduce((n, b) => n + rowTotal(b), 0)
  const boxed = (id: number) => boxes.reduce((n, b) => n + b.lines.filter(r => r.product === id).reduce((n, r) => n + r.quantity, 0), 0)
  const snapshot = (): Snapshot => ({ shipment, seller, supply, rows: boxes.flatMap(box => box.lines.map(line => ({ boxBarcode: box.internal_barcode, productBarcode: products.find(p => p.id === line.product)!.meta.wb_primary_barcode!, quantity: line.quantity }))) })
  function changeScenario(value: string) {
    setScenario(value); setNotice(null); setUnknown(false); setLastSnapshot(null); setSentSnapshot(null); setQty({}); setFormError(null)
    const next = initialBoxes()
    if (value === 'partial') next[2].lines[0].quantity = 15
    setBoxes(next)
  }
  function exportFile() {
    const data = snapshot(); setLastSnapshot(data)
    download(packingXlsx(data), `MOCKUP-WB-FBO-${shipment}-supply-${supply}.xlsx`)
    setNotice({ type: 'success', text: `Демонстрационный файл: ${data.rows.length} строк, ${packed} единиц. Селлер: ${seller}.` }); setMenu(null)
  }
  function transmit() {
    setMenu(null); setTransmitting(true); setNotice(null)
    const data = snapshot(); setLastSnapshot(data); setSentSnapshot(data)
    setTimeout(() => {
      setTransmitting(false)
      if (scenario === 'error') setNotice({ type: 'error', text: 'Макет: WB отклонил состав. Демонстрационная ошибка: поставка не найдена у выбранного селлера.' })
      else if (scenario === 'unknown') { setUnknown(true); setNotice({ type: 'warning', text: 'Макет: ответ WB не получен. Результат передачи неизвестен.' }) }
      else setNotice({ type: 'success', text: `Макет: состав передан в поставку WB № ${data.supply}. ${data.rows.length} строк, ${data.rows.reduce((n, r) => n + r.quantity, 0)} единиц. Селлер: ${data.seller}.` })
    }, 500)
  }
  function checkResult() {
    setTransmitting(true)
    const matches = JSON.stringify(sentSnapshot) === JSON.stringify(snapshot())
    setTimeout(() => { setTransmitting(false); setUnknown(false); setNotice(matches
      ? { type: 'success', text: `Макет: состав найден в поставке WB № ${supply}. Коды коробов, товары и количества совпадают. Повторная передача не выполнялась.` }
      : { type: 'warning', text: `Макет: ранее переданный состав найден в поставке WB № ${supply}. Текущая раскладка в WMS изменена и отличается. Повторная передача не выполнялась.` }) }, 500)
  }
  function removeLine(boxId: string, productId: number) {
    setBoxes(prev => prev.map(b => b.id === boxId ? { ...b, lines: b.lines.filter(r => r.product !== productId) } : b)); setNotice(null)
  }
  function addLine(productId: number, count: number) {
    const remaining = products.find(p => p.id === productId)!.picked - boxed(productId)
    if (!Number.isInteger(count) || count < 1 || count > remaining) { setFormError(`Доступно к раскладке: ${remaining} шт.`); return }
    setBoxes(prev => prev.map(b => b.id !== fillBox ? b : { ...b, lines: b.lines.some(r => r.product === productId) ? b.lines.map(r => r.product === productId ? { ...r, quantity: r.quantity + count } : r) : [...b.lines, { product: productId, quantity: count }] }))
    setFormError(null); setNotice(null)
  }
  function scanProduct() {
    const product = products.find(p => p.meta.wb_barcodes.includes(scan.trim()))
    if (!product) setFormError('Штрихкод не найден в товарах этой отгрузки.')
    else { addLine(product.id, 1); setScan('') }
  }
  function createBoxes() {
    const count = Number(batchCount)
    if (!Number.isInteger(count) || count < 1) { setNotice({ type: 'error', text: 'Введите целое положительное количество коробов.' }); return }
    const alphabet = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
    const existing = new Set(boxes.map(b => b.internal_barcode))
    const created: ShippingBox[] = Array.from({ length: count }, () => {
      let code: string
      do { code = 'WHB-' + Array.from(crypto.getRandomValues(new Uint8Array(14)), n => alphabet[n % 32]).join('') } while (existing.has(code))
      existing.add(code)
      return { id: crypto.randomUUID(), internal_barcode: code, box_preset: preset, lines: [] }
    })
    setBoxes(prev => [...prev, ...created]); setNotice(null)
  }
  const transmissionActions = <>
    <Button variant="outlined" startIcon={<DownloadOutlined />} onClick={exportFile} data-testid="export">Выгрузить для WB</Button>
    <Button variant="contained" startIcon={<SendOutlined />} onClick={unknown ? checkResult : transmit} disabled={transmitting} data-testid="transmit">{transmitting ? 'Проверка…' : unknown ? 'Проверить результат в WB' : 'Передать состав в WB'}</Button>
  </>
  function productTable(lines: { product: number; quantity: number }[], boxId?: string) {
    return <TableContainer><Table size="small" sx={{ minWidth: 1080, tableLayout: 'fixed' }}><TableHead><TableRow><FfProductTableHeadCells showPrint={false} /><TableCell align="right" sx={{ width: 98 }}>{boxId ? 'В коробе' : 'По накладной'}</TableCell>{boxId && <TableCell sx={{ width: 42 }} />}</TableRow></TableHead><TableBody>{lines.map(line => <TableRow key={line.product}><FfProductLineCells showPrint={false} meta={products.find(p => p.id === line.product)!.meta} /><TableCell align="right">{line.quantity}</TableCell>{boxId && <TableCell sx={{ p: .5 }}><Tooltip title="Убрать из короба"><IconButton size="small" aria-label="Убрать из короба" onClick={() => removeLine(boxId, line.product)}><DeleteOutlineOutlined fontSize="small" /></IconButton></Tooltip></TableCell>}</TableRow>)}</TableBody></Table></TableContainer>
  }
  return <>
    <Box className="mock-toolbar" sx={{ bgcolor: 'text.primary', color: 'white', px: 2.5, py: 1, display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
      <Button component="a" href="./index.html" size="small" sx={{ color: 'white' }} startIcon={<ArrowBackOutlined />}>Все варианты</Button>
      <Typography variant="body2" sx={{ fontWeight: 700 }}>Вариант {variant}</Typography>
      <Button component="a" href={`./variant-${variant === 1 ? 2 : 1}.html`} size="small" sx={{ color: '#c4b5fd' }}>Открыть вариант {variant === 1 ? 2 : 1}</Button>
      <TextField select size="small" value={scenario} onChange={e => changeScenario(e.target.value)} label="Сценарий макета" disabled={transmitting} sx={{ minWidth: 235, bgcolor: 'white', borderRadius: 1, ml: { md: 'auto' } }} data-testid="scenario">
        <MenuItem value="normal">Состав разложен</MenuItem><MenuItem value="partial">Осталось разложить 5 шт.</MenuItem><MenuItem value="error">WB отклонил состав</MenuItem><MenuItem value="unknown">Ответ WB не получен</MenuItem>
      </TextField>
      <Typography variant="caption" sx={{ opacity: .75 }}>Макет · вымышленные данные · WB не подключён</Typography>
    </Box>
    <Box className="document" sx={{ bgcolor: 'background.paper', minHeight: 'calc(100vh - 62px)' }}>
      <Box sx={{ px: 3, py: 1.5, borderBottom: 1, borderColor: 'divider', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}><Typography variant="h6">Отгрузка на МП</Typography><Stack direction="row" gap={1} flexWrap="wrap">{variant === 2 && <><Button variant="contained" startIcon={<SendOutlined />} onClick={unknown ? checkResult : transmit} disabled={transmitting} data-testid="transmit">{transmitting ? 'Проверка…' : unknown ? 'Проверить результат в WB' : 'Передать состав в WB'}</Button><Button variant="outlined" endIcon={<ExpandMoreOutlined />} onClick={e => setMenu(e.currentTarget)} data-testid="doc-actions">Действия</Button></>}<IconButton component="a" href="./index.html" aria-label="Закрыть отгрузку"><CloseOutlined /></IconButton></Stack></Box>
      <Box sx={{ p: { xs: 1.5, sm: 3 }, pb: 10 }}>
        <Stack direction="row" alignItems="center" gap={1.5} sx={{ mb: .75 }}><Typography variant="h5">Отгрузка {shipment}</Typography><MarketplaceChip marketplace="wb" /><Typography variant="body2" color="text.secondary">FBO</Typography></Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Склад ФФ: <strong>Демо-склад Север</strong> · Подтверждена</Typography>
        <Stack direction="row" gap={3} flexWrap="wrap" sx={{ mb: 2 }}><Typography variant="body2">Селлер: <strong>{seller}</strong></Typography><Typography variant="body2">Склад WB: <strong>Демо-склад WB</strong></Typography><Typography variant="body2">Поставка WB: <strong>№ {supply}</strong></Typography></Stack>
        <Paper variant="outlined" sx={{ mb: 2, p: 1.5, bgcolor: 'action.hover' }}><Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4,1fr)' }, gap: 1 }}>{[['План', 90], ['Подобрано', 90], ['Осталось подобрать', 0], ['Упаковано (из подобранного)', `${packed} / 90`]].map(([label, value]) => <Box key={label}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" sx={{ fontWeight: 700 }}>{value}</Typography></Box>)}</Box></Paper>
        <Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}><Tab label="Товары" value="plan" /><Tab label="Подбор" value="pick" /><Tab label="Упаковка" value="packaging" /></Tabs>
        {notice && <Alert severity={notice.type} onClose={() => setNotice(null)} sx={{ mb: 2 }} data-testid="notice">{notice.text}</Alert>}
        {tab === 'plan' && <><Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}><Typography variant="subtitle1">Товары по накладной</Typography><Button variant="outlined" startIcon={<PrintOutlined />} onClick={() => { setNotice({ type: 'success', text: 'Макет: состав накладной показан ниже. Печать накладной в этом варианте не моделируется.' }) }}>Накладная</Button></Stack>{productTable(products.map(p => ({ product: p.id, quantity: p.plan })))}</>}
        {tab === 'pick' && <><Typography variant="subtitle1" sx={{ mb: 2 }}>Подбор по накладной</Typography><TableContainer><Table size="small" sx={{ minWidth: 1100 }}><TableHead><TableRow><FfProductTableHeadCells showPrint={false} /><TableCell align="right">План</TableCell><TableCell align="right">Подобрано</TableCell></TableRow></TableHead><TableBody>{products.map(p => <TableRow key={p.id}><FfProductLineCells meta={p.meta} showPrint={false} /><TableCell align="right">{p.plan}</TableCell><TableCell align="right">{p.picked}</TableCell></TableRow>)}</TableBody></Table></TableContainer></>}
        {tab === 'packaging' && <Accordion disableGutters variant="outlined" expanded={expanded} onChange={(_, value) => setExpanded(value)}>
          <AccordionSummary expandIcon={<ExpandMoreOutlined />} sx={{ bgcolor: 'rgba(91,33,182,.08)' }}><Stack direction="row" gap={1.5} alignItems="center"><Typography variant="subtitle2">Короба</Typography><Chip size="small" label={`Коробов: ${boxes.length}`} /><Chip size="small" label={`Единиц: ${packed}`} /></Stack></AccordionSummary>
          <AccordionDetails>
            <Stack direction={{ xs: 'column', md: 'row' }} gap={1.5} alignItems={{ md: 'center' }} justifyContent="space-between" sx={{ mb: 2, mt: .5 }}><Typography variant="body2" color="text.secondary">Поставка WB № {supply} · {seller}</Typography><Stack direction="row" gap={1} flexWrap="wrap">{variant === 1 && transmissionActions}<Button variant="outlined" startIcon={<PrintOutlined />} onClick={() => setPrintTarget(boxes)}>Печать ШК всех коробов</Button></Stack></Stack>
            <Stack spacing={1.5}>{boxes.map((box, i) => <Paper variant="outlined" key={box.id} sx={{ borderRadius: 1, overflow: 'hidden' }} data-testid={`box-${i + 1}`}>
              <Box sx={{ bgcolor: 'action.hover', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1, flexWrap: 'wrap', px: 1.25, py: 1 }}><Box><Typography variant="subtitle2" sx={{ lineHeight: 1.25 }}>Короб {i + 1}</Typography><Typography variant="body2" color="text.secondary">{sizeLabel(box.box_preset)}{box.lines.length === 0 ? ' · готов к наполнению' : ''}</Typography><Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'ui-monospace, monospace' }} data-testid={`box-code-${i + 1}`}>{box.internal_barcode}</Typography></Box><Stack direction="row" gap={.5}><Button size="small" variant="outlined" onClick={() => { setFillBox(box.id); setFormError(null); setScan('') }} data-testid={`fill-${i + 1}`}>Наполнить</Button><Tooltip title="Печать ШК короба"><IconButton size="small" aria-label={`Печать ШК короба ${i + 1}`} onClick={() => setPrintTarget([box])}><Typography variant="caption" sx={{ fontWeight: 700 }}>ШК</Typography></IconButton></Tooltip></Stack></Box>
              {box.lines.length > 0 && productTable(box.lines, box.id)}
            </Paper>)}</Stack>
            <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" sx={{ mt: 2 }}><TextField label="Кол-во коробов" type="number" value={batchCount} onChange={e => setBatchCount(e.target.value)} sx={{ width: 140 }} slotProps={{ htmlInput: { min: 1 } }} /><TextField select label="Пресет" value={preset} onChange={e => setPreset(e.target.value)} sx={{ width: 170 }}><MenuItem value="60_40_40">60×40×40</MenuItem><MenuItem value="30_20_30">30×20×30</MenuItem></TextField><Button variant="outlined" onClick={createBoxes} data-testid="create-box">Создать короба</Button></Stack>
          </AccordionDetails>
        </Accordion>}
      </Box>
      <Box sx={{ position: 'fixed', bottom: 0, left: 0, right: 0, bgcolor: 'background.paper', borderTop: 1, borderColor: 'divider', p: 1.5, display: 'flex', justifyContent: 'flex-end' }}><Button component="a" href="./index.html" variant="outlined">Закрыть</Button></Box>
    </Box>
    <Menu anchorEl={menu} open={Boolean(menu)} onClose={() => setMenu(null)}><MenuItem onClick={exportFile} data-testid="export"><DownloadOutlined fontSize="small" sx={{ mr: 1 }} />Выгрузить состав для WB</MenuItem><MenuItem onClick={() => { setMenu(null); setPrintTarget(boxes) }}><PrintOutlined fontSize="small" sx={{ mr: 1 }} />Печать ШК всех коробов</MenuItem></Menu>
    <Dialog open={Boolean(fillBox)} onClose={() => setFillBox(null)} maxWidth="lg" fullWidth><DialogTitle>Наполнить короб {boxes.findIndex(b => b.id === fillBox) + 1}<Typography variant="caption" component="div" color="text.secondary">{boxes.find(b => b.id === fillBox)?.internal_barcode}</Typography></DialogTitle><DialogContent><Stack direction="row" gap={1} sx={{ mt: 1, mb: 2 }}><TextField label="Штрихкод товара" value={scan} onChange={e => setScan(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') scanProduct() }} fullWidth /><Button variant="contained" onClick={scanProduct}>Скан</Button></Stack>{formError && <Alert severity="error" sx={{ mb: 2 }}>{formError}</Alert>}<TableContainer><Table size="small" sx={{ minWidth: 800 }}><TableHead><TableRow><TableCell>Артикул</TableCell><TableCell>Товар</TableCell><TableCell align="right">План</TableCell><TableCell align="right">В коробах</TableCell><TableCell align="right">Доступно</TableCell><TableCell>Кол-во</TableCell><TableCell /></TableRow></TableHead><TableBody>{products.map(p => <TableRow key={p.id}><TableCell>{p.meta.sku_code}</TableCell><TableCell>{p.meta.product_name}</TableCell><TableCell align="right">{p.plan}</TableCell><TableCell align="right">{boxed(p.id)}</TableCell><TableCell align="right">{p.picked - boxed(p.id)}</TableCell><TableCell><TextField type="number" value={qty[p.id] ?? '1'} onChange={e => setQty(prev => ({ ...prev, [p.id]: e.target.value }))} sx={{ width: 72 }} slotProps={{ htmlInput: { min: 1, 'aria-label': `Количество ${p.meta.sku_code}` } }} /></TableCell><TableCell><Button variant="outlined" size="small" disabled={boxed(p.id) >= p.picked} onClick={() => addLine(p.id, Number(qty[p.id] ?? '1'))}>Добавить</Button></TableCell></TableRow>)}</TableBody></Table></TableContainer></DialogContent><DialogActions><Button onClick={() => setFillBox(null)}>Закрыть</Button></DialogActions></Dialog>
    <BoxLabelPrintDialog open={Boolean(printTarget)} title="Печать штрихкода короба" description={printTarget?.length === 1 ? printTarget[0].internal_barcode : `Все короба отгрузки ${shipment}`} onClose={() => setPrintTarget(null)} onConfirm={size => { setLabelPreview({ boxes: printTarget!, size }); setPrintTarget(null) }} />
    <Dialog open={Boolean(labelPreview)} onClose={() => setLabelPreview(null)} maxWidth="sm" fullWidth className="label-dialog"><DialogTitle>Предпросмотр этикеток</DialogTitle><DialogContent><Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Макет · вымышленные коды · {labelPreview?.size.label}</Typography><Stack spacing={2} className="print-area">{labelPreview?.boxes.map(box => <Box key={box.id} className="print-label" sx={{ border: '1px solid #ddd', p: 2, textAlign: 'center', mx: 'auto' }}><Typography variant="caption">WB FBO · {shipment}</Typography><Barcode value={box.internal_barcode} /><Typography variant="caption">{seller}</Typography></Box>)}</Stack></DialogContent><DialogActions><Button onClick={() => setLabelPreview(null)}>Закрыть</Button><Button variant="contained" startIcon={<DownloadOutlined />} onClick={() => {
      const labels = labelPreview!.boxes.map(box => { const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); JsBarcode(svg, box.internal_barcode, { format: 'CODE128', width: 1.3, height: 60, fontSize: 12 }); return `<section><div>WB FBO · ${shipment}</div>${svg.outerHTML}<div>${seller}</div></section>` }).join('')
      const size = labelPreview!.size
      download(new Blob([`<!doctype html><html lang="ru"><meta charset="utf-8"><title>Макет этикеток коробов</title><style>@page{size:${size.widthMm}mm ${size.heightMm}mm;margin:0}body{margin:0;font:10px system-ui}section{width:${size.widthMm}mm;height:${size.heightMm}mm;display:flex;flex-direction:column;align-items:center;justify-content:center;break-after:page}svg{max-width:96%;height:auto}@media print{button,p{display:none}}</style><button onclick="window.print()">Печать</button><p>Макет: вымышленные коды. Физическая печать не подтверждена.</p>${labels}</html>`], { type: 'text/html' }), `MOCKUP-${shipment}-labels.html`)
    }}>Скачать этикетки</Button></DialogActions></Dialog>
    <Box className="mock-footer" sx={{ bgcolor: 'text.primary', color: '#cbd5e1', p: 2.5, pb: 10 }}><Typography variant="caption">Обвязка макета: исходный состав для обоих способов передачи</Typography><Box component="details" sx={{ mt: 1 }}><Box component="summary" sx={{ cursor: 'pointer', fontSize: 13 }}>Последняя выгрузка / передача</Box><Box component="pre" sx={{ overflow: 'auto', fontSize: 12 }} data-testid="last-snapshot">{lastSnapshot ? JSON.stringify(lastSnapshot, null, 2) : 'Нажмите «Выгрузить» или «Передать состав».'}</Box></Box></Box>
  </>
}
const variant = Number(document.body.dataset.variant || 0)
createRoot(document.getElementById('root')!).render(<ThemeProvider theme={muiTheme}><CssBaseline />{variant ? <Workspace variant={variant} /> : <Gallery />}</ThemeProvider>)
