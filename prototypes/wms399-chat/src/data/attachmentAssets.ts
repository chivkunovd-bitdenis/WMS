const b64 = (s: string) => `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(s)))}`

const paletteShort = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <defs>
    <linearGradient id="bg" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#e2e8f0"/>
      <stop offset="1" stop-color="#94a3b8"/>
    </linearGradient>
    <linearGradient id="wood" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#c69364"/>
      <stop offset="1" stop-color="#8b5a2b"/>
    </linearGradient>
    <linearGradient id="carton" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#d6a06a"/>
      <stop offset="1" stop-color="#a8794a"/>
    </linearGradient>
  </defs>
  <rect width="640" height="480" fill="url(#bg)"/>
  <g opacity="0.5">
    <rect x="0" y="380" width="640" height="100" fill="#475569"/>
    <line x1="0" y1="380" x2="640" y2="380" stroke="#334155" stroke-width="2"/>
  </g>
  <!-- pallet -->
  <g transform="translate(90,300)">
    <rect x="0" y="60" width="460" height="18" fill="url(#wood)"/>
    <rect x="10" y="80" width="60" height="24" fill="url(#wood)"/>
    <rect x="200" y="80" width="60" height="24" fill="url(#wood)"/>
    <rect x="390" y="80" width="60" height="24" fill="url(#wood)"/>
  </g>
  <!-- cartons -->
  <g>
    <rect x="110" y="180" width="110" height="120" fill="url(#carton)" stroke="#5b3720" stroke-width="2"/>
    <rect x="240" y="180" width="110" height="120" fill="url(#carton)" stroke="#5b3720" stroke-width="2"/>
    <!-- missing spot -->
    <rect x="370" y="180" width="110" height="120" fill="none" stroke="#dc2626" stroke-width="4" stroke-dasharray="8 6"/>
    <text x="425" y="245" text-anchor="middle" font-family="Inter, sans-serif" font-size="26" font-weight="800" fill="#dc2626">−5</text>
    <text x="425" y="275" text-anchor="middle" font-family="Inter, sans-serif" font-size="14" font-weight="600" fill="#dc2626">недовоз</text>
  </g>
  <g font-family="Inter, sans-serif" fill="#0f172a">
    <rect x="20" y="20" width="220" height="52" fill="#ffffff" opacity="0.9" rx="8"/>
    <text x="34" y="46" font-size="16" font-weight="700">Приёмка IN-2926</text>
    <text x="34" y="66" font-size="13" fill="#475569" font-weight="600">Ловиана · SKU-88213 · паллет 4/4</text>
  </g>
</svg>`

const damagedCarton = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <rect width="640" height="480" fill="#f1f5f9"/>
  <g transform="translate(120,110)">
    <polygon points="0,80 200,20 400,80 400,300 200,360 0,300" fill="#d6a06a" stroke="#5b3720" stroke-width="2"/>
    <polygon points="0,80 200,140 400,80" fill="none" stroke="#5b3720" stroke-width="2"/>
    <line x1="200" y1="140" x2="200" y2="360" stroke="#5b3720" stroke-width="2"/>
    <!-- tear -->
    <polyline points="60,120 120,150 90,200 160,220 130,270" stroke="#7f1d1d" stroke-width="4" fill="none"/>
    <polygon points="60,120 120,150 90,200 160,220 130,270 60,270" fill="#fecaca" stroke="#7f1d1d" stroke-width="2"/>
    <text x="90" y="200" font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#7f1d1d">повреждение</text>
  </g>
  <g font-family="Inter, sans-serif" fill="#0f172a">
    <rect x="20" y="20" width="260" height="52" fill="#ffffff" opacity="0.9" rx="8"/>
    <text x="34" y="46" font-size="16" font-weight="700">Короб #04, паллет 2</text>
    <text x="34" y="66" font-size="13" fill="#475569" font-weight="600">SKU-99010 · плёнка порвана, содержимое цело</text>
  </g>
</svg>`

