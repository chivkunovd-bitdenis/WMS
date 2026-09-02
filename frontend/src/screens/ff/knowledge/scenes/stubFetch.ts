/**
 * Подставной сервер для живых макетов базы знаний.
 *
 * Экраны портала ходят на бэкенд обычным `fetch` через `apiUrl()`. Чтобы
 * показать такой экран без сервера и без входа в систему, мы подменяем
 * глобальный `fetch` таблицей «шаблон адреса → ответ». Всё, что не описано в
 * таблице, отдаётся пустым успешным ответом, а не ошибкой: экран должен
 * дорисоваться до конца, а не встать на первом же незнакомом запросе.
 */

export type StubHandler = (
  match: RegExpMatchArray,
  init: RequestInit | undefined,
) => unknown | Promise<unknown>

export type StubRoute = {
  /** HTTP-метод; `*` — любой. */
  method?: string
  /** Регулярка по пути без префикса `/api`. */
  path: RegExp
  handler: StubHandler
}

function pathOf(input: RequestInfo | URL): string {
  const raw =
    typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  const withoutOrigin = raw.replace(/^https?:\/\/[^/]+/, '')
  return withoutOrigin.replace(/^\/api/, '')
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body ?? null), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

/**
 * Ставит подставной `fetch` на время жизни макета и возвращает функцию отката.
 * Откат обязателен: макет живёт внутри портала, и оставленная подмена сломала бы
 * настоящие экраны, открытые после него.
 */
export function installStubFetch(routes: StubRoute[]): () => void {
  const original = window.fetch
  const stub: typeof window.fetch = async (input, init) => {
    const path = pathOf(input)
    const method = (init?.method ?? 'GET').toUpperCase()
    for (const route of routes) {
      const wanted = (route.method ?? 'GET').toUpperCase()
      if (wanted !== '*' && wanted !== method) continue
      const match = path.match(route.path)
      if (!match) continue
      return jsonResponse(await route.handler(match, init))
    }
    // Незнакомый запрос: пустой успешный ответ, чтобы экран не показывал ошибку.
    return jsonResponse(null)
  }
  window.fetch = stub
  return () => {
    window.fetch = original
  }
}
