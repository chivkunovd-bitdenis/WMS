// One-line "Написать сообщение" action for document pages.
//
// Pass the seller/document context; the button owns its own dialog state so a
// doc page only wires props and a single button element into its toolbar.

import { useState } from 'react'
import { Button, Tooltip } from '@mui/material'
import ChatBubbleOutlineOutlinedIcon from '@mui/icons-material/ChatBubbleOutlineOutlined'
import { ChatDialog } from './ChatDialog'
import type { AttachedDocument } from './chatApi'

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  currentUserId: string | null
  sellerId: string
  sellerName?: string
  attachedDocument?: AttachedDocument
  label?: string
  size?: 'small' | 'medium'
  variant?: 'text' | 'outlined' | 'contained'
}

export function ChatOpenButton({
  token,
  authHeaders,
  currentUserId,
  sellerId,
  sellerName,
  attachedDocument,
  label = 'Написать сообщение',
  size = 'small',
  variant = 'outlined',
}: Props) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Tooltip title="Открыть чат с продавцом и прикрепить документ">
        <Button
          size={size}
          variant={variant}
          startIcon={<ChatBubbleOutlineOutlinedIcon fontSize="small" />}
          onClick={() => setOpen(true)}
          data-testid="chat-open-button"
        >
          {label}
        </Button>
      </Tooltip>
      <ChatDialog
        open={open}
        onClose={() => setOpen(false)}
        token={token}
        authHeaders={authHeaders}
        currentUserId={currentUserId}
        sellerId={sellerId}
        sellerName={sellerName}
        attachedDocument={attachedDocument}
      />
    </>
  )
}
