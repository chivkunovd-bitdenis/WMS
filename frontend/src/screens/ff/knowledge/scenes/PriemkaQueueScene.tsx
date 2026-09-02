import { FfInboundQueuePage } from '../../FfInboundQueuePage'
import type { InboundQueueRow } from '../../../../utils/inboundQueues'
import { SceneShell } from './SceneShell'
import { SELLERS } from './data'

/** Шаг 1 статьи «Приёмка»: очередь документов, с которой начинается работа. */

const ROWS: InboundQueueRow[] = [
  {
    id: 'in-45',
    status: 'submitted',
    operation_type: 'inbound',
    line_count: 6,
    planned_delivery_date: '2026-09-03',
    seller_name: 'ООО Ловиана',
    document_number: '000045',
    display_number: '000045',
    goods_qty_total: 240,
    planned_box_count: 4,
    actual_box_count: 0,
    created_at: '2026-09-03T08:10:00Z',
  },
  {
    id: 'in-44',
    status: 'submitted',
    operation_type: 'inbound',
    line_count: 3,
    planned_delivery_date: '2026-09-03',
    seller_name: 'ИП Горячкина',
    document_number: '000044',
    display_number: '000044',
    goods_qty_total: 55,
    planned_box_count: 2,
    actual_box_count: 0,
    created_at: '2026-09-03T07:40:00Z',
  },
  {
    id: 'in-43',
    status: 'receiving',
    operation_type: 'inbound',
    line_count: 5,
    planned_delivery_date: '2026-09-02',
    seller_name: 'ООО Ситипак',
    document_number: '000043',
    display_number: '000043',
    goods_qty_total: 110,
    planned_box_count: 3,
    actual_box_count: 2,
    created_at: '2026-09-02T15:20:00Z',
  },
  {
    id: 'in-42',
    status: 'sorting',
    operation_type: 'inbound',
    line_count: 4,
    planned_delivery_date: '2026-09-02',
    seller_name: 'ИП Ларин',
    document_number: '000042',
    display_number: '000042',
    goods_qty_total: 70,
    planned_box_count: 2,
    actual_box_count: 2,
    sorting_remaining_qty: 30,
    created_at: '2026-09-02T11:05:00Z',
  },
  {
    id: 'in-41',
    status: 'verified',
    operation_type: 'inbound',
    line_count: 7,
    planned_delivery_date: '2026-09-01',
    seller_name: 'ООО Ловиана',
    document_number: '000041',
    display_number: '000041',
    goods_qty_total: 312,
    planned_box_count: 6,
    actual_box_count: 6,
    created_at: '2026-09-01T09:30:00Z',
  },
  {
    id: 'in-40',
    status: 'verified',
    operation_type: 'return',
    line_count: 2,
    planned_delivery_date: '2026-09-01',
    seller_name: 'ИП Горячкина',
    document_number: '000040',
    display_number: '000040',
    goods_qty_total: 12,
    planned_box_count: 1,
    actual_box_count: 1,
    has_discrepancy: true,
    created_at: '2026-09-01T08:15:00Z',
  },
]

export default function PriemkaQueueScene() {
  return (
    <SceneShell route="/app/ff/reception">
      <FfInboundQueuePage
        workspace="reception"
        rows={ROWS}
        sellers={SELLERS}
        onOpen={() => {}}
        onCreateDraft={() => {}}
      />
    </SceneShell>
  )
}
