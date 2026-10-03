import type { Marketplace } from './products'

/**
 * Режим макета, который читает подставной сервер в момент запроса.
 * «Сейчас» — ответы такие, какие сегодня отдаёт бэкенд; «Предложение» — ответы
 * там, где предложение требует от бэкенда новое поле (например, код для печати
 * строки возврата именно по площадке документа).
 */
export const runtime: { mode: 'now' | 'proposal'; doc: Marketplace } = {
  mode: 'proposal',
  doc: 'wb',
}

function base64Url(text: string): string {
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/**
 * Токен-болванка. Приёмка читает из токена «кто и в какой организации» (хранит
 * черновик в localStorage по ключу пользователя), поэтому ему нужна не пустая
 * строка, а строка вида JWT. Это выдуманные данные: сервера, который бы такой
 * токен проверял, в макете нет.
 */
export const MOCK_TOKEN = [
  base64Url(JSON.stringify({ alg: 'none', typ: 'JWT' })),
  base64Url(JSON.stringify({ sub: 'user-649', tenant_id: 'tenant-649' })),
  'mockup',
].join('.')
