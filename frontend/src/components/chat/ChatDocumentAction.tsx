import { useEffect, useState } from 'react'
import { Button, MenuItem, Stack, TextField, Tooltip } from '@mui/material'
import { apiUrl } from '../../api'
import { ChatOpenButton } from './ChatOpenButton'
import type { AttachedDocument } from './chatApi'
type Props = {
  token: string; authHeaders: (t: string) => Record<string, string>; currentUserId: string | null
  kind: string; documentId: string
}
export function ChatDocumentAction(props: Props) {
  return <DocumentAction key={`${props.kind}:${props.documentId}:${props.token}`} {...props} />
}
function DocumentAction({ token, authHeaders, currentUserId, kind, documentId }: Props) {
  const [documents, setDocuments] = useState<AttachedDocument[]>([])
  const [sellerId, setSellerId] = useState('')
  const [failed, setFailed] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    void fetch(apiUrl(`/operations/chat/document-options/${kind}/${documentId}`), { headers: authHeaders(token) })
      .then(async (r) => {
        if (r.status === 403) { if (active) setForbidden(true); return [] }
        if (!r.ok) throw Error()
        return await r.json() as AttachedDocument[]
      })
      .then((rows) => { if (active) { setDocuments(rows); setSellerId(rows[0]?.seller_id ?? '') } })
      .catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [token, authHeaders, kind, documentId, attempt])
  const document = documents.find((d) => d.seller_id === sellerId)
  if (forbidden) return <Tooltip title="Нет права просмотра этого документа. Обратитесь к администратору.">
    <span><Button disabled>Написать сообщение</Button></span>
  </Tooltip>
  if (failed) return <Button onClick={() => { setFailed(false); setAttempt((n) => n + 1) }}>Не удалось открыть чат. Повторить</Button>
  if (!document) return null
  return <Stack direction="row" spacing={1}>
    {documents.length > 1 && <TextField select size="small" label="Продавец" value={sellerId}
      onChange={(e) => setSellerId(e.target.value)} sx={{ minWidth: 180 }}>
      {documents.map((d) => <MenuItem key={d.seller_id} value={d.seller_id}>{d.seller_name}</MenuItem>)}
    </TextField>}
    <ChatOpenButton key={sellerId} token={token} authHeaders={authHeaders} currentUserId={currentUserId}
      sellerId={sellerId} sellerName={document.seller_name} attachedDocument={document} />
  </Stack>
}
