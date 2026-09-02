import { Fragment } from 'react'
import type { ReactNode } from 'react'
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'

import type { Block, InlineNode } from './markdown'

type Props = {
  blocks: Block[]
  /** Слова из строки поиска — подсвечиваем их в тексте статьи. */
  highlight?: string
}

function highlightText(text: string, words: string[], keyPrefix: string): ReactNode {
  if (words.length === 0 || !text) return text
  // Ищем сразу все слова запроса: оператор набрал «короб приёмка» — пусть
  // видит оба слова подсвеченными, а не бегает глазами по абзацу.
  const lower = text.toLowerCase()
  const hits: Array<{ from: number; to: number }> = []
  for (const word of words) {
    let at = lower.indexOf(word)
    while (at !== -1) {
      hits.push({ from: at, to: at + word.length })
      at = lower.indexOf(word, at + word.length)
    }
  }
  if (hits.length === 0) return text
  hits.sort((a, b) => a.from - b.from)

  const parts: ReactNode[] = []
  let cursor = 0
  hits.forEach((hit, index) => {
    if (hit.from < cursor) return
    if (hit.from > cursor) parts.push(text.slice(cursor, hit.from))
    parts.push(
      <Box
        key={`${keyPrefix}-mark-${index}`}
        component="mark"
        sx={{ bgcolor: 'warning.light', color: 'inherit', px: 0.25, borderRadius: 0.5 }}
      >
        {text.slice(hit.from, hit.to)}
      </Box>,
    )
    cursor = hit.to
  })
  if (cursor < text.length) parts.push(text.slice(cursor))
  return parts
}

function Inline({
  nodes,
  words,
  keyPrefix,
}: {
  nodes: InlineNode[]
  words: string[]
  keyPrefix: string
}) {
  return (
    <>
      {nodes.map((node, index) => {
        const key = `${keyPrefix}-${index}`
        const content = highlightText(node.text, words, key)
        if (node.kind === 'bold') {
          return (
            <Box key={key} component="strong" sx={{ fontWeight: 700 }}>
              {content}
            </Box>
          )
        }
        if (node.kind === 'code') {
          return (
            <Box
              key={key}
              component="code"
              sx={{
                px: 0.5,
                py: 0.15,
                borderRadius: 0.75,
                bgcolor: 'action.hover',
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                fontSize: '0.875em',
              }}
            >
              {content}
            </Box>
          )
        }
        return <Fragment key={key}>{content}</Fragment>
      })}
    </>
  )
}

export function MarkdownView({ blocks, highlight = '' }: Props) {
  const words = highlight
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter((word) => word.length > 1)

  return (
    <Box data-testid="knowledge-article-body" sx={{ maxWidth: 860 }}>
      {blocks.map((block, index) => {
        const key = `block-${index}`

        if (block.kind === 'heading') {
          return (
            <Typography
              key={key}
              variant={block.level === 2 ? 'h6' : 'subtitle1'}
              sx={{
                fontWeight: 700,
                mt: block.level === 2 ? 3.5 : 2.5,
                mb: 1,
                '&:first-of-type': { mt: 0 },
              }}
            >
              {highlightText(block.text, words, key)}
            </Typography>
          )
        }

        if (block.kind === 'paragraph') {
          return (
            <Typography key={key} variant="body1" sx={{ mb: 1.5, lineHeight: 1.65 }}>
              <Inline nodes={block.nodes} words={words} keyPrefix={key} />
            </Typography>
          )
        }

        if (block.kind === 'list') {
          return (
            <Box
              key={key}
              component={block.ordered ? 'ol' : 'ul'}
              sx={{ pl: 3, mt: 0, mb: 2, '& li': { mb: 0.85, lineHeight: 1.65 } }}
            >
              {block.items.map((item, itemIndex) => (
                <Typography key={`${key}-${itemIndex}`} component="li" variant="body1">
                  <Inline nodes={item} words={words} keyPrefix={`${key}-${itemIndex}`} />
                </Typography>
              ))}
            </Box>
          )
        }

        if (block.kind === 'quote') {
          return (
            <Box
              key={key}
              sx={{
                my: 2,
                px: 2,
                py: 1.5,
                borderLeft: '4px solid',
                borderColor: 'primary.main',
                bgcolor: 'action.hover',
                borderRadius: 1,
              }}
            >
              <Typography variant="body1" sx={{ lineHeight: 1.6 }}>
                <Inline nodes={block.nodes} words={words} keyPrefix={key} />
              </Typography>
            </Box>
          )
        }

        if (block.kind === 'table') {
          return (
            <TableContainer key={key} component={Paper} variant="outlined" sx={{ my: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {block.head.map((cell, cellIndex) => (
                      <TableCell key={`${key}-h-${cellIndex}`} sx={{ fontWeight: 700 }}>
                        {highlightText(cell, words, `${key}-h-${cellIndex}`)}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {block.rows.map((row, rowIndex) => (
                    <TableRow key={`${key}-r-${rowIndex}`}>
                      {row.map((cell, cellIndex) => (
                        <TableCell key={`${key}-r-${rowIndex}-${cellIndex}`}>
                          {highlightText(cell, words, `${key}-r-${rowIndex}-${cellIndex}`)}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )
        }

        return (
          <Box key={key} sx={{ my: 2.5 }}>
            <Box
              component="img"
              src={block.src}
              alt={block.alt}
              loading="lazy"
              sx={{
                display: 'block',
                width: '100%',
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1.5,
                bgcolor: 'background.paper',
              }}
            />
            {block.alt ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                {block.alt}
              </Typography>
            ) : null}
          </Box>
        )
      })}
    </Box>
  )
}
