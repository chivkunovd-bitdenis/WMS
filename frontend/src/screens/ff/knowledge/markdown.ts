// Маленький разборщик markdown под «Базу знаний».
//
// Внешняя библиотека тут не нужна и вредна: статьи пишет своя же команда, набор
// разметки узкий и известен заранее, а рендерить мы хотим не «голый» HTML, а
// компоненты MUI — иначе статья выпадет из общего дизайна портала.
//
// Поддерживаем ровно то, чем пользуются авторы статей:
//   ## и ### заголовки, абзацы, списки «1.» и «- » (без вложенности),
//   цитату «> », простую таблицу через «|», картинку «![alt](src)»,
//   **жирный** и `код` внутри строки.
//
// Плюс одна своя строчка-директива, которой в markdown нет: `::scenario id::`
// вставляет в статью проигрыватель — живой макет, который сам идёт по шагам.
// Отдельный синтаксис нужен потому, что проигрыватель это не текст и не
// картинка: он должен попасть в статью так же просто, как картинка, но
// развернуться в компонент.

export type InlineNode =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'code'; text: string }

export type Block =
  | { kind: 'heading'; level: 2 | 3; text: string }
  | { kind: 'paragraph'; nodes: InlineNode[] }
  | { kind: 'list'; ordered: boolean; items: InlineNode[][] }
  | { kind: 'quote'; nodes: InlineNode[] }
  | { kind: 'table'; head: string[]; rows: string[][] }
  | { kind: 'image'; src: string; alt: string }
  | { kind: 'scenario'; id: string }

export type FrontMatter = { meta: Record<string, string>; body: string }

const IMAGE_RE = /^!\[([^\]]*)\]\(([^)]+)\)$/
const SCENARIO_RE = /^::scenario\s+([a-z0-9-]+)::$/
const ORDERED_RE = /^\d+\.\s+(.*)$/
const BULLET_RE = /^-\s+(.*)$/
const INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`)/g

/**
 * Отрезает «шапку» файла между двумя строками `---` и разбирает её как
 * простые пары `ключ: значение`. Заголовок и краткое описание статьи живут
 * именно там, чтобы список статей можно было собрать, не разбирая весь текст.
 */
export function splitFrontMatter(raw: string): FrontMatter {
  const text = raw.replace(/\r\n/g, '\n')
  if (!text.startsWith('---\n')) return { meta: {}, body: text }
  const end = text.indexOf('\n---', 3)
  if (end === -1) return { meta: {}, body: text }
  const head = text.slice(4, end)
  const body = text.slice(end + 4).replace(/^\n+/, '')
  const meta: Record<string, string> = {}
  for (const line of head.split('\n')) {
    const at = line.indexOf(':')
    if (at === -1) continue
    const key = line.slice(0, at).trim()
    if (!key) continue
    meta[key] = line.slice(at + 1).trim()
  }
  return { meta, body }
}

/** Разбирает одну строку на куски: обычный текст, **жирный** и `код`. */
export function parseInline(text: string): InlineNode[] {
  const out: InlineNode[] = []
  let last = 0
  for (const match of text.matchAll(INLINE_RE)) {
    const start = match.index ?? 0
    if (start > last) out.push({ kind: 'text', text: text.slice(last, start) })
    const token = match[0]
    if (token.startsWith('**')) out.push({ kind: 'bold', text: token.slice(2, -2) })
    else out.push({ kind: 'code', text: token.slice(1, -1) })
    last = start + token.length
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) })
  return out.length > 0 ? out : [{ kind: 'text', text: '' }]
}

function isTableDivider(line: string | undefined): boolean {
  const trimmed = (line ?? '').trim()
  if (!trimmed.startsWith('|') || !trimmed.includes('-')) return false
  return /^\|[\s:|-]+\|$/.test(trimmed)
}

function tableCells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((cell) => cell.trim())
}

export function parseMarkdown(body: string): Block[] {
  const lines = body.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let paragraph: string[] = []

  const flush = () => {
    if (paragraph.length === 0) return
    blocks.push({ kind: 'paragraph', nodes: parseInline(paragraph.join(' ').trim()) })
    paragraph = []
  }

  for (let i = 0; i < lines.length; i += 1) {
    const line = (lines[i] ?? '').trim()

    if (!line) {
      flush()
      continue
    }

    const scenario = SCENARIO_RE.exec(line)
    if (scenario) {
      flush()
      blocks.push({ kind: 'scenario', id: scenario[1] ?? '' })
      continue
    }

    const image = IMAGE_RE.exec(line)
    if (image) {
      flush()
      blocks.push({ kind: 'image', alt: image[1] ?? '', src: image[2] ?? '' })
      continue
    }

    if (line.startsWith('### ')) {
      flush()
      blocks.push({ kind: 'heading', level: 3, text: line.slice(4).trim() })
      continue
    }

    if (line.startsWith('## ')) {
      flush()
      blocks.push({ kind: 'heading', level: 2, text: line.slice(3).trim() })
      continue
    }

    if (line.startsWith('>')) {
      flush()
      const parts: string[] = []
      while (i < lines.length && (lines[i] ?? '').trim().startsWith('>')) {
        parts.push(
          (lines[i] ?? '')
            .trim()
            .replace(/^>\s?/, '')
            .trim(),
        )
        i += 1
      }
      i -= 1
      blocks.push({ kind: 'quote', nodes: parseInline(parts.join(' ').trim()) })
      continue
    }

    if (line.startsWith('|') && isTableDivider(lines[i + 1])) {
      flush()
      const head = tableCells(line)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && (lines[i] ?? '').trim().startsWith('|')) {
        rows.push(tableCells(lines[i] ?? ''))
        i += 1
      }
      i -= 1
      blocks.push({ kind: 'table', head, rows })
      continue
    }

    const ordered = ORDERED_RE.test(line)
    const bullet = BULLET_RE.test(line)
    if (ordered || bullet) {
      flush()
      const pattern = ordered ? ORDERED_RE : BULLET_RE
      const items: InlineNode[][] = []
      // Пустая строка между пунктами не должна рвать список на два: авторы
      // ставят её по привычке, а читатель ждёт сплошную нумерацию.
      while (i < lines.length) {
        let probe = i
        while (probe < lines.length && !(lines[probe] ?? '').trim()) probe += 1
        const match = pattern.exec((lines[probe] ?? '').trim())
        if (!match) break
        items.push(parseInline((match[1] ?? '').trim()))
        i = probe + 1
      }
      i -= 1
      blocks.push({ kind: 'list', ordered, items })
      continue
    }

    paragraph.push(line)
  }

  flush()
  return blocks
}

function inlineText(nodes: InlineNode[]): string {
  return nodes.map((node) => node.text).join('')
}

/**
 * Плоский текст статьи — то, по чему ищет оператор. Собираем его из уже
 * разобранных блоков, а не из исходного файла: так в поиск не попадут звёздочки,
 * решётки и палки таблиц, из-за которых запрос «короб» мог бы не найтись.
 */
export function blocksToPlainText(blocks: Block[]): string {
  const parts: string[] = []
  for (const block of blocks) {
    if (block.kind === 'heading') parts.push(block.text)
    else if (block.kind === 'paragraph' || block.kind === 'quote') parts.push(inlineText(block.nodes))
    else if (block.kind === 'list') for (const item of block.items) parts.push(inlineText(item))
    else if (block.kind === 'table') {
      parts.push(block.head.join(' '))
      for (const row of block.rows) parts.push(row.join(' '))
    } else if (block.kind === 'image') parts.push(block.alt)
  }
  return parts.join('\n')
}
