import { describe, expect, it } from 'vitest'

import { blocksToPlainText, parseInline, parseMarkdown, splitFrontMatter } from './markdown'

describe('splitFrontMatter', () => {
  it('вынимает заголовок и краткое описание статьи', () => {
    const { meta, body } = splitFrontMatter(
      '---\ntitle: Приёмка товара\nsummary: Как принять товар.\n---\n\n## Зачем\n\nТекст.\n',
    )
    expect(meta.title).toBe('Приёмка товара')
    expect(meta.summary).toBe('Как принять товар.')
    expect(body.startsWith('## Зачем')).toBe(true)
  })

  it('файл без шапки отдаёт как есть', () => {
    const { meta, body } = splitFrontMatter('## Просто заголовок\n')
    expect(meta).toEqual({})
    expect(body).toBe('## Просто заголовок\n')
  })
})

describe('parseInline', () => {
  it('разбирает жирный и код внутри строки', () => {
    expect(parseInline('нажмите **«Провести»** в поле `barcode`')).toEqual([
      { kind: 'text', text: 'нажмите ' },
      { kind: 'bold', text: '«Провести»' },
      { kind: 'text', text: ' в поле ' },
      { kind: 'code', text: 'barcode' },
    ])
  })

  it('строку без разметки не трогает', () => {
    expect(parseInline('обычный текст')).toEqual([{ kind: 'text', text: 'обычный текст' }])
  })
})

describe('parseMarkdown', () => {
  it('собирает заголовки, абзацы и цитату', () => {
    const blocks = parseMarkdown('## Зачем\n\nПервый абзац.\n\n> Важно помнить.\n')
    expect(blocks).toEqual([
      { kind: 'heading', level: 2, text: 'Зачем' },
      { kind: 'paragraph', nodes: [{ kind: 'text', text: 'Первый абзац.' }] },
      { kind: 'quote', nodes: [{ kind: 'text', text: 'Важно помнить.' }] },
    ])
  })

  it('нумерованный список не рвётся на части из-за пустых строк', () => {
    const blocks = parseMarkdown('1. Первый шаг\n\n2. Второй шаг\n\n3. Третий шаг\n')
    expect(blocks).toHaveLength(1)
    const list = blocks[0]
    expect(list?.kind).toBe('list')
    if (list?.kind !== 'list') throw new Error('ожидался список')
    expect(list.ordered).toBe(true)
    expect(list.items).toHaveLength(3)
    expect(list.items[2]).toEqual([{ kind: 'text', text: 'Третий шаг' }])
  })

  it('маркированный список читается отдельным блоком', () => {
    const blocks = parseMarkdown('Текст.\n\n- **Ошибка.** Что делать.\n- Вторая.\n')
    expect(blocks[0]?.kind).toBe('paragraph')
    const list = blocks[1]
    if (list?.kind !== 'list') throw new Error('ожидался список')
    expect(list.ordered).toBe(false)
    expect(list.items).toHaveLength(2)
    expect(list.items[0]?.[0]).toEqual({ kind: 'bold', text: 'Ошибка.' })
  })

  it('таблица разбирается на шапку и строки', () => {
    const blocks = parseMarkdown('| Услуга | Единица |\n|---|---|\n| Хранение | литр-день |\n')
    expect(blocks).toEqual([
      { kind: 'table', head: ['Услуга', 'Единица'], rows: [['Хранение', 'литр-день']] },
    ])
  })

  it('картинка становится отдельным блоком', () => {
    const blocks = parseMarkdown('![Экран приёмки](images/priemka.svg)\n')
    expect(blocks).toEqual([
      { kind: 'image', alt: 'Экран приёмки', src: 'images/priemka.svg' },
    ])
  })

  it('соседние строки абзаца склеиваются в один блок', () => {
    const blocks = parseMarkdown('Первая строка\nвторая строка.\n')
    expect(blocks).toEqual([
      { kind: 'paragraph', nodes: [{ kind: 'text', text: 'Первая строка вторая строка.' }] },
    ])
  })
})

describe('blocksToPlainText', () => {
  it('отдаёт текст без разметки — по нему ищет оператор', () => {
    const blocks = parseMarkdown('## Короба\n\nНажмите **«Наполнить»**.\n\n- Пункт про `КИЗ`\n')
    expect(blocksToPlainText(blocks)).toBe('Короба\nНажмите «Наполнить».\nПункт про КИЗ')
  })
})
