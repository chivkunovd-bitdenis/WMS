import { useEffect, useState } from 'react'
import { Alert, Button, Dialog, DialogContent, DialogTitle, MenuItem, TextField, Typography } from '@mui/material'
import { apiUrl } from '../../api'
import type { ChatConversation } from './chatApi'
export function ChatParticipants({ conversation, token, authHeaders, onClose }: {
  conversation: ChatConversation; token: string; authHeaders: (t: string) => Record<string, string>; onClose: () => void
}) {
  const [options, setOptions] = useState<{ id: string; email: string }[]>([])
  const [members, setMembers] = useState<string[]>([])
  const [selected, setSelected] = useState('')
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    void Promise.all([
      fetch(apiUrl(`/operations/chat/participant-options?seller_id=${conversation.seller_id}`), { headers: authHeaders(token) }),
      fetch(apiUrl(`/operations/chat/conversations/${conversation.id}/participants`), { headers: authHeaders(token) }),
    ]).then(async ([a, b]) => {
      if (!a.ok || !b.ok) throw Error()
      const opts = await a.json(); const rows = await b.json()
      if (active) { setOptions(opts); setMembers(rows.items.map((r: { user_id: string }) => r.user_id)) }
    }).catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [conversation.id, conversation.seller_id, token, authHeaders])
  const add = async () => {
    if (busy || !selected) return
    setBusy(true); setError(false)
    try {
      const response = await fetch(apiUrl(`/operations/chat/conversations/${conversation.id}/participants`), {
        method: 'POST', headers: { ...authHeaders(token), 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: selected }),
      })
      if (!response.ok) throw Error()
      setMembers((ids) => [...ids, selected]); setSelected('')
    } catch { setError(true) } finally { setBusy(false) }
  }
  return <Dialog open onClose={onClose} fullWidth maxWidth="sm"><DialogTitle>Участники</DialogTitle><DialogContent>
    {error && <Alert severity="error">Не удалось загрузить или сохранить участников.</Alert>}
    {members.map((id) => <Typography key={id}>{options.find((o) => o.id === id)?.email ?? 'Участник'}</Typography>)}
    <TextField select fullWidth label="Добавить участника" value={selected} onChange={(e) => setSelected(e.target.value)} sx={{ mt: 2 }}>
      {options.filter((o) => !members.includes(o.id)).map((o) => <MenuItem key={o.id} value={o.id}>{o.email}</MenuItem>)}
    </TextField><Button disabled={busy || !selected} onClick={() => void add()}>Добавить</Button><Button onClick={onClose}>Закрыть</Button>
  </DialogContent></Dialog>
}
