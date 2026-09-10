import { useEffect, useState } from 'react'
import { Alert, Box, Button, Link } from '@mui/material'
import { attachmentContentUrl, type ChatAttachment } from './chatApi'

type Props = {
  attachment: ChatAttachment
  token: string
  authHeaders: (token: string) => Record<string, string>
}
export function ChatAttachmentView(props: Props) {
  return <AttachmentContent key={`${props.attachment.id}:${props.token}`} {...props} />
}
function AttachmentContent({ attachment, token, authHeaders }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!attachment.is_image && attempt === 0) return
    const controller = new AbortController()
    let objectUrl: string | undefined
    void fetch(attachmentContentUrl(attachment.id), {
      headers: authHeaders(token), signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) throw new Error('attachment')
      const blob = await response.blob()
      if (controller.signal.aborted) return
      // Downloaded HTML/SVG must never acquire the app's origin as an active
      // blob document. Only server-validated raster images retain their MIME.
      objectUrl = URL.createObjectURL(attachment.is_image ? blob : new Blob([blob], { type: 'application/octet-stream' }))
      setUrl(objectUrl)
      if (!attachment.is_image) {
        const link = document.createElement('a')
        link.href = objectUrl; link.download = attachment.filename; link.click()
      }
    }).catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [attachment.id, attachment.is_image, attachment.filename, authHeaders, token, attempt])
  if (failed) return <Alert severity="error">Не удалось загрузить {attachment.filename}
    <Button onClick={() => { setFailed(false); setUrl(null); setAttempt((n) => n + 1) }}>Повторить</Button></Alert>
  if (!attachment.is_image && attempt === 0) return <Button color="inherit" onClick={() => setAttempt(1)}>{attachment.filename}</Button>
  if (!url) return <span>Загрузка {attachment.filename}…</span>
  return <Link href={url} download={attachment.filename}>
    {attachment.is_image ? <Box component="img" src={url} alt={attachment.filename}
      sx={{ maxWidth: 220, maxHeight: 220, display: 'block', borderRadius: 1 }} /> : attachment.filename}
  </Link>
}