const shelfLabel = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <rect width="640" height="480" fill="#f8fafc"/>
  <g transform="translate(90,110)">
    <rect x="0" y="0" width="460" height="260" fill="#ffffff" stroke="#0f172a" stroke-width="2"/>
    <text x="230" y="46" text-anchor="middle" font-family="Inter, sans-serif" font-size="24" font-weight="800" fill="#0f172a">A-04-12-3</text>
    <text x="230" y="70" text-anchor="middle" font-family="Inter, sans-serif" font-size="13" font-weight="600" fill="#475569">Хамовники · зона A · стеллаж 04</text>
    <g transform="translate(70,100)">
      ${Array.from({ length: 40 })
        .map(
          (_, i) =>
            `<rect x="${i * 8}" y="0" width="${i % 3 === 0 ? 2 : i % 2 === 0 ? 3 : 4}" height="90" fill="#0f172a"/>`,
        )
        .join('')}
    </g>
    <text x="230" y="230" text-anchor="middle" font-family="ui-monospace, monospace" font-size="18" font-weight="700" fill="#0f172a">88213 · A0412-3</text>
  </g>
</svg>`

const kizLabel = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <rect width="640" height="480" fill="#0f172a"/>
  <g transform="translate(140,90)">
    <rect x="0" y="0" width="360" height="300" fill="#f8fafc" rx="12"/>
    <text x="180" y="46" text-anchor="middle" font-family="Inter, sans-serif" font-size="22" font-weight="800" fill="#0f172a">Честный знак</text>
    <text x="180" y="70" text-anchor="middle" font-family="Inter, sans-serif" font-size="13" fill="#475569">DataMatrix · 44 знака</text>
    <g transform="translate(120,90)">
      ${Array.from({ length: 20 })
        .map((_, y) =>
          Array.from({ length: 20 })
            .map((_, x) => {
              const on = (x * 7 + y * 3 + (x ^ y)) % 3 === 0
              return on ? `<rect x="${x * 6}" y="${y * 6}" width="6" height="6" fill="#0f172a"/>` : ''
            })
            .join(''),
        )
        .join('')}
    </g>
    <text x="180" y="260" text-anchor="middle" font-family="ui-monospace, monospace" font-size="13" font-weight="700" fill="#0f172a">0104607...9021×VF7Z</text>
  </g>
</svg>`

const shippingLabel = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <rect width="640" height="480" fill="#f1f5f9"/>
  <g transform="translate(60,60)">
    <rect x="0" y="0" width="520" height="360" fill="#ffffff" stroke="#0f172a" stroke-width="2"/>
    <text x="20" y="36" font-family="Inter, sans-serif" font-size="18" font-weight="800" fill="#0f172a">Wildberries · FBS</text>
    <text x="20" y="60" font-family="Inter, sans-serif" font-size="13" font-weight="600" fill="#475569">Партия F-880 · Хамовники → СЦ Внуково</text>
    <line x1="20" y1="80" x2="500" y2="80" stroke="#e2e8f0" stroke-width="1"/>
    <text x="20" y="110" font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#0f172a">Заказ: 32117-4419</text>
    <text x="20" y="132" font-family="Inter, sans-serif" font-size="13" font-weight="600" fill="#334155">SKU-77104 · 2 шт</text>
    <text x="20" y="152" font-family="Inter, sans-serif" font-size="13" font-weight="600" fill="#334155">SKU-77022 · 1 шт</text>
    <g transform="translate(20,180)">
      ${Array.from({ length: 60 })
        .map(
          (_, i) =>
            `<rect x="${i * 8}" y="0" width="${i % 4 === 0 ? 2 : i % 3 === 0 ? 3 : 4}" height="80" fill="#0f172a"/>`,
        )
        .join('')}
    </g>
    <text x="20" y="290" font-family="ui-monospace, monospace" font-size="14" font-weight="700" fill="#0f172a">88 042 991 04471</text>
    <text x="380" y="290" font-family="Inter, sans-serif" font-size="12" font-weight="600" fill="#475569">до 08.09 · 18:00</text>
  </g>
