import { useCallback, useEffect, useMemo, useState } from 'react'
import { Stack, Typography } from '@mui/material'
import {
  CheckCell,
  ChoiceFilter,
  DataTable,
  ErrorNotice,
  FilterBar,
  ModalFrame,
  PrintAction,
  QtyCell,
  SecondaryAction,
  TextCell,
  type Column,
} from '../../ui-kit'
import { getFbsPickingList, printFbsOrderTape, resolveFbsAssetUrl, type FbsPickingItem } from './fbsApi'

type Props = { token: string; authHeaders: (t: string) => Record<string, string>; supplyId: string | null; open: boolean; onClose: () => void }
type Mark = { collected: boolean; packed: boolean }
type Marks = Record<string, Mark>
type PickFilter = 'all' | 'not_collected' | 'not_packed'
type NumberedItem = FbsPickingItem & { numberFrom: number; numberTo: number }

export function buildNumberedItems(items: FbsPickingItem[]): NumberedItem[] {
  return items.map((item) => ({ ...item, numberFrom: item.number_start, numberTo: item.number_end }))
}

export function markKey(item: Pick<FbsPickingItem, 'article' | 'sku_code' | 'size' | 'product_name'>): string {
  return [item.article, item.sku_code ?? '', item.size ?? '', item.product_name].join('::')
}

function loadMarks(supplyId: string): Marks {
  try { return JSON.parse(localStorage.getItem(`fbs-picklist-${supplyId}`) ?? '{}') as Marks } catch { return {} }
}
function saveMarks(supplyId: string, marks: Marks): void { localStorage.setItem(`fbs-picklist-${supplyId}`, JSON.stringify(marks)) }

