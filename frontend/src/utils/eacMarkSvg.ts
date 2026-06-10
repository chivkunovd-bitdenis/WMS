/** EAC mark for product thermal labels (stacked letters in frame, as on WB-style 58×40). */
export const EAC_MARK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 56" aria-hidden="true">
  <rect x="1" y="1" width="42" height="54" fill="none" stroke="#111" stroke-width="2"/>
  <text x="22" y="18" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="700" fill="#111">E</text>
  <text x="22" y="34" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="700" fill="#111">A</text>
  <text x="22" y="50" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="700" fill="#111">C</text>
</svg>`

export const EAC_MARK_DATA_URL = `data:image/svg+xml,${encodeURIComponent(EAC_MARK_SVG)}`
