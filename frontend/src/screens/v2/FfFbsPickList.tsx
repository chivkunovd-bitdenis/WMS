import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import {
  generateFbsSupplyStickers,
  getFbsPickingList,
  type FbsPickingItem,
} from './fbsApi'

type Props = {
  token: string
  authHeaders: (t: string) => Record<string, string>
  supplyId: string | null
  open: boolean
  onClose: () => void
}

type Mark = { collected: boolean; packed: boolean }
type Marks = Record<string, Mark>
type PickFilter = 'all' | 'not_collected' | 'not_packed'

// Отметки Собрал/Упаковал в v1 живут локально (localStorage) — серверного персиста пока нет.
function loadMarks(supplyId: string): Marks {
  try {
    return JSON.parse(localStorage.getItem(`fbs-picklist-${supplyId}`) ?? '{}') as Marks
  } catch {
    return {}
  }
}
function saveMarks(supplyId: string, marks: Marks): void {
  localStorage.setItem(`fbs-picklist-${supplyId}`, JSON.stringify(marks))
}

function printImages(title: string, dataUrls: string[]): void {
  const w = window.open('', '_blank')
  if (!w) return
  const imgs = dataUrls.map((s) => `<img src="${s}" style="display:block;margin:0 auto 8px" />`).join('')
  w.document.write(`<title>${title}</title><body onload="window.print()">${imgs}</body>`)
  w.document.close()
}

export function FfFbsPickList({ token, authHeaders, supplyId, open, onClose }: Props) {
  const [items, setItems] = useState<FbsPickingItem[]>([])
  const [marks, setMarks] = useState<Marks>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<PickFilter>('all')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    if (!supplyId) return
    setError(null)
    setBusy(true)
    try {
      setItems(await getFbsPickingList(token, authHeaders, supplyId))
      setMarks(loadMarks(supplyId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить лист подбора')
      setItems([])
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, supplyId])

  useEffect(() => {
    if (open && supplyId) void load()
  }, [open, supplyId, load])

  const setMark = useCallback(
    (article: string, patch: Partial<Mark>) => {
      if (!supplyId) return
      setMarks((prev) => {
        const cur = prev[article] ?? { collected: false, packed: false }
        const next = { ...prev, [article]: { ...cur, ...patch } }
        saveMarks(supplyId, next)
        return next
      })
    },
    [supplyId],
  )

  const collectedCount = useMemo(
    () => items.filter((i) => marks[i.article]?.collected).length,
    [items, marks],
  )
  const packedCount = useMemo(
    () => items.filter((i) => marks[i.article]?.packed).length,
    [items, marks],
  )

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return items.filter((i) => {
      const m = marks[i.article] ?? { collected: false, packed: false }
      if (filter === 'not_collected' && m.collected) return false
      if (filter === 'not_packed' && m.packed) return false
      if (needle) {
        return (
          i.article.toLowerCase().includes(needle) ||
          i.product_name.toLowerCase().includes(needle)
        )
      }
      return true
    })
  }, [items, marks, filter, search])

  const printStickers = useCallback(async () => {
    if (!supplyId) return
    setBusy(true)
    setError(null)
    try {
      const stickers = await generateFbsSupplyStickers(token, authHeaders, supplyId)
      const urls = stickers
        .map((s) => s.sticker_file)
        .filter((f): f is string => !!f)
        .map((f) => (f.startsWith('data:') ? f : `data:image/png;base64,${f}`))
      if (urls.length === 0) setError('Стикеры ещё не готовы — попробуйте позже.')
      else printImages('Стикеры заказов FBS', urls)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось получить стикеры')
    } finally {
      setBusy(false)
    }
  }, [token, authHeaders, supplyId])

  const filters: { key: PickFilter; label: string }[] = [
    { key: 'all', label: 'Все' },
    { key: 'not_collected', label: 'Не собраны' },
    { key: 'not_packed', label: 'Не упакованы' },
  ]

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" data-testid="fbs-pick-list">
      <DialogTitle>
        Лист подбора
        <Typography variant="body2" color="text.secondary">
          Собрано {collectedCount}/{items.length} · Упаковано {packedCount}/{items.length}
        </Typography>
      </DialogTitle>
      <DialogContent dividers>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }} data-testid="fbs-pick-error">
            {error}
          </Alert>
        ) : null}

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 2, alignItems: 'center' }}>
          <Stack direction="row" spacing={1} data-testid="fbs-pick-filters">
            {filters.map((f) => (
              <Chip
                key={f.key}
                label={f.label}
                color={filter === f.key ? 'primary' : 'default'}
                variant={filter === f.key ? 'filled' : 'outlined'}
                onClick={() => setFilter(f.key)}
                data-testid={`fbs-pick-filter-${f.key}`}
              />
            ))}
          </Stack>
          <TextField
            size="small"
            label="Поиск"
            placeholder="Артикул или название"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ minWidth: 240, flexGrow: 1 }}
            slotProps={{ htmlInput: { 'data-testid': 'fbs-pick-search' } }}
          />
          {busy ? <CircularProgress size={18} data-testid="fbs-pick-loading" /> : null}
        </Stack>

        <TableContainer sx={{ maxHeight: '60vh' }}>
          <Table stickyHeader size="small" data-testid="fbs-pick-table">
            <TableHead>
              <TableRow>
                <TableCell>Товар</TableCell>
                <TableCell width={90} align="right">
                  Кол-во
                </TableCell>
                <TableCell width={90} align="center">
                  Собрал
                </TableCell>
                <TableCell width={90} align="center">
                  Упаковал
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visible.map((i) => {
                const m = marks[i.article] ?? { collected: false, packed: false }
                return (
                  <TableRow key={i.article} data-testid="fbs-pick-row" data-article={i.article}>
                    <TableCell>
                      <Typography variant="body2">{i.product_name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {i.article}
                        {i.size ? ` · ${i.size}` : ''}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{i.quantity}</TableCell>
                    <TableCell align="center">
                      <Checkbox
                        checked={m.collected}
                        onChange={(e) => setMark(i.article, { collected: e.target.checked })}
                        data-testid="fbs-pick-collected"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Checkbox
                        checked={m.packed}
                        onChange={(e) => setMark(i.article, { packed: e.target.checked })}
                        data-testid="fbs-pick-packed"
                      />
                    </TableCell>
                  </TableRow>
                )
              })}
              {!busy && visible.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Box sx={{ py: 3, textAlign: 'center' }} data-testid="fbs-pick-empty">
                      <Typography variant="body2" color="text.secondary">
                        Нет позиций по фильтру.
                      </Typography>
                    </Box>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => void printStickers()} disabled={busy} data-testid="fbs-pick-print-stickers">
          Печать стикеров
        </Button>
        <Button variant="contained" onClick={onClose}>
          Закрыть
        </Button>
      </DialogActions>
    </Dialog>
  )
}