export function FfFbsPickList({ token, authHeaders, supplyId, open, onClose }: Props) {
  const [items, setItems] = useState<FbsPickingItem[]>([])
  const [marks, setMarks] = useState<Marks>({})
  const [loading, setLoading] = useState(false)
  const [printing, setPrinting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<PickFilter>('all')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    if (!supplyId) return
    setLoading(true); setError(null)
    try { setItems(await getFbsPickingList(token, authHeaders, supplyId)); setMarks(loadMarks(supplyId)) }
    catch (e) { setItems([]); setError(e instanceof Error ? e.message : 'Не удалось загрузить лист подбора. Попробуйте ещё раз') }
    finally { setLoading(false) }
  }, [token, authHeaders, supplyId])

  useEffect(() => { if (open && supplyId) void load() }, [open, supplyId, load])

  const numbered = useMemo(() => buildNumberedItems(items), [items])
  const setMark = useCallback((key: string, patch: Partial<Mark>) => {
    if (!supplyId) return
    setMarks((prev) => { const next = { ...prev, [key]: { ...(prev[key] ?? { collected: false, packed: false }), ...patch } }; saveMarks(supplyId, next); return next })
  }, [supplyId])
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return numbered.filter((item) => {
      const mark = marks[markKey(item)] ?? { collected: false, packed: false }
      if (filter === 'not_collected' && mark.collected) return false
      if (filter === 'not_packed' && mark.packed) return false
      return !needle || item.article.toLowerCase().includes(needle) || item.product_name.toLowerCase().includes(needle) || (item.size?.toLowerCase().includes(needle) ?? false)
    })
  }, [numbered, marks, filter, search])
  const collected = items.filter((i) => marks[markKey(i)]?.collected).length
  const packed = items.filter((i) => marks[markKey(i)]?.packed).length
  const canPrint = !loading && !error && items.length > 0 && !printing

  const printStickers = useCallback(async () => {
    if (!supplyId || !canPrint) return
    setPrinting(true); setError(null)
    try {
      const freshItems = await getFbsPickingList(token, authHeaders, supplyId)
      setItems(freshItems)
      const orderIds = freshItems.flatMap((item) => item.order_ids)
      if (orderIds.length === 0) { setError('В поставке нет заказов для печати'); return }
      const tape = await printFbsOrderTape(token, authHeaders, supplyId, {
        order_ids: orderIds,
        layout_json: null,
        allow_partial: false,
        include_order_qr: true,
        reprint: false,
      })
      if (tape.shortage > 0 || tape.missing > 0 || tape.failed > 0 || tape.order_errors.length > 0) {
        setError(['Стикеры ещё не готовы или получены не все', ...tape.order_errors.map((item) => `Заказ WB №${item.wb_order_id}: стикер не получен (№ ${item.order_number ?? '—'})`)].join('\n'))
        return
      }
      const w = window.open('', '_blank'); if (!w) return
      const pages = await Promise.all(tape.orders.map(async (order, index) => {
        if (!order.qr_asset?.preview_url) throw new Error(`Заказ WB №${order.wb_order_id}: стикер не получен`)
        const response = await fetch(resolveFbsAssetUrl(order.qr_asset.preview_url), { headers: { ...authHeaders(token) } })
        if (!response.ok) throw new Error(`Заказ WB №${order.wb_order_id}: стикер не получен`)
        const imageUrl = URL.createObjectURL(await response.blob())
        const number = order.order_number ?? index + 1
        return `<section class="label"><img src="${imageUrl}" alt="Стикер WB №${order.wb_order_id}"></section><section class="label service">№ ${number}<small>Заказ WB №${order.wb_order_id}</small></section>`
      }))
      const css = '@page{size:40mm 58mm;margin:0}html,body{margin:0;padding:0}.label{width:40mm;height:58mm;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;justify-content:center;break-after:page;padding:1mm;font-family:Arial,sans-serif;text-align:center}.label img{max-width:100%;max-height:100%;object-fit:contain}.service{font-size:28pt;font-weight:900}.service small{display:block;font-size:8pt;font-weight:400;margin-top:4mm}'
      w.document.write(`<title>Стикеры заказов FBS</title><style>${css}</style>${pages.join('')}<script>Promise.all(Array.from(document.images).map(function(i){return i.complete?Promise.resolve():new Promise(function(r){i.onload=r;i.onerror=r})})).then(function(){window.focus();window.print()})</script>`); w.document.close()
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось получить стикеры') }
    finally { setPrinting(false) }
  }, [authHeaders, canPrint, supplyId, token])

  const columns: Column<NumberedItem>[] = [
    { key: 'number', header: '№', width: 76, align: 'center', render: (i) => <Typography fontWeight={800}>{i.numberFrom === i.numberTo ? i.numberFrom : `${i.numberFrom}–${i.numberTo}`}</Typography> },
    { key: 'product', header: 'Товар', render: (i) => <Stack><TextCell value={i.product_name} /><Typography variant="caption" color="text.secondary">{i.article}</Typography></Stack> },
    { key: 'size', header: 'Размер', width: 92, align: 'center', render: (i) => i.size || '—' },
    { key: 'quantity', header: 'Кол-во', width: 90, align: 'right', render: (i) => <QtyCell value={i.quantity} /> },
    { key: 'collected', header: 'Собрал', width: 90, align: 'center', render: (i) => <CheckCell checked={Boolean(marks[markKey(i)]?.collected)} onChange={(checked) => setMark(markKey(i), { collected: checked })} ariaLabel={`Собрал ${i.product_name}`} testId="fbs-pick-collected" /> },
    { key: 'packed', header: 'Упаковал', width: 90, align: 'center', render: (i) => <CheckCell checked={Boolean(marks[markKey(i)]?.packed)} onChange={(checked) => setMark(markKey(i), { packed: checked })} ariaLabel={`Упаковал ${i.product_name}`} testId="fbs-pick-packed" /> },
  ]
  const empty = items.length === 0 ? { title: 'В поставке нет позиций для подбора', hint: 'Закройте лист и проверьте состав поставки' } : { title: 'Нет позиций по фильтру', hint: 'Сбросьте поиск или выберите «Все»' }
  return <ModalFrame open={open} title="Лист подбора" purpose={loading ? undefined : `Собрано ${collected}/${items.length} · Упаковано ${packed}/${items.length}`} busy={printing} onClose={onClose} testId="fbs-pick-list" actions={<><SecondaryAction onClick={onClose} disabled={printing}>Закрыть</SecondaryAction><PrintAction what="стикеры заказов" placement="panel" busy={printing} onClick={() => void printStickers()} disabledReason={!canPrint ? (printing ? 'Подготавливаем печать' : loading ? 'Лист подбора ещё загружается' : error ? 'Сначала загрузите лист подбора' : 'В поставке нет заказов для печати') : undefined} testId="fbs-pick-print-stickers" /></>}>
    {error ? <ErrorNotice>{error}</ErrorNotice> : null}
    <FilterBar search={search} onSearchChange={setSearch} searchPlaceholder="Артикул или название" testId="fbs-pick-filters"><ChoiceFilter value={filter} options={[{ value: 'all', label: 'Все' }, { value: 'not_collected', label: 'Не собраны' }, { value: 'not_packed', label: 'Не упакованы' }]} onChange={setFilter} ariaLabel="Фильтр листа" testId="fbs-pick-filter-choice" /></FilterBar>
    <DataTable columns={columns} rows={visible} getRowKey={(i) => markKey(i)} loading={loading} empty={empty} testId="fbs-pick-table" />
  </ModalFrame>
}
