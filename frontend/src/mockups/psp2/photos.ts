// Макет PSP-2: «фотографии» товаров нарисованы прямо здесь, как SVG в data-URI.
// Настоящих снимков у выдуманных карточек нет, а внешние адреса в статической
// сборке не открылись бы. Рисунок простой: фон и силуэт вида товара в его цвете.

export type PhotoKind = 'bedding' | 'sheet' | 'pillowcase' | 'duvet' | 'plaid' | 'bedspread' | 'cushion' | 'tshirt' | 'longsleeve'

function svg(body: string, background: string): string {
  const markup = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 160"><rect width="120" height="160" fill="${background}"/>${body}</svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`
}

function shade(hex: string, amount: number): string {
  const n = Number.parseInt(hex.slice(1), 16)
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)))
  const r = clamp(((n >> 16) & 255) + amount)
  const g = clamp(((n >> 8) & 255) + amount)
  const b = clamp((n & 255) + amount)
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`
}

export function productPhoto(kind: PhotoKind, color: string): string {
  const dark = shade(color, -28)
  const light = shade(color, 34)
  const bg = '#F4F1EC'
  switch (kind) {
    case 'bedding':
      return svg(
        `<rect x="18" y="52" width="84" height="22" rx="4" fill="${light}"/>` +
          `<rect x="14" y="72" width="92" height="26" rx="4" fill="${color}"/>` +
          `<rect x="10" y="96" width="100" height="30" rx="4" fill="${dark}"/>` +
          `<rect x="40" y="58" width="40" height="10" rx="2" fill="#ffffff" opacity=".55"/>`,
        bg,
      )
    case 'sheet':
      return svg(
        `<rect x="16" y="60" width="88" height="50" rx="6" fill="${color}"/>` +
          `<path d="M16 100 Q60 118 104 100 L104 110 Q60 126 16 110Z" fill="${dark}"/>`,
        bg,
      )
    case 'pillowcase':
      return svg(
        `<rect x="20" y="46" width="80" height="58" rx="12" fill="${color}"/>` +
          `<rect x="28" y="64" width="80" height="58" rx="12" fill="${dark}" opacity=".85"/>`,
        bg,
      )
    case 'duvet':
      return svg(
        `<rect x="14" y="40" width="92" height="80" rx="6" fill="${color}"/>` +
          `<path d="M14 80 H106 M60 40 V120" stroke="${dark}" stroke-width="2" opacity=".6"/>`,
        bg,
      )
    case 'plaid':
      return svg(
        `<rect x="16" y="44" width="88" height="72" rx="6" fill="${color}"/>` +
          `<path d="M16 62 H104 M16 80 H104 M16 98 H104 M38 44 V116 M60 44 V116 M82 44 V116" stroke="${dark}" stroke-width="3" opacity=".45"/>` +
          `<path d="M16 116 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10 l4 10 l4 -10" stroke="${dark}" stroke-width="2" fill="none"/>`,
        bg,
      )
    case 'bedspread':
      return svg(
        `<rect x="12" y="46" width="96" height="70" rx="8" fill="${color}"/>` +
          `<path d="M12 70 Q36 60 60 70 T108 70 M12 94 Q36 84 60 94 T108 94" stroke="${light}" stroke-width="3" fill="none"/>`,
        bg,
      )
    case 'cushion':
      return svg(
        `<path d="M26 50 Q60 40 94 50 Q104 80 94 110 Q60 120 26 110 Q16 80 26 50Z" fill="${color}"/>` +
          `<circle cx="60" cy="80" r="5" fill="${dark}"/>`,
        bg,
      )
    case 'longsleeve':
      return svg(
        `<path d="M42 34 L24 42 L10 104 L24 108 L34 64 L34 128 L86 128 L86 64 L96 108 L110 104 L96 42 L78 34 Q60 46 42 34Z" fill="${color}"/>` +
          `<path d="M42 34 Q60 46 78 34" stroke="${dark}" stroke-width="3" fill="none"/>`,
        bg,
      )
    case 'tshirt':
    default:
      return svg(
        `<path d="M42 36 L18 48 L26 70 L36 66 L36 128 L84 128 L84 66 L94 70 L102 48 L78 36 Q60 48 42 36Z" fill="${color}"/>` +
          `<path d="M42 36 Q60 48 78 36" stroke="${dark}" stroke-width="3" fill="none"/>`,
        bg,
      )
  }
}
