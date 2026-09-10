import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Alert, Box, Button, Paper, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import { apiUrl } from '../../api'
import { ChatOpenButton } from '../../components/chat/ChatOpenButton'
import type { AttachedDocument } from '../../components/chat/chatApi'

type DocumentDetail = { document: AttachedDocument; status: string; lines: { product: string; quantity: number; received?: number; order_id?: string }[] }
type Props = {
  token: string; authHeaders: (t: string) => Record<string, string>; currentUserId: string | null
}
export function ChatDocumentScreen(props: Props) {
  const { kind, documentId } = useParams()
  const [params] = useSearchParams()
  return <DocumentScreen key={`${kind}:${documentId}:${params.get('seller_id')}:${props.token}`} {...props} />
}
function DocumentScreen({ token, authHeaders, currentUserId }: Props) {
  const { kind, documentId } = useParams()
  const [params] = useSearchParams()
  const sellerId = params.get('seller_id') ?? ''
  const [detail, setDetail] = useState<DocumentDetail | null>(null)
  const [error, setError] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  useEffect(() => {
    const controller = new AbortController()
    void fetch(apiUrl(`/operations/chat/documents/${kind}/${documentId}?seller_id=${sellerId}`), {
      headers: authHeaders(token), signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw Error()
      const row = await response.json()
      if (!controller.signal.aborted) setDetail(row)
    }).catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => controller.abort()
  }, [kind, documentId, sellerId, token, authHeaders])
  const base = location.pathname.split('/chat')[0]
  const workDocumentTarget = base === '/app/ff' ? (
    kind === 'fbs_supply' ? `/app/ff/fbs?supply_id=${documentId}` :
    kind === 'inbound_intake' ? `/app/ff/reception?open=${documentId}` :
    kind === 'outbound_shipment' ? `/app/ff/mp-shipments?open_outbound=${documentId}` :
    kind === 'marketplace_unload' ? `/app/ff/mp-shipments?open_mp=${documentId}` : null
  ) : kind === 'inbound_intake' ? `${base}/inbound/${documentId}` : null
  return <Paper variant="outlined" sx={{ m: 2, p: 2 }}>
    <Button onClick={() => navigate(`${base}/chat?seller_id=${sellerId}`)}>Вернуться в чат</Button>
    {error && <Alert severity="error">Документ не найден или у вас нет права его просматривать.</Alert>}
    {detail ? <>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2, my: 2 }}>
        <Box><Typography variant="h5">{detail.document.title}</Typography>
          <Typography>{detail.document.seller_name}</Typography>
          <Typography color="text.secondary">Статус: {detail.status}</Typography></Box>
        <ChatOpenButton token={token} authHeaders={authHeaders} currentUserId={currentUserId}
          sellerId={sellerId} sellerName={detail.document.seller_name} attachedDocument={detail.document} />
      </Box>
      <Table><TableHead><TableRow><TableCell>{kind === 'fbs_supply' ? 'Заказ' : 'Товар'}</TableCell><TableCell>Количество</TableCell></TableRow></TableHead>
        <TableBody>{detail.lines.map((line, i) => <TableRow key={i}>
          <TableCell>{line.order_id ? <Button onClick={() => navigate(`${base}/chat/documents/fbs_order/${line.order_id}?seller_id=${sellerId}`)}>{line.product}</Button> : line.product}</TableCell>
          <TableCell>{line.quantity}</TableCell>
        </TableRow>)}</TableBody></Table>
      {workDocumentTarget && <Button sx={{ mt: 2 }} onClick={() => navigate(workDocumentTarget)}>
        Открыть рабочий документ
      </Button>}
    </> : !error && <Typography>Загрузка документа…</Typography>}
  </Paper>
}
