/**
 * Идентификатор запроса, который работает на обычном HTTP.
 *
 * ⛔ `crypto.randomUUID()` напрямую вызывать нельзя. Браузер отдаёт его только в
 * защищённом контексте — по HTTPS или на localhost. Прод открыт по адресу вида
 * `http://194.87.96.144:8088`, и там этого метода просто нет: вызов падает с
 * TypeError и уносит с собой весь обработчик.
 *
 * Ровно это останавливало склад 02.09.2026. На пересчёте товар, который лежит не
 * в том коробе, где числится, идёт веткой находки — а она начиналась с
 * `crypto.randomUUID()`. Обработчик падал молча: ни счёта, ни сообщения, ни
 * запроса на сервер. Оператор видел «часть товара сканируется, часть нет» и не
 * мог понять закономерности, потому что закономерность была не в товаре, а в
 * том, совпало ли его место с учётом.
 *
 * `crypto.getRandomValues` доступен и на HTTP, поэтому случайность настоящая;
 * `Math.random` остаётся последней подпоркой для совсем древних сред.
 */
export function randomId(): string {
  const native = globalThis.crypto?.randomUUID
  if (typeof native === 'function') return native.call(globalThis.crypto)

  const bytes = new Uint8Array(16)
  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(bytes)
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256)
  }
  // Версия 4 и вариант 1 — чтобы значение оставалось законным UUID: сервер
  // хранит его как uuid, и мусор он не примет.
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
