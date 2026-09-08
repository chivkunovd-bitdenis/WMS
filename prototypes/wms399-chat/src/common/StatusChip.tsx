import { Chip } from '@mui/material'
import type { DocumentStatus } from '../types'

const LABELS: Record<DocumentStatus, { label: string; color: string; bg: string }> = {
  draft: { label: 'Черновик', color: '#334155', bg: '#e2e8f0' },
  submitted: { label: 'Отправлена', color: '#1e3a8a', bg: '#dbeafe' },
  in_progress: { label: 'В работе', color: '#7c2d12', bg: '#fed7aa' },
  confirmed: { label: 'Утверждена', color: '#134e4a', bg: '#a7f3d0' },
  shipped: { label: 'Отгружена', color: '#065f46', bg: '#bbf7d0' },
  closed: { label: 'Закрыта', color: '#334155', bg: '#e2e8f0' },
  discrepancy: { label: 'Расхождение', color: '#7f1d1d', bg: '#fecaca' },
}

export function StatusChip({ status }: { status: DocumentStatus }) {
  const p = LABELS[status]
  return (
    <Chip
      size="small"
      label={p.label}
      sx={{
        bgcolor: p.bg,
        color: p.color,
        fontWeight: 700,
        fontSize: 12,
        height: 22,
      }}
    />
  )
}

export function docKindLabel(kind: 'inbound' | 'mp_outbound' | 'fbs_batch' | 'return'): string {
  switch (kind) {
    case 'inbound':
      return 'Приёмка'
    case 'mp_outbound':
      return 'Отгрузка'
    case 'fbs_batch':
      return 'FBS-партия'
    case 'return':
      return 'Возврат'
  }
}
