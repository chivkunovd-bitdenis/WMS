import { Box, Stack, Typography } from '@mui/material'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AppDialog,
  PrimaryAction,
  SecondaryAction,
  WarningNotice,
} from '../../../ui-kit'
import { CommentField } from './CommentField'
import {
  applyScan,
  containerName,
  type ScanTone,
} from './InventoryScan'
import { InventoryScanField } from './InventoryScanField'
import { InventoryTree } from './InventoryTree'
import {
  EMPTY_FILTERS,
  buildRows,
  setActual,
  totals,
  type InvRow,
} from './InventoryRows'
import type { InventoryCount, InventoryNode } from './InventoryTypes'

// Пересчёт прямо с карты склада.
//
// Это тот же документ инвентаризации, что и на экране S-11, только суженный до
// одной ячейки или одной тары. Человек стоит у полки: уводить его на другой
// экран, чтобы пересчитать один короб, — лишний шаг и потерянное место в списке.
//
// Фильтров здесь нет намеренно: отбирать не из чего, в документе десяток строк.

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 14) return `${n} ${many}`
  if (mod10 === 1) return `${n} ${one}`
  if (mod10 >= 2 && mod10 <= 4) return `${n} ${few}`
  return `${n} ${many}`
}

type Props = {
  open: boolean
  /** Что пересчитываем: «Короб КР-000471», «Ячейка А-01-02». */
  title: string
  /** Где это лежит. Пусто, когда пересчитываем саму ячейку. */
  place?: string | null
  /**
   * Документ, каким он открылся. Дальше правки живут внутри диалога.
   *
   * Иначе каждая набранная цифра поднимала бы документ наверх, а оттуда
   * перерисовывалась вся карта склада — три десятка строк с перетаскиванием.
   * Печатать в такое поле нельзя: буквы догоняют через секунду.
   */
  initialCount: InventoryCount | null
  onClose: () => void
  onSave: (count: InventoryCount) => void
  onPost: (count: InventoryCount) => void
}

/**
 * Серверная версия документа меняется только при открытии/сохранении. Ключ
 * пересоздаёт локальное состояние тогда, а не через каскад setState в effect.
 * Посимвольный ввод сканера родителя вообще не касается.
 */
function countRevisionKey(count: InventoryCount | null): string {
  if (!count) return 'empty'
  const actuals: string[] = []
  function walk(nodes: InventoryNode[]) {
    for (const node of nodes) {
      if (node.kind === 'product') actuals.push(`${node.id}:${node.actual ?? ''}`)
      else walk(node.children)
    }
  }
  for (const cell of count.cells) walk(cell.children)
  return `${count.id}:${actuals.join('|')}`
}

export function InventoryCountDialog(props: Props) {
  return <InventoryCountDialogState key={countRevisionKey(props.initialCount)} {...props} />
}