</svg>`

const shelfPhoto = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480">
  <defs>
    <linearGradient id="floor" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="#cbd5f5"/>
      <stop offset="1" stop-color="#64748b"/>
    </linearGradient>
  </defs>
  <rect width="640" height="480" fill="url(#floor)"/>
  <!-- floor line -->
  <rect x="0" y="360" width="640" height="120" fill="#334155"/>
  <!-- rack frame -->
  <g stroke="#0f172a" stroke-width="4" fill="none">
    <rect x="60" y="60" width="520" height="320"/>
    <line x1="60" y1="160" x2="580" y2="160"/>
    <line x1="60" y1="260" x2="580" y2="260"/>
    <line x1="160" y1="60" x2="160" y2="380"/>
    <line x1="320" y1="60" x2="320" y2="380"/>
    <line x1="480" y1="60" x2="480" y2="380"/>
  </g>
  <g>
    <rect x="72" y="72" width="80" height="80" fill="#f97316" stroke="#7c2d12" stroke-width="2"/>
    <rect x="172" y="72" width="80" height="80" fill="#f97316" stroke="#7c2d12" stroke-width="2"/>
    <rect x="272" y="72" width="40" height="80" fill="#f97316" stroke="#7c2d12" stroke-width="2"/>
    <rect x="332" y="72" width="140" height="80" fill="none" stroke="#dc2626" stroke-width="3" stroke-dasharray="6 4"/>
    <text x="402" y="120" text-anchor="middle" font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="#dc2626">пусто</text>

    <rect x="72" y="172" width="240" height="80" fill="#a78bfa" stroke="#4c1d95" stroke-width="2"/>
    <rect x="332" y="172" width="140" height="80" fill="#a78bfa" stroke="#4c1d95" stroke-width="2"/>
    <rect x="492" y="172" width="80" height="80" fill="#a78bfa" stroke="#4c1d95" stroke-width="2"/>

    <rect x="72" y="272" width="80" height="90" fill="#22d3ee" stroke="#0e7490" stroke-width="2"/>
    <rect x="172" y="272" width="140" height="90" fill="#22d3ee" stroke="#0e7490" stroke-width="2"/>
    <rect x="332" y="272" width="140" height="90" fill="#22d3ee" stroke="#0e7490" stroke-width="2"/>
    <rect x="492" y="272" width="80" height="90" fill="#22d3ee" stroke="#0e7490" stroke-width="2"/>
  </g>
  <g font-family="Inter, sans-serif" fill="#0f172a">
    <rect x="20" y="20" width="220" height="34" fill="#ffffff" opacity="0.9" rx="6"/>
    <text x="34" y="42" font-size="14" font-weight="700">Стеллаж A-04, полка 2</text>
  </g>
</svg>`

export type SyntheticImage = {
  id: string
  name: string
  mime: string
  width: number
  height: number
  size: number
  dataUri: string
}

export const IMAGES: Record<string, SyntheticImage> = {
  paletteShort: {
    id: 'img_pallet_short',
    name: 'palette-short-5sht.png',
    mime: 'image/png',
    width: 1280,
    height: 960,
    size: 486_913,
    dataUri: b64(paletteShort),
  },
  damagedCarton: {
    id: 'img_carton_damaged',
    name: 'carton-damaged.jpg',
    mime: 'image/jpeg',
    width: 1280,
    height: 960,
    size: 388_204,
    dataUri: b64(damagedCarton),
  },
  shelfLabel: {
    id: 'img_shelf_label',
    name: 'shelf-A0412-3.png',
    mime: 'image/png',
    width: 1280,
    height: 960,
    size: 214_557,
    dataUri: b64(shelfLabel),
  },
  kizLabel: {
    id: 'img_kiz',
    name: 'kiz-88213.png',
    mime: 'image/png',
    width: 1280,
    height: 960,
    size: 191_003,
    dataUri: b64(kizLabel),
  },
  shippingLabel: {
    id: 'img_ship_label',
    name: 'wb-fbs-label-F880.png',
    mime: 'image/png',
    width: 1280,
    height: 960,
    size: 267_887,
    dataUri: b64(shippingLabel),
  },
  shelfPhoto: {
    id: 'img_shelf_photo',
    name: 'shelf-A04-photo.jpg',
    mime: 'image/jpeg',
    width: 1280,
    height: 960,
    size: 512_004,
    dataUri: b64(shelfPhoto),
  },
}
