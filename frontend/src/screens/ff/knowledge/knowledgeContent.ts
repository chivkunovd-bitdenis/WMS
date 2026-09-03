// Загрузка статей «Базы знаний» из репозитория.
//
// Сервера у раздела нет и не планируется: статьи — это markdown-файлы в
// `frontend/src/content/knowledge`, которые команда правит через git и катит
// вместе с фронтом. Плюс такого решения в том, что статья всегда соответствует
// той версии интерфейса, которая сейчас на экране, а не отстаёт от неё.

import { blocksToPlainText, parseMarkdown, splitFrontMatter } from './markdown'
import type { Block } from './markdown'

export type KnowledgeArticle = {
  slug: string
  order: number
  title: string
  summary: string
  blocks: Block[]
  /** Плоский текст статьи как он написан — из него режем подсказку под названием. */
  plainText: string
  /** Тот же текст в нижнем регистре — по нему ищем, чтобы регистр не мешал. */
  searchText: string
}

const rawArticles = import.meta.glob('../../../content/knowledge/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

// Иллюстрации лежат рядом со статьями. Прогоняем их через сборщик, чтобы в
// продовой сборке получить настоящие адреса файлов с хэшем, а не путь из текста.
const rawImages = import.meta.glob('../../../content/knowledge/images/*.{svg,png,jpg,jpeg}', {
  query: '?url',
  import: 'default',
  eager: true,
}) as Record<string, string>

const imagesByName = new Map<string, string>(
  Object.entries(rawImages).map(([path, url]) => [path.split('/').pop() ?? path, url]),
)

/** `01-priemka.md` → slug `priemka`, порядок 1. */
function fileIdentity(path: string): { slug: string; order: number } {
  const name = (path.split('/').pop() ?? path).replace(/\.md$/, '')
  const numbered = /^(\d+)-(.+)$/.exec(name)
  if (!numbered) return { slug: name, order: Number.MAX_SAFE_INTEGER }
  return { slug: numbered[2] ?? name, order: Number(numbered[1]) }
}

function resolveImages(blocks: Block[]): Block[] {
  return blocks.map((block) => {
    if (block.kind !== 'image') return block
    const name = block.src.split('/').pop() ?? block.src
    return { ...block, src: imagesByName.get(name) ?? block.src }
  })
}

function buildArticle(path: string, raw: string): KnowledgeArticle {
  const { slug, order } = fileIdentity(path)
  const { meta, body } = splitFrontMatter(raw)
  const blocks = resolveImages(parseMarkdown(body))
  const plainText = [meta.title ?? '', meta.summary ?? '', blocksToPlainText(blocks)].join('\n')
  return {
    slug,
    order,
    title: meta.title ?? slug,
    summary: meta.summary ?? '',
    blocks,
    plainText,
    searchText: plainText.toLowerCase(),
  }
}

export const knowledgeArticles: KnowledgeArticle[] = Object.entries(rawArticles)
  .map(([path, raw]) => buildArticle(path, raw))
  .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title, 'ru'))

export function findArticle(slug: string | undefined): KnowledgeArticle | undefined {
  if (!slug) return undefined
  return knowledgeArticles.find((article) => article.slug === slug)
}

/**
 * Кусок текста вокруг найденного слова — чтобы в списке было видно, за что
 * статья зацепилась, а не только её название.
 */
export function searchSnippet(article: KnowledgeArticle, query: string): string | null {
  const needle = query.trim().toLowerCase()
  if (!needle) return null
  const at = article.searchText.indexOf(needle)
  if (at === -1) return null
  // Ищем по нижнему регистру, а показываем исходный текст: подсказка под
  // названием статьи должна читаться как обычное предложение.
  const plain = article.plainText
  const from = Math.max(0, at - 40)
  const to = Math.min(plain.length, at + needle.length + 60)
  const head = from > 0 ? '…' : ''
  const tail = to < plain.length ? '…' : ''
  return `${head}${plain.slice(from, to).replace(/\n/g, ' ').trim()}${tail}`
}

export function filterArticles(query: string): KnowledgeArticle[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return knowledgeArticles
  // Несколько слов через пробел ищем как «и»: оператор набирает «короб приёмка»
  // и ждёт статью, где встречаются оба слова, а не список всего подряд.
  const words = needle.split(/\s+/).filter(Boolean)
  return knowledgeArticles.filter((article) =>
    words.every((word) => article.searchText.includes(word)),
  )
}
