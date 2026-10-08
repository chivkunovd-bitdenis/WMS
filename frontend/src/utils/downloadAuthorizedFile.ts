import { apiUrl } from '../api'
import { readApiErrorMessage } from './readApiErrorMessage'

// Файлы, которые отдаёт сервер только по токену (XLSX отгрузки и пропуска), нельзя
// открыть обычной ссылкой: браузер не приложит заголовок авторизации. Поэтому файл
// читается через fetch и сохраняется через временную ссылку. Имя берём из
// Content-Disposition (в WMS сервер сам кладёт туда готовое имя на русском).

/** Имя файла из Content-Disposition: сначала filename*=UTF-8''…, затем filename="…". */
export function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback
  const encoded = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim())
    } catch {
      /* битая кодировка — пробуем простое имя ниже */
    }
  }
  const plain = header.match(/filename="([^"]+)"/i)
  return plain ? plain[1] : fallback
}

export type AuthHeadersSource = Record<string, string> | ((token: string) => Record<string, string>)

export function resolveAuthHeaders(source: AuthHeadersSource, token: string): Record<string, string> {
  return typeof source === 'function' ? source(token) : source
}

export type DownloadedFile = {
  filename: string
  /** Значение заголовка x-wms-warning-code, если сервер предупредил о чём-то при выгрузке. */
  warningCode: string | null
}

/**
 * Скачивает файл по пути API (например, `/operations/…/pass.xlsx`).
 *
 * Бросает Error с понятным текстом сервера, если ответ не успешен — вызывающий
 * показывает его на месте. `isCurrent` защищает от устаревшего ответа: если пользователь
 * успел закрыть окно или повторить запрос, файл не сохраняется, а функция возвращает null.
 */
export async function downloadAuthorizedFile(
  path: string,
  headers: Record<string, string>,
  fallbackName: string,
  isCurrent: () => boolean = () => true,
): Promise<DownloadedFile | null> {
  const response = await fetch(apiUrl(path), { headers })
  if (!isCurrent()) return null
  if (!response.ok) {
    throw new Error(await readApiErrorMessage(response))
  }
  const warningCode = response.headers.get('x-wms-warning-code')
  const filename = filenameFromContentDisposition(response.headers.get('content-disposition'), fallbackName)
  const blob = await response.blob()
  if (!isCurrent()) return null
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
  return { filename, warningCode }
}
