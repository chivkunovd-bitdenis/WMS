import { useMemo } from 'react'
import { Alert, Box, Button, Chip, Divider, IconButton, LinearProgress, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material'
import OpenInNewIcon from '@mui/icons-material/OpenInNewOutlined'
import DescriptionIcon from '@mui/icons-material/DescriptionOutlined'
import HistoryIcon from '@mui/icons-material/HistoryToggleOffOutlined'
import LinkIcon from '@mui/icons-material/LinkOutlined'
import { useStore } from '../state/store'
import { Row } from '../common/Row'
import { EmptyState } from '../common/EmptyState'
import { StatusChip, docKindLabel } from '../common/StatusChip'
import { fmtRelative, fmtTime } from '../utils/format'
import type { Conversation } from '../types'

export function ContextPanel({ conversation }: { conversation: Conversation }) {
  const { data, ui, dispatch, documentById, actorById, sellerById, warehouseById, actions } = useStore()

  const doc = conversation.documentId ? documentById.get(conversation.documentId) : null
  const seller = conversation.sellerId ? sellerById.get(conversation.sellerId) : null
  const warehouse = conversation.warehouseId ? warehouseById.get(conversation.warehouseId) : null

  const linkedMsgs = useMemo(() => {
    if (!doc) return []
    const ids = data.messagesByConversation.get(conversation.id) ?? []
    return ids
      .map((id) => data.messages.get(id))
      .filter((m): m is NonNullable<typeof m> => Boolean(m))
      .filter((m) => m.documentRef === doc.id || m.kind === 'document_card' || m.attachments?.length)
  }, [doc, data.messages, data.messagesByConversation, conversation.id])

  const outdated = ui.demo.documentOutdated
  const noAccess = ui.demo.permissionDenied

  if (!doc) {
    return (
      <Stack sx={{ p: 2, gap: 1.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
          Общий канал
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Этот канал не привязан к документу. Он один на пару селлер↔склад и
          подходит для нерегулярных вопросов. Каналы под приёмки, отгрузки и
          FBS появляются автоматически при первом сообщении по документу.
        </Typography>
        {seller ? (
          <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: 'action.hover' }}>
            <Typography variant="caption" color="text.secondary">
              Селлер
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {seller.brand}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Контакт: {seller.contact}
            </Typography>
          </Box>
        ) : null}
        {warehouse ? (
          <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: 'action.hover' }}>
            <Typography variant="caption" color="text.secondary">
              Склад
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {warehouse.name} · {warehouse.city}
            </Typography>
          </Box>
        ) : null}
        <Divider />
        <Typography variant="caption" color="text.secondary">
          Прикрепить сюда конкретный документ можно через кнопку 📎 → «Документ» в редакторе.
        </Typography>
      </Stack>
    )
  }

  if (noAccess) {
    return (
      <Stack sx={{ p: 2, gap: 1.5 }}>
        <Alert severity="warning">Нет доступа к документу для текущей роли.</Alert>
        <Typography variant="body2" color="text.secondary">
          Канал остаётся доступен, но карточка и таймлайн скрыты. Обратитесь к
          админу ФФ, если это ошибка.
        </Typography>
      </Stack>
    )
  }

  return (
    <Stack sx={{ p: 2, gap: 2 }} data-testid="context-panel">
      <Row align="center" spacing={1}>
        <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: 'primary.main', color: 'primary.contrastText' }}>
          <DescriptionIcon fontSize="small" />
        </Box>
        <Stack sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 800 }} noWrap>
            {docKindLabel(doc.kind)} · {doc.number}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {doc.summary}
          </Typography>
        </Stack>
        <Tooltip title="Открыть документ в разделе">
          <IconButton
            aria-label="Открыть документ"
            onClick={() => dispatch({ type: 'open_document', documentId: doc.id })}
          >
            <OpenInNewIcon />
          </IconButton>
        </Tooltip>
      </Row>
      <Row spacing={0.5} wrap>
        <StatusChip status={doc.status} />
        <Chip size="small" label={`План ${doc.totalPlanned} шт`} sx={{ bgcolor: 'action.hover' }} />
        <Chip size="small" label={`Факт ${doc.totalFact} шт`} sx={{ bgcolor: 'action.hover' }} />
        <Chip size="small" label={`Обновлено ${fmtRelative(doc.updatedAt)}`} sx={{ bgcolor: 'action.hover' }} />
        {seller ? <Chip size="small" label={seller.brand} sx={{ bgcolor: 'action.hover' }} /> : null}
        {warehouse ? <Chip size="small" label={warehouse.name} sx={{ bgcolor: 'action.hover' }} /> : null}
      </Row>
      {outdated ? (
        <Alert severity="warning">
          Документ обновился с момента открытия канала. Откройте его заново, чтобы увидеть свежие строки.
        </Alert>
      ) : null}
      <Box>
        <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
          Прогресс
        </Typography>
        <LinearProgress
          variant="determinate"
          value={doc.totalPlanned > 0 ? Math.min(100, Math.round((doc.totalFact / doc.totalPlanned) * 100)) : 0}
          sx={{ height: 8, borderRadius: 4 }}
        />
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          {doc.totalPlanned > 0
            ? `${Math.min(100, Math.round((doc.totalFact / doc.totalPlanned) * 100))}% от плана`
            : 'План не задан'}
        </Typography>
      </Box>

      <Box>
        <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
          Строки документа
        </Typography>
        <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Артикул</TableCell>
                <TableCell>Наименование</TableCell>
                <TableCell align="right">План</TableCell>
                <TableCell align="right">Факт</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {doc.lines.map((l) => (
                <TableRow key={l.sku}>
                  <TableCell sx={{ fontFamily: 'ui-monospace, monospace', fontWeight: 700 }}>{l.sku}</TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {l.name}
                    </Typography>
                    {l.note ? (
                      <Typography variant="caption" color="warning.main">
                        {l.note}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell align="right">{l.planned}</TableCell>
                  <TableCell align="right">
                    {l.fact ?? '—'}
                    {l.fact != null && l.fact < l.planned ? (
                      <Typography variant="caption" color="error" sx={{ ml: 0.5 }}>
                        (−{l.planned - l.fact})
                      </Typography>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Box>

      <Box>
        <Row align="center" spacing={1} sx={{ mb: 0.75 }}>
          <HistoryIcon fontSize="small" color="primary" />
          <Typography variant="subtitle2">Таймлайн</Typography>
        </Row>
        <Stack spacing={0.75}>
          {doc.timeline.map((ev) => {
            const actor = actorById.get(ev.by)
            return (
              <Box key={ev.id} sx={{ p: 1, borderRadius: 1.5, bgcolor: 'action.hover' }}>
                <Typography variant="caption" color="text.secondary">
                  {fmtTime(ev.at)} · {actor?.name ?? '—'}
                </Typography>
                <Typography variant="body2">{ev.text}</Typography>
                {ev.linkedMessageId ? (
                  <Button
                    size="small"
                    variant="text"
                    startIcon={<LinkIcon />}
                    onClick={() => actions.openConversation(conversation.id, { flashMessageId: ev.linkedMessageId })}
                  >
                    Открыть сообщение
                  </Button>
                ) : null}
              </Box>
            )
          })}
        </Stack>
      </Box>

      <Box>
        <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
          Связанные сообщения
        </Typography>
        {linkedMsgs.length === 0 ? (
          <EmptyState title="Нет связей" description="Пока никаких карточек или вложений с документом не связывали." />
        ) : (
          <Stack spacing={0.5}>
            {linkedMsgs.slice(0, 6).map((m) => (
              <Button
                key={m.id}
                size="small"
                variant="text"
                onClick={() => actions.openConversation(conversation.id, { flashMessageId: m.id })}
                sx={{ justifyContent: 'flex-start', textAlign: 'left' }}
              >
                {fmtTime(m.createdAt)} · {m.text?.slice(0, 60) || (m.attachments?.length ? '📎 Вложение' : 'Карточка документа')}
              </Button>
            ))}
          </Stack>
        )}
      </Box>
    </Stack>
  )
}
