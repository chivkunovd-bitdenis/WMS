// Attached-document card rendered inside a chat message.
//
// Two behaviours combined into a single component per the owner's minimal
// contract: it shows the document title (with seller name for FF admins who
// jump between sellers), and clicks navigate to the matching route so the
// operator can jump straight to the doc without leaving the chat.

import { memo, useMemo } from 'react'
import { Box, Paper, Typography } from '@mui/material'
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined'
import { useNavigate, useLocation } from 'react-router-dom'
import type { AttachedDocument } from './chatApi'

type Props = {
  document: AttachedDocument
  basePath?: string
}

const KIND_LABEL: Record<string, string> = {
  fbs_order: 'FBS-заказ',
  fbs_supply: 'FBS-поставка',
  inbound_intake: 'Приёмка',
  marketplace_unload: 'Отгрузка',
  outbound_shipment: 'Отгрузка',
}

export const AttachedDocCard = memo(function AttachedDocCard({
  document,
  basePath,
}: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const base = basePath ?? (location.pathname.startsWith('/app/ff') ? '/app/ff' : location.pathname.startsWith('/app/seller') ? '/app/seller' : '')
  const label = KIND_LABEL[document.kind] ?? 'Документ'
  const target = useMemo(
    () => `${base}/chat/documents/${document.kind}/${document.id}?seller_id=${document.seller_id}`,
    [document.kind, document.id, document.seller_id, base],
  )
  const clickable = target !== null
  return (
    <Paper
      variant="outlined"
      role="link"
      tabIndex={0}
      onKeyDown={(event) => { if (event.key === 'Enter') navigate(target) }}
      onClick={() => {
        if (target) navigate(target)
      }}
      sx={{
        p: 1.25,
        display: 'flex',
        gap: 1,
        alignItems: 'center',
        maxWidth: 360,
        cursor: clickable ? 'pointer' : 'default',
        borderColor: 'divider',
        bgcolor: 'background.default',
        '&:hover': clickable
          ? { borderColor: 'primary.main', bgcolor: 'action.hover' }
          : undefined,
      }}
      data-testid="chat-attached-doc-card"
      data-doc-kind={document.kind}
      data-doc-id={document.id}
    >
      <DescriptionOutlinedIcon fontSize="small" color={clickable ? 'primary' : 'disabled'} />
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" noWrap>
          {label}
          {document.seller_name ? ` · ${document.seller_name}` : ''}
        </Typography>
        <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>
          {document.title}
        </Typography>
      </Box>
    </Paper>
  )
})
