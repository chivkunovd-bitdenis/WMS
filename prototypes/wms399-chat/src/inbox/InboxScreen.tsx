import { useMemo } from 'react'
import { Box, Stack, TextField, Tabs, Tab, InputAdornment, Typography, MenuItem, Select, FormControl, InputLabel } from '@mui/material'
import SearchIcon from '@mui/icons-material/SearchOutlined'
import { useStore } from '../state/store'
import { EmptyState } from '../common/EmptyState'
import { ConversationRow } from './ConversationRow'
import { conversationAccessible } from '../state/selectors'
import type { Conversation } from '../types'

export function InboxScreen() {
  const { data, ui, dispatch, currentActor, sellerById } = useStore()

  const conversations = useMemo(() => {
    const list: Conversation[] = []
    data.conversations.forEach((c) => list.push(c))
    return list
  }, [data.conversations])

  const filtered = useMemo(() => {
    const q = ui.inboxFilter.query.trim().toLowerCase()
    return conversations
      .filter((c) => conversationAccessible(c, currentActor))
      .filter((c) => {
        if (ui.inboxFilter.kind === 'mentions') return c.mentionIds.length > 0
        if (ui.inboxFilter.kind === 'followup') return c.followupOpen
        if (ui.inboxFilter.kind === 'archived') return c.archived
        if (ui.inboxFilter.kind === 'muted') return c.muted
        return !c.archived
      })
      .filter((c) => (ui.inboxFilter.sellerId ? c.sellerId === ui.inboxFilter.sellerId : true))
      .filter((c) =>
        q
          ? c.title.toLowerCase().includes(q) ||
            (c.subtitle ?? '').toLowerCase().includes(q)
          : true,
      )
      .sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
        const aLast = a.lastMessageId ? data.messages.get(a.lastMessageId)?.createdAt ?? '' : ''
        const bLast = b.lastMessageId ? data.messages.get(b.lastMessageId)?.createdAt ?? '' : ''
        return bLast.localeCompare(aLast)
      })
  }, [conversations, ui.inboxFilter, currentActor, data.messages])

  const sellers = Array.from(sellerById.values())
  const isSeller = currentActor.role === 'seller'

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }} data-testid="inbox">
      <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Typography variant="h6">Инбокс</Typography>
          <Typography variant="caption" color="text.secondary">
            {filtered.length} каналов
          </Typography>
        </Stack>
        <TextField
          fullWidth
          size="small"
          placeholder="Поиск канала…"
          value={ui.inboxFilter.query}
          onChange={(e) => dispatch({ type: 'set_inbox_filter', patch: { query: e.target.value } })}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
        {!isSeller ? (
          <FormControl fullWidth size="small" sx={{ mt: 1.25 }}>
            <InputLabel>Селлер</InputLabel>
            <Select
              label="Селлер"
              value={ui.inboxFilter.sellerId ?? ''}
              onChange={(e) => dispatch({ type: 'set_inbox_filter', patch: { sellerId: e.target.value ? String(e.target.value) : null } })}
            >
              <MenuItem value="">Все</MenuItem>
              {sellers.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.brand}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        ) : null}
        <Tabs
          value={ui.inboxFilter.kind}
          onChange={(_, v) => dispatch({ type: 'set_inbox_filter', patch: { kind: v } })}
          variant="scrollable"
          scrollButtons={false}
          sx={{ mt: 1, minHeight: 34, '& .MuiTab-root': { minHeight: 34, fontWeight: 700, px: 1.5 } }}
        >
          <Tab value="all" label="Все" />
          <Tab value="mentions" label="Упоминания" />
          <Tab value="followup" label="Требуют ответа" />
          <Tab value="muted" label="Заглушены" />
          <Tab value="archived" label="Архив" />
        </Tabs>
      </Box>
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {filtered.length === 0 ? (
          <EmptyState
            title="Здесь ничего нет"
            description="Попробуйте изменить фильтр или сбросить поиск. Каналы под документы появляются, когда в них написано первое сообщение."
          />
        ) : (
          <Stack divider={<Box sx={{ borderBottom: '1px solid', borderColor: 'divider' }} />}>
            {filtered.map((c) => (
              <ConversationRow key={c.id} conversation={c} />
            ))}
          </Stack>
        )}
      </Box>
    </Box>
  )
}
