/**
 * Печатная форма счёта на оплату.
 *
 * Раньше счёт печатался голым HTML: заголовок, три подзаголовка и таблица без
 * рамок — документ, который стыдно отправить плательщику. Здесь собран обычный
 * счёт на оплату: банковские реквизиты получателя сверху, позиции с широкой
 * колонкой услуги и узкой суммой справа, итог цифрами и прописью, места под
 * подписи и печать.
 *
 * Форма одна на все места, откуда счёт печатается: расходиться им нельзя —
 * плательщик получает один и тот же документ независимо от того, из какого
 * окна его напечатали.
 */

export type PrintProfile = Record<string, string | null | undefined>

export type PrintLine = {
  description: string
  /** Количество и цена есть не у всякого счёта: ручные строки идут одной суммой. */
  quantity?: string | null
  unit?: string | null
  price?: string | null
  amount: string
}

export type PrintInvoice = {
  number: string
  dateLabel: string
  periodLabel: string
  supplierName: string
  payerName: string
  supplier: PrintProfile
  payer: PrintProfile
  lines: PrintLine[]
  total: string
  totalKopecks: number
}

const ONES = [
  '', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять',
  'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать',
  'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать',
]
const ONES_FEMALE = ['', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
const TENS = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
const HUNDREDS = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']

function plural(value: number, one: string, few: string, many: string): string {
  const mod100 = value % 100
  if (mod100 >= 11 && mod100 <= 14) return many
  const mod10 = value % 10
  if (mod10 === 1) return one
  if (mod10 >= 2 && mod10 <= 4) return few
  return many
}

function tripletInWords(value: number, female: boolean): string {
  const parts: string[] = []
  const hundreds = Math.floor(value / 100)
  const rest = value % 100
  if (hundreds) parts.push(HUNDREDS[hundreds] ?? '')
  if (rest < 20) {
    const word = female && rest < 10 ? ONES_FEMALE[rest] : ONES[rest]
    if (word) parts.push(word)
  } else {
    const tens = Math.floor(rest / 10)
    const ones = rest % 10
    if (tens) parts.push(TENS[tens] ?? '')
    if (ones) parts.push((female ? ONES_FEMALE[ones] : ONES[ones]) ?? '')
  }
  return parts.filter(Boolean).join(' ')
}

/** Сумма прописью: без неё счёт на оплату не счёт. */
export function amountInWords(totalKopecks: number): string {
  const safe = Math.max(0, Math.round(totalKopecks))
  const rubles = Math.floor(safe / 100)
  const kopecks = safe % 100
  if (rubles === 0) {
    return `Ноль рублей ${String(kopecks).padStart(2, '0')} копеек`
  }
  const groups: Array<{ value: number; female: boolean; forms: [string, string, string] }> = [
    { value: Math.floor(rubles / 1_000_000_000) % 1000, female: false, forms: ['миллиард', 'миллиарда', 'миллиардов'] },
    { value: Math.floor(rubles / 1_000_000) % 1000, female: false, forms: ['миллион', 'миллиона', 'миллионов'] },
    { value: Math.floor(rubles / 1000) % 1000, female: true, forms: ['тысяча', 'тысячи', 'тысяч'] },
    { value: rubles % 1000, female: false, forms: ['', '', ''] },
  ]
  const words: string[] = []
  for (const group of groups) {
    if (!group.value) continue
    words.push(tripletInWords(group.value, group.female))
    if (group.forms[0]) words.push(plural(group.value, group.forms[0], group.forms[1], group.forms[2]))
  }
  const phrase = words.filter(Boolean).join(' ')
  const capitalized = phrase.charAt(0).toUpperCase() + phrase.slice(1)
  return (
    `${capitalized} ${plural(rubles, 'рубль', 'рубля', 'рублей')} ` +
    `${String(kopecks).padStart(2, '0')} ${plural(kopecks, 'копейка', 'копейки', 'копеек')}`
  )
}

export function escapeHtml(value: unknown): string {
  const entities: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }
  return String(value ?? '').replace(/[&<>"']/g, (character) => entities[character] ?? character)
}

function profileValue(profile: PrintProfile, key: string): string {
  const value = profile[key]
  return value ? String(value) : ''
}

/** Сторона счёта: наименование, под ним ИНН и КПП. Банковское — в шапке. */
function profileLines(profile: PrintProfile, fallbackName: string): string {
  const name = profileValue(profile, 'legal_name') || fallbackName
  const tax = [
    profileValue(profile, 'inn') ? `ИНН ${profileValue(profile, 'inn')}` : '',
    profileValue(profile, 'kpp') ? `КПП ${profileValue(profile, 'kpp')}` : '',
  ]
    .filter(Boolean)
    .join(', ')
  return [escapeHtml(name), tax ? escapeHtml(tax) : ''].filter(Boolean).join('<br>')
}

const STYLES = `
  @page { size: A4; margin: 14mm; }
  body { font-family: Arial, Helvetica, sans-serif; font-size: 12px; line-height: 1.45; color: #111; margin: 0; }
  .doc { max-width: 182mm; margin: 0 auto; }
  table { border-collapse: collapse; width: 100%; }
  .bank td { border: 1px solid #111; padding: 4px 6px; vertical-align: top; }
  .bank .label { width: 26%; color: #333; }
  .bank .narrow { width: 14%; }
  h1 { font-size: 20px; margin: 0 0 6px; }
  .rule { border-bottom: 2px solid #111; margin-bottom: 14px; }
  .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #555; margin-bottom: 4px; }
  .parties { display: flex; gap: 24px; margin: 14px 0 6px; }
  .parties .party { flex: 1; }
  .party .role { font-weight: 700; margin-bottom: 2px; }
  .period { margin: 8px 0 0; color: #333; }
  .items { margin-top: 14px; }
  .items th, .items td { border: 1px solid #111; padding: 5px 6px; }
  .items th { background: #f2f2f2; text-align: left; font-weight: 700; }
  .items col.num { width: 6%; }
  .items col.qty { width: 9%; }
  .items col.unit { width: 10%; }
  .items col.price { width: 13%; }
  .items col.sum { width: 15%; }
  .items td.right, .items th.right { text-align: right; white-space: nowrap; }
  .totals { margin-top: 10px; text-align: right; }
  .totals .grand { font-size: 15px; font-weight: 700; }
  .words { margin-top: 10px; }
  .sign { margin-top: 34px; display: flex; gap: 40px; }
  .sign div { flex: 1; border-top: 1px solid #111; padding-top: 4px; color: #333; }
  .stamp { margin-top: 26px; color: #777; }
`

export function buildInvoicePrintHtml(invoice: PrintInvoice): string {
  const withQuantity = invoice.lines.some((line) => line.quantity || line.price)
  const head = withQuantity
    ? `<colgroup><col class="num"><col><col class="qty"><col class="unit"><col class="price"><col class="sum"></colgroup>
       <thead><tr><th>№</th><th>Наименование услуги</th><th class="right">Кол-во</th><th>Ед.</th><th class="right">Цена</th><th class="right">Сумма</th></tr></thead>`
    : `<colgroup><col class="num"><col><col class="sum"></colgroup>
       <thead><tr><th>№</th><th>Наименование услуги</th><th class="right">Сумма</th></tr></thead>`
  const body = invoice.lines
    .map((line, index) => {
      const cells = withQuantity
        ? `<td class="right">${escapeHtml(line.quantity ?? '')}</td><td>${escapeHtml(line.unit ?? '')}</td><td class="right">${escapeHtml(line.price ?? '')}</td>`
        : ''
      return `<tr><td>${index + 1}</td><td>${escapeHtml(line.description)}</td>${cells}<td class="right">${escapeHtml(line.amount)}</td></tr>`
    })
    .join('')
  const bank = `
    <table class="bank">
      <tr>
        <td class="label">Получатель</td>
        <td colspan="3">${escapeHtml(profileValue(invoice.supplier, 'legal_name') || invoice.supplierName)}</td>
      </tr>
      <tr>
        <td class="label">ИНН / КПП</td>
        <td>${escapeHtml([profileValue(invoice.supplier, 'inn'), profileValue(invoice.supplier, 'kpp')].filter(Boolean).join(' / '))}</td>
        <td class="label narrow">Сч. №</td>
        <td>${escapeHtml(profileValue(invoice.supplier, 'settlement_account'))}</td>
      </tr>
      <tr>
        <td class="label">Банк получателя</td>
        <td>${escapeHtml(profileValue(invoice.supplier, 'bank_name'))}</td>
        <td class="label narrow">БИК</td>
        <td>${escapeHtml(profileValue(invoice.supplier, 'bik'))}</td>
      </tr>
      <tr>
        <td class="label">Корр. счёт</td>
        <td colspan="3">${escapeHtml(profileValue(invoice.supplier, 'correspondent_account'))}</td>
      </tr>
    </table>`
  // Заголовок идёт первым, банковские реквизиты — под ним. В типовой форме 1С
  // блок с БИК стоит выше слова «Счёт», но владелец читает документ сверху вниз
  // и хочет сначала понять, что перед ним за бумага.
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Счёт ${escapeHtml(invoice.number)}</title><style>${STYLES}</style></head><body><div class="doc">
    <h1>Счёт на оплату № ${escapeHtml(invoice.number)} ${escapeHtml(invoice.dateLabel)}</h1>
    <div class="rule"></div>
    <div class="section-title">Реквизиты для оплаты</div>
    ${bank}
    <div class="parties">
      <div class="party"><div class="role">Исполнитель</div>${profileLines(invoice.supplier, invoice.supplierName)}</div>
      <div class="party"><div class="role">Плательщик</div>${profileLines(invoice.payer, invoice.payerName)}</div>
    </div>
    <div class="period">Период оказания услуг: ${escapeHtml(invoice.periodLabel)}</div>
    <table class="items">${head}<tbody>${body}</tbody></table>
    <div class="totals">
      <div>Итого: ${escapeHtml(invoice.total)}</div>
      <div>Без налога (НДС)</div>
      <div class="grand">Всего к оплате: ${escapeHtml(invoice.total)}</div>
    </div>
    <div class="words">Всего наименований ${invoice.lines.length}, на сумму ${escapeHtml(invoice.total)}<br><strong>${escapeHtml(amountInWords(invoice.totalKopecks))}</strong></div>
    <div class="sign"><div>Руководитель</div><div>Бухгалтер</div></div>
    <div class="stamp">М.П.</div>
  </div></body></html>`
}
