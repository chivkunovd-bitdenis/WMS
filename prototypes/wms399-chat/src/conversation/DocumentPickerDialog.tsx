import { useMemo, useState } from 'react'
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/CloseOutlined'
import SearchIcon from '@mui/icons-material/SearchOutlined'
import DescriptionIcon from '@mui/icons-material/DescriptionOutlined'
import { useStore } from '../state/store'
import { EmptyState } from '../common/EmptyState'
import { Row } from '../common/Row'
import { docKindLabel, StatusChip } from '../common/StatusChip'
import { fmtRelative } from '../utils/format'
import type { DocumentKind } from '../types'

const KINDS: { value: DocumentKind | 'all'; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'inbound', label: 'Приёмка' },
  { value: 'mp_outbound', label: 'Отгрузка' },
  { value: 'fbs_batch', label: 'FBS' },
  { value: 'return', label: 'Возврат' },
]

export function DocumentPickerDialog() {
  const { ui, dispatch, documentById, currentActor, sellerById, warehouseById } = useStore()
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<DocumentKind | 'all'>('all')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const arr = Array.from(documentById.values())
    return arr
      .filter((d) => {
        if (currentActor.role === 'seller') return d.sellerId === currentActor.sellerId
        return true
      })
      .filter((d) => (kind === 'all' ? true : d.kind === kind))
      .filter((d) =>
        q
          ? d.number.toLowerCase().includes(q) ||
            d.summary.toLowerCase().includes(q) ||
            d.lines.some((l) => l.sku.toLowerCase().includes(q) || l.name.toLowerCase().includes(q))
          : true,
      )
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  }, [documentById, currentActor, kind, query])

  const close = () => dispatch({ type: 'toggle_document_picker', open: false })

  const pick = (docId: string) => {
    if (!ui.selectedConversationId) return
    dispatch({
      type: 'set_draft',
      conversationId: ui.selectedConversationId,
      patch: { documentRef: docId },
    })
    close()
  }

  if (!ui.showDocumentPicker) return null

  return (
    <Dialog open onClose={close} fullWidth maxWidth="md">
      <DialogTitle>
        <Row align="center" spacing={1}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
              Вставить карточку документа
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Ссылка на приёмку, отгрузку, FBS-партию или возврат. Открытие карточки не двигает статус документа.
            </Typography>
          </Box>
          <IconButton onClick={close} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Row>
      </DialogTitle>
      <DialogContent dividers>
        <Row spacing={1.25} sx={{ mb: 2 }}>
          <TextField
            size="small"
            fullWidth
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по номеру, тексту, SKU"
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              },
            }}
          />
          <TextField
            size="small"
            select
            value={kind}
            onChange={(e) => setKind(e.target.value as DocumentKind | 'all')}
            sx={{ minWidth: 160 }}
          >
            {KINDS.map((k) => (
              <MenuItem key={k.value} value={k.value}>
                {k.label}
              </MenuItem>
            ))}
          </TextField>
        </Row>
        {filtered.length === 0 ? (
          <EmptyState
            title="Ничего не нашли"
            description="Уточните запрос или снимите фильтр по типу. Селлер видит только свои документы."
          />
        ) : (
          <Stack spacing={1}>
            {filtered.map((d) => {
              const seller = sellerById.get(d.sellerId)
              const warehouse = warehouseById.get(d.warehouseId)
              return (
                <Box
                  key={d.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => pick(d.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') pick(d.id)
                  }}
                  sx={(t) => ({
                    p: 1.5,
                    borderRadius: 2,
                    border: '1px solid',
                    borderColor: 'divider',
                    display: 'flex',
                    gap: 1.5,
                    alignItems: 'flex-start',
                    cursor: 'pointer',
                    outline: 'none',
                    transition: 'background 120ms',
                    '&:hover, &:focus-visible': { bgcolor: t.palette.action.hover, borderColor: t.palette.primary.light },
                  })}
                >
                  <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: 'primary.main', color: 'primary.contrastText' }}>
                    <DescriptionIcon />
                  </Box>
                  <Stack sx={{ flex: 1, minWidth: 0 }} spacing={0.5}>
                    <Row align="center" spacing={0.75}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                        {docKindLabel(d.kind)} · {d.number}
                      </Typography>
                      <StatusChip status={d.status} />
                    </Row>
                    <Typography variant="body2" color="text.secondary" sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {d.summary}
                    </Typography>
                    <Row spacing={0.5} wrap>
                      {seller ? <Chip size="small" label={seller.brand} sx={{ bgcolor: 'action.hover' }} /> : null}
                      {warehouse ? <Chip size="small" label={warehouse.name} sx={{ bgcolor: 'action.hover' }} /> : null}
                      <Chip size="small" label={`${d.totalFact}/${d.totalPlanned} шт`} sx={{ bgcolor: 'action.hover' }} />
                      <Chip size="small" label={`Обновлено ${fmtRelative(d.updatedAt)}`} sx={{ bgcolor: 'action.hover' }} />
                    </Row>
                  </Stack>
                </Box>
              )
            })}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Отмена</Button>
      </DialogActions>
    </Dialog>
  )
}
