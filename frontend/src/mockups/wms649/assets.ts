/**
 * WMS-649 · картинки, которые подставной сервер должен отдавать не JSON-ом.
 *
 * Подставной сервер базы знаний отвечает только JSON. Картинку QR заказа WB, которую
 * печатная лента скачивает по ссылке, отдаём здесь SVG-заглушкой — чтобы в
 * предпросмотре ленты на месте QR был квадрат, а не битая картинка.
 */
const QR_PLACEHOLDER = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">
  <rect width="240" height="240" fill="#fff"/>
  <rect x="20" y="20" width="200" height="200" fill="none" stroke="#111" stroke-width="10"/>
  <rect x="40" y="40" width="50" height="50" fill="#111"/>
  <rect x="150" y="40" width="50" height="50" fill="#111"/>
  <rect x="40" y="150" width="50" height="50" fill="#111"/>
  <rect x="110" y="110" width="30" height="30" fill="#111"/>
  <text x="120" y="228" font-family="Arial" font-size="16" text-anchor="middle" fill="#111">QR заказа (макет)</text>
</svg>`

export function installAssetFetch(): void {
  const previous = window.fetch
  window.fetch = async (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    if (/\/operations\/fbs-print-assets\/[^/?]+\/preview/.test(raw)) {
      return new Response(QR_PLACEHOLDER, { status: 200, headers: { 'Content-Type': 'image/svg+xml' } })
    }
    return previous(input, init)
  }
}
