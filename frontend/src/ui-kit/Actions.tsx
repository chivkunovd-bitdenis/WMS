import { Button, IconButton, Stack, Tooltip } from '@mui/material'
import type { ButtonProps } from '@mui/material'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import type { ReactElement, ReactNode } from 'react'

// Канон R-18/R-31: вариантов действия ровно три и четвёртого не будет.
// Главное — заполненная кнопка. Второстепенное — контурная, и она существует
// только рядом с главным действием, чтобы не спорить с ним по весу; отдельно
// стоящая контурная кнопка — это просто слабая кнопка, её быть не должно.
// Опасное — красная заполненная.

const MAX_LABEL_CHARS = 22

function assertShortLabel(children: ReactNode) {
  if (import.meta.env.DEV && typeof children === 'string' && children.length > MAX_LABEL_CHARS) {
    // Канон R-32: подпись кнопки — не длиннее трёх слов. Длинные подписи ломают
    // выравнивание в панели и заставляют оператора читать вместо того, чтобы жать.
    console.warn(`[ui-kit] Подпись кнопки длиннее ${MAX_LABEL_CHARS} символов: «${children}»`)
  }
}

type ActionProps = Omit<ButtonProps, 'variant' | 'color' | 'size'> & {
  children: ReactNode
  disabledReason?: string
}

// Канон R-20: недоступная кнопка объясняет причину, а не просто сереет.
// Tooltip вешаем на span, потому что disabled-кнопка не отдаёт события мыши.
function withReason(node: ReactElement, disabledReason?: string) {
  if (!disabledReason) return node
  return (
    <Tooltip title={disabledReason}>
      <span style={{ display: 'inline-flex' }}>{node}</span>
    </Tooltip>
  )
}

export function PrimaryAction({ children, disabledReason, ...rest }: ActionProps) {
  assertShortLabel(children)
  return withReason(
    <Button variant="contained" size="small" disabled={Boolean(disabledReason)} sx={{ whiteSpace: 'nowrap' }} {...rest}>
      {children}
    </Button>,
    disabledReason,
  )
}

export function SecondaryAction({ children, disabledReason, ...rest }: ActionProps) {
  assertShortLabel(children)
  return withReason(
    <Button variant="outlined" size="small" disabled={Boolean(disabledReason)} sx={{ whiteSpace: 'nowrap' }} {...rest}>
      {children}
    </Button>,
    disabledReason,
  )
}

export function DangerAction({ children, disabledReason, ...rest }: ActionProps) {
  assertShortLabel(children)
  return withReason(
    <Button variant="contained" color="error" size="small" disabled={Boolean(disabledReason)} sx={{ whiteSpace: 'nowrap' }} {...rest}>
      {children}
    </Button>,
    disabledReason,
  )
}

// Канон R-32: кнопки одной группы выравниваются по ширине — иначе панель
// превращается в лесенку, и глаз каждый раз заново ищет главное действие.
export function ActionGroup({ children }: { children: ReactNode }) {
  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{ flexWrap: 'wrap', gap: 1, alignItems: 'center', '& .MuiButton-root': { minWidth: 168 } }}
    >
      {children}
    </Stack>
  )
}

// Канон R-17: иконка без подписи существует только вместе с подсказкой.
// title обязателен по типам — забыть его нельзя, а не «желательно не забывать».
export function IconAction({
  title,
  children,
  testId,
  onClick,
  disabledReason,
}: {
  title: string
  children: ReactNode
  testId?: string
  onClick?: () => void
  disabledReason?: string
}) {
  return (
    <Tooltip title={disabledReason ?? title}>
      <span style={{ display: 'inline-flex' }}>
        <IconButton size="small" onClick={onClick} data-testid={testId} disabled={Boolean(disabledReason)}>
          {children}
        </IconButton>
      </span>
    </Tooltip>
  )
}

// Канон R-33: печать выглядит одинаково во всей системе, а вид определяется местом,
// а не настроением: в строке таблицы — иконка с подсказкой, в панели экрана — кнопка
// с текстом. Что именно поедет на принтер, указывается всегда: печать необратима.
// Список печатаемого закрыт типом, чтобы не разрастались девять разных подписей.
export type Printable = 'ШК товара' | 'ЧЗ и ШК' | 'ШК короба' | 'ШК ячейки' | 'накладную' | 'счёт'

export function PrintAction({
  what,
  placement,
  onClick,
  disabledReason,
  testId,
}: {
  what: Printable
  placement: 'row' | 'panel'
  onClick?: () => void
  disabledReason?: string
  testId?: string
}) {
  const title = `Печать ${what}`
  if (placement === 'row') {
    return (
      <IconAction title={title} onClick={onClick} disabledReason={disabledReason} testId={testId}>
        <PrintOutlined fontSize="small" />
      </IconAction>
    )
  }
  return (
    <PrimaryAction onClick={onClick} disabledReason={disabledReason} data-testid={testId}>
      {title}
    </PrimaryAction>
  )
}
