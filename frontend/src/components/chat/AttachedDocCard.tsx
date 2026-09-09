// Attached-document card rendered inside a chat message.
//
// Two behaviours combined into a single component per the owner's minimal
// contract: it shows the document title (with seller name for FF admins who
// jump between sellers), and clicks navigate to the matching route so the
// operator can jump straight to the doc without leaving the chat.

import { memo, useMemo } from 'react'
import { Box, Paper, Typography } from '@mui/material'
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined'
import { useNavigate } from 'react-router-dom'
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

function routeFor(kind: string, id: string, base: string): string | null {
  // The chat card only jumps to routes we know exist in App.tsx today. If a
  // kind lands here without a route we render it as a static card so the
  // seller still sees the reference.
  switch (kind) {
    case 'fbs_order':
    case 'fbs_supply':
      return `${base}/ff/fbs?open=${id}`
    case 'inbound_intake':
      return `${base}/ff/inbound?open=${id}`
    case 'marketplace_unload':
    case 'outbound_shipment':
      return `${base}/ff/mp-shipments?open=${id}`
    default:
      return null
  }
}

export const AttachedDocCard = memo(function AttachedDocCard({
  document,
  basePath = '/app',
}: Props) {
  const navigate = useNavigate()
  const label = KIND_LABEL[document.kind] ?? 'Документ'
  const target = useMemo(
    () => routeFor(document.kind, document.id, basePath),
    [document.kind, document.id, basePath],
  )
  const clickable = target !== null
  return (
    <Paper
      variant="outlined"
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