function InventoryCountDialogState({
  open,
  title,
  place,
  initialCount,
  onClose,
  onSave,
  onPost,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [count, setCount] = useState<InventoryCount | null>(initialCount)
  // Память сканера на одну вещь: какую тару открыли. Пока открыта, пики идут в неё.
  const [openContainerId, setOpenContainerId] = useState<string | null>(null)
  const [scanNote, setScanNote] = useState<{ text: string; tone: ScanTone } | null>(null)
  const [scanFocus, setScanFocus] = useState<{ key: string; request: number } | null>(null)
  const treeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!scanFocus) return
    const frame = window.requestAnimationFrame(() => {
      treeRef.current
        ?.querySelector<HTMLElement>(`[data-row-key="${scanFocus.key}"]`)
        ?.scrollIntoView({ behavior: 'auto', block: 'center' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [scanFocus])

  function handleScan(code: string) {
    setCount((current) => {
      if (!current) return current
      const result = applyScan(current, code, openContainerId)
      setOpenContainerId(result.activeContainerId)
      setScanNote({ text: result.message, tone: result.tone })
      if (result.focusRowKey) {
        const openKeys = result.focusPathKeys ?? []
        setCollapsed((collapsedKeys) => {
          const next = new Set(collapsedKeys)
          let changed = false
          for (const key of openKeys) changed = next.delete(key) || changed
          return changed ? next : collapsedKeys
        })
        const focusKey = result.focusRowKey
        setScanFocus((focus) => focus?.key === focusKey ? focus : ({
          key: focusKey,
          request: (focus?.request ?? 0) + 1,
        }))
      }
      return result.count
    })
  }

  const rows = useMemo(
    () => (count ? buildRows(count, EMPTY_FILTERS, collapsed) : []),
    [count, collapsed],
  )
  const t = useMemo(
    () => (count ? totals(count) : { lines: 0, counted: 0, discrepancies: 0, surplus: 0, shortage: 0, stale: 0 }),
    [count],
  )

  function toggle(row: InvRow) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(row.key)) next.delete(row.key)
      else next.add(row.key)
      return next
    })
  }

  function handleActual(row: InvRow, value: number | null) {
    setCount((current) => (current ? setActual(current, row.id, value) : current))
  }

  const postReason =
    t.counted === 0 ? 'Не введено ни одной цифры' : undefined

  return (
    <AppDialog
      open={open}
      title={`Пересчёт: ${title}`}
      onClose={onClose}
      maxWidth="lg"
      testId="inventory-count-dialog"
      actions={
        <>
          <SecondaryAction onClick={onClose} data-testid="inv-dialog-close">
            Закрыть
          </SecondaryAction>
          <SecondaryAction
            onClick={() => count && onSave(count)}
            disabledReason={t.counted === 0 ? 'Нечего сохранять' : undefined}
            data-testid="inv-dialog-save"
          >
            Сохранить
          </SecondaryAction>
          <PrimaryAction
            onClick={() => count && onPost(count)}
            disabledReason={postReason}
            data-testid="inv-dialog-post"
          >
            Провести
          </PrimaryAction>
        </>
      }
    >
      <Stack spacing={1.5}>
        <InventoryScanField
          onScan={handleScan}
          expects={
            openContainerId && count
              ? `товар в ${containerName(count, openContainerId)}`
              : 'ШК тары или товара'
          }
          error={scanNote?.tone === 'error' ? scanNote.text : null}
          notice={scanNote && scanNote.tone !== 'error' ? scanNote.text : null}
          testId="inv-dialog-scan"
        />

        {place ? (
          <Typography variant="body2" color="text.secondary">
            Лежит в ячейке <strong>{place}</strong>
          </Typography>
        ) : null}
        <Typography variant="body2" color="text.secondary">
          Введите фактическое количество у товара. Строка сходится — зелёная, расходится —
          красная. Сохранение оставит документ черновиком, проведение изменит остаток и
          запишет движения.
        </Typography>

        {t.stale > 0 ? (
          <WarningNotice testId="inv-dialog-stale">
            {`По ${plural(t.stale, 'строке', 'строкам', 'строкам')} остаток изменился с момента открытия: там прошло движение. При проведении посчитаем от нового остатка.`}
          </WarningNotice>
        ) : null}

        <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap' }}>
          <Typography variant="body2">
            Строк: <strong>{t.lines}</strong>
          </Typography>
          <Typography variant="body2">
            Посчитано: <strong>{t.counted}</strong>
          </Typography>
          <Typography variant="body2" color={t.discrepancies ? 'error.main' : 'text.secondary'}>
            С расхождением: <strong>{t.discrepancies}</strong>
          </Typography>
          {t.surplus > 0 ? (
            <Typography variant="body2" sx={{ color: 'success.main' }}>
              Излишек: <strong>+{t.surplus}</strong>
            </Typography>
          ) : null}
          {t.shortage > 0 ? (
            <Typography variant="body2" sx={{ color: 'error.main' }}>
              Недостача: <strong>−{t.shortage}</strong>
            </Typography>
          ) : null}
        </Stack>

        {/* Свободная строка про причину. Та же, что на экране документа: человек
            пишет «пересорт» у полки, а видит это тот, кто откроет документ потом. */}
        <CommentField
          value={count?.comment ?? ''}
          onCommit={(comment) =>
            setCount((current) => (current ? { ...current, comment } : current))
          }
          helperText="Пересорт, повреждение, чужой товар — что угодно своими словами"
          testId="inv-dialog-comment"
        />

        {/* Высоту держим: у короба три строки, у ячейки может быть сорок, и диалог
            не должен прыгать от одного нажатия к другому. */}
        <Box ref={treeRef} sx={{ maxHeight: 460, overflowY: 'auto' }}>
          <InventoryTree
            rows={rows}
            loading={false}
            readOnly={false}
            highlightedKey={scanFocus?.key}
            empty={{
              title: 'Здесь пусто',
              hint: 'Внутри этого места сейчас нет товара — пересчитывать нечего.',
            }}
            onToggle={toggle}
            onActual={handleActual}
          />
        </Box>
      </Stack>
    </AppDialog>
  )
}
