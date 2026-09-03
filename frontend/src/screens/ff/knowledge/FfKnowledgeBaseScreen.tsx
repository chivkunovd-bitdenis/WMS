import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  InputAdornment,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ArrowBackOutlinedIcon from '@mui/icons-material/ArrowBackOutlined'
import MenuBookOutlinedIcon from '@mui/icons-material/MenuBookOutlined'
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined'

import { MarkdownView } from './MarkdownView'
import { filterArticles, findArticle, knowledgeArticles, searchSnippet } from './knowledgeContent'

/**
 * «База знаний» — встроенные инструкции для сотрудников склада.
 *
 * Раздел намеренно сделан без сервера: статьи лежат в репозитории рядом с
 * кодом экранов, которые они описывают, и катятся вместе с фронтом. Значит,
 * инструкция не может «отстать» от интерфейса на один релиз — обе половины
 * едут одним коммитом.
 */
export function FfKnowledgeBaseScreen() {
  const navigate = useNavigate()
  const { slug } = useParams<{ slug: string }>()
  const [query, setQuery] = useState('')
  const readerRef = useRef<HTMLDivElement | null>(null)

  const found = useMemo(() => filterArticles(query), [query])
  const article = findArticle(slug)

  // Открыли другую статью — читаем её с начала, а не с середины предыдущей.
  useEffect(() => {
    readerRef.current?.scrollTo({ top: 0 })
    window.scrollTo({ top: 0 })
  }, [slug])

  const openArticle = (next: string) => {
    navigate(`/app/ff/knowledge/${next}`)
  }

  return (
    <Box sx={{ width: '100%', maxWidth: 'calc(100vw - 308px)', boxSizing: 'border-box' }}>
      <Typography variant="h5" gutterBottom>
        База знаний
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Инструкции по работе в системе: что делать на каждом участке склада, в каком порядке и что
        делать, если пошло не так.
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Paper
          variant="outlined"
          sx={{
            p: 1.5,
            width: { xs: '100%', md: 340 },
            flexShrink: 0,
            position: { md: 'sticky' },
            top: { md: 88 },
          }}
          data-testid="knowledge-sidebar"
        >
          <TextField
            fullWidth
            size="small"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Поиск по статьям"
            slotProps={{
              htmlInput: { 'data-testid': 'knowledge-search-input' },
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchOutlinedIcon fontSize="small" />
                  </InputAdornment>
                ),
              },
            }}
            data-testid="knowledge-search"
          />

          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, px: 0.5 }}>
            {query.trim()
              ? `Найдено статей: ${found.length} из ${knowledgeArticles.length}`
              : `Статей: ${knowledgeArticles.length}`}
          </Typography>

          {found.length === 0 ? (
            <Alert severity="info" sx={{ mt: 1.5 }} data-testid="knowledge-empty">
              Ничего не нашлось. Попробуйте одно слово вместо фразы — поиск ищет по заголовкам и по
              всему тексту статей.
            </Alert>
          ) : (
            <List dense sx={{ mt: 0.5 }} data-testid="knowledge-list">
              {found.map((item) => {
                const snippet = query.trim() ? searchSnippet(item, query.trim().split(/\s+/)[0] ?? '') : null
                return (
                  <ListItemButton
                    key={item.slug}
                    selected={item.slug === slug}
                    onClick={() => openArticle(item.slug)}
                    data-testid={`knowledge-item-${item.slug}`}
                    sx={{ borderRadius: 1, alignItems: 'flex-start' }}
                  >
                    <ListItemText
                      primary={item.title}
                      secondary={snippet ?? item.summary}
                      slotProps={{
                        primary: { sx: { fontWeight: item.slug === slug ? 700 : 500 } },
                        secondary: { variant: 'caption' },
                      }}
                    />
                  </ListItemButton>
                )
              })}
            </List>
          )}
        </Paper>

        <Paper
          variant="outlined"
          ref={readerRef}
          sx={{ p: { xs: 2, md: 3 }, flexGrow: 1, minWidth: 0, width: '100%' }}
          data-testid="knowledge-reader"
        >
          {article ? (
            <>
              <Button
                size="small"
                startIcon={<ArrowBackOutlinedIcon />}
                onClick={() => navigate('/app/ff/knowledge')}
                sx={{ mb: 1.5, display: { md: 'none' } }}
                data-testid="knowledge-back"
              >
                Все статьи
              </Button>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {article.title}
              </Typography>
              {article.summary ? (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>
                  {article.summary}
                </Typography>
              ) : null}
              <MarkdownView blocks={article.blocks} highlight={query} />
            </>
          ) : (
            <Box data-testid="knowledge-intro">
              <Stack direction="row" spacing={1.5} sx={{ mb: 1, alignItems: 'center' }}>
                <MenuBookOutlinedIcon color="primary" />
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  Как пользоваться разделом
                </Typography>
              </Stack>
              <Typography variant="body1" sx={{ mb: 2, lineHeight: 1.65, maxWidth: 720 }}>
                Слева — список статей, по одной на участок работы. Каждая статья устроена одинаково:
                сначала коротко «зачем это нужно», потом пошаговый порядок действий, в конце — частые
                ошибки и что с ними делать. Если не знаете, с чего начать, откройте статью про свой
                участок и пройдите шаги сверху вниз.
              </Typography>
              <Typography variant="body1" sx={{ mb: 2.5, lineHeight: 1.65, maxWidth: 720 }}>
                Поиск наверху ищет не только по названиям, но и по тексту статей: наберите «короб»,
                «расхождение» или «КИЗ» и получите все места, где об этом написано. Несколько слов
                через пробел работают как «и» — найдутся статьи, где встречаются оба.
              </Typography>
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
                {knowledgeArticles.map((item) => (
                  <Chip
                    key={item.slug}
                    label={item.title}
                    onClick={() => openArticle(item.slug)}
                    variant="outlined"
                    data-testid={`knowledge-chip-${item.slug}`}
                  />
                ))}
              </Stack>
            </Box>
          )}
        </Paper>
      </Stack>
    </Box>
  )
}
