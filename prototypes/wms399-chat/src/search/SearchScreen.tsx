import { useMemo } from 'react'
import {
  Alert,
  Box,
  Chip,
  FormControlLabel,
  InputAdornment,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/SearchOutlined'
import { useStore } from '../state/store'
import { conversationAccessible, visibleMessagesForActor } from '../state/selectors'
import { fmtTime } from '../utils/format'
import { EmptyState } from '../common/EmptyState'
import { Row } from '../common/Row'
import type { Message } from '../types'

type Hit = {
  message: Message
  conversationTitle: string
  conversationId: string
  before?: string
  after?: string
  matchStart: number
}

export function SearchScreen() {
  const { ui, dispatch, data, currentActor, sellerById, actions, actorById, documentById } = useStore()
  const q = ui.search.query.trim().toLowerCase()
  const isSeller = currentActor.role === 'seller'

  const results = useMemo(() => {
    const list: Hit[] = []
    if (q.length < 2 && !ui.search.hasAttachment && !ui.search.hasDocument) return list
    data.conversations.forEach((conv) => {
      if (!conversationAccessible(conv, currentActor)) return
      if (ui.search.sellerId && conv.sellerId !== ui.search.sellerId) return
      const ids = data.messagesByConversation.get(conv.id) ?? []
      const msgs = ids
        .map((id) => data.messages.get(id))
        .filter((m): m is NonNullable<typeof m> => Boolean(m))
      const visible = visibleMessagesForActor(msgs, currentActor)
      for (const m of visible) {
        if (ui.search.hasAttachment && !(m.attachments?.length)) continue
        if (ui.search.hasDocument && !m.documentRef) continue
        const doc = m.documentRef ? documentById.get(m.documentRef) : null
        const haystack = `${m.text ?? ''}\n${doc ? `${doc.number} ${doc.summary} ${doc.lines.map((l) => `${l.sku} ${l.name}`).join(' ')}` : ''}`
        const lower = haystack.toLowerCase()
        if (q && !lower.includes(q)) continue
        const idx = q ? lower.indexOf(q) : 0
        list.push({
          message: m,
          conversationTitle: conv.title,
          conversationId: conv.id,
          matchStart: idx,
          before: haystack.slice(Math.max(0, idx - 40), idx),
          after: haystack.slice(idx + q.length, idx + q.length + 60),
        })
      }
    })
    return list.slice(0, 100)
  }, [q, ui.search, data, currentActor, documentById])

  const sellers = Array.from(sellerById.values())

  return (
    <Stack sx={{ maxWidth: 960, mx: 'auto', gap: 2 }} data-testid="search-screen">
      <Box>
        <Typography variant="h5" sx={{ fontWeight: 800 }}>
          Поиск по каналам
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isSeller
            ? 'Ищем только по вашим каналам и только сообщения, которые вам видимы.'
            : 'Полнотекстовый поиск по всем каналам вашего тенанта: текст, номера документов, SKU.'}
        </Typography>
      </Box>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Row spacing={1.5} wrap>
          <TextField
            size="small"
            fullWidth
            autoFocus
            value={ui.search.query}
            onChange={(e) => dispatch({ type: 'set_search', patch: { query: e.target.value } })}
            placeholder="Например: недовоз, IN-2926, 88213"
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" />
                  </InputAdornment>
                ),
              },
            }}
            sx={{ flex: 2, minWidth: 260 }}
          />
          {!isSeller ? (
            <TextField
              size="small"
              select
              label="Селлер"
              value={ui.search.sellerId ?? ''}
              onChange={(e) => dispatch({ type: 'set_search', patch: { sellerId: e.target.value ? String(e.target.value) : null } })}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="">Все</MenuItem>
              {sellers.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.brand}
                </MenuItem>
              ))}
            </TextField>
          ) : null}
          <FormControlLabel
            control={
              <Switch
                checked={ui.search.hasAttachment}
                onChange={(e) => dispatch({ type: 'set_search', patch: { hasAttachment: e.target.checked } })}
              />
            }
            label="С вложением"
          />
          <FormControlLabel
            control={
              <Switch
                checked={ui.search.hasDocument}
                onChange={(e) => dispatch({ type: 'set_search', patch: { hasDocument: e.target.checked } })}
              />
            }
            label="С карточкой документа"
          />
        </Row>
      </Paper>

      {q.length > 0 && q.length < 2 ? (
        <Alert severity="info">Введите минимум 2 символа.</Alert>
      ) : null}
      {results.length >= 100 ? (
        <Alert severity="warning">Показываем первые 100 совпадений. Уточните запрос, если ищете конкретное.</Alert>
      ) : null}

      {q.length < 2 && !ui.search.hasAttachment && !ui.search.hasDocument ? (
        <EmptyState
          title="Начните искать"
          description="Ищем по тексту сообщений, номерам документов, SKU. Фильтры сверху ограничивают выборку."
        />
      ) : results.length === 0 ? (
        <EmptyState title="Ничего не нашли" description="Попробуйте изменить запрос или снять один из фильтров." />
      ) : (
        <Stack spacing={1}>
          {results.map((r) => {
            const author = actorById.get(r.message.authorId)
            return (
              <Paper
                key={r.message.id}
                variant="outlined"
                sx={(t) => ({
                  p: 1.5,
                  cursor: 'pointer',
                  transition: 'background 120ms',
                  '&:hover': { bgcolor: t.palette.action.hover, borderColor: t.palette.primary.light },
                })}
                onClick={() =>
                  actions.openConversation(r.conversationId, {
                    flashMessageId: r.message.id,
                    threadRootId: r.message.threadRootId,
                  })
                }
              >
                <Row align="center" spacing={1} sx={{ mb: 0.5 }}>
                  <Chip size="small" label={r.conversationTitle} sx={{ fontWeight: 700 }} />
                  {r.message.visibility === 'internal' ? (
                    <Chip
                      size="small"
                      label="внутр."
                      sx={{ bgcolor: 'warning.main', color: 'warning.contrastText', fontWeight: 700 }}
                    />
                  ) : null}
                  <Typography variant="caption" color="text.secondary">
                    {author?.name ?? '—'} · {fmtTime(r.message.createdAt)}
                  </Typography>
                </Row>
                <Typography variant="body2" sx={{ color: 'text.primary' }}>
                  <span style={{ opacity: 0.65 }}>…{r.before}</span>
                  <mark style={{ padding: '0 3px', background: '#fde68a', borderRadius: 3 }}>{q || ''}</mark>
                  <span>{r.after}</span>
                </Typography>
                {r.message.attachments?.length ? (
                  <Typography variant="caption" color="text.secondary">
                    📎 {r.message.attachments.length} вложение{r.message.attachments.length === 1 ? '' : 'я'}
                  </Typography>
                ) : null}
                {r.message.documentRef ? (
                  <Typography variant="caption" color="text.secondary">
                    📄 карточка документа
                  </Typography>
                ) : null}
              </Paper>
            )
          })}
        </Stack>
      )}
    </Stack>
  )
}
