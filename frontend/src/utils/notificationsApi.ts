import { apiUrl } from '../api'

export type NotificationRow = {
  id: string
  type: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  body: string
  link: string | null
  payload_json: Record<string, unknown> | null
  read_at: string | null
  created_at: string
}

export type NotificationListResponse = {
  items: NotificationRow[]
  unread_count: number
}

export async function fetchNotifications(
  token: string,
  params?: { unread?: boolean; limit?: number },
): Promise<NotificationListResponse> {
  const qs = new URLSearchParams()
  if (params?.unread === true) qs.set('unread', 'true')
  if (params?.unread === false) qs.set('unread', 'false')
  if (params?.limit != null) qs.set('limit', String(params.limit))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(apiUrl(`/operations/notifications${suffix}`), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    throw new Error(`notifications_list_failed:${res.status}`)
  }
  return res.json() as Promise<NotificationListResponse>
}

export async function markNotificationRead(
  token: string,
  notificationId: string,
): Promise<NotificationRow> {
  const res = await fetch(apiUrl(`/operations/notifications/${notificationId}/read`), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    throw new Error(`notification_read_failed:${res.status}`)
  }
  return res.json() as Promise<NotificationRow>
}

export async function markAllNotificationsRead(token: string): Promise<number> {
  const res = await fetch(apiUrl('/operations/notifications/read-all'), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    throw new Error(`notifications_read_all_failed:${res.status}`)
  }
  const body = (await res.json()) as { marked: number }
  return body.marked
}

export function resolveNotificationLink(
  link: string | null,
  portal: 'seller' | 'ff',
): string | null {
  if (!link) return null
  if (link.startsWith('/app/')) return link
  if (portal === 'seller') {
    return link.startsWith('/') ? `/app/seller${link}` : link
  }
  if (link.startsWith('/app/ff')) return link
  return link.startsWith('/') ? `/app/ff${link}` : link
}
