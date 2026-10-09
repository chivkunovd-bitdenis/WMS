import { useState } from 'react'
import { Button, ButtonBase, IconButton, Stack, Typography } from '@mui/material'
import CloseOutlined from '@mui/icons-material/CloseOutlined'
import { kizDisplayCode, type FboKizCode } from './fboKizData'

// WMS-686 · подбор отгрузки FBO: КИЗ, привязанные к товару в этой отгрузке.
//
// Число КИЗ — просто счёт кодов с этим товаром (GET /marking-codes), отдельного
// счётчика нет. Клик по числу раскрывает под товаром вертикальный список кодов.

/** Крупное число КИЗ товара; клик раскрывает и скрывает список кодов. */
export function FboKizCount({
  count,
  open,
  onToggle,
  productName,
  testId,
}: {
  count: number
  open: boolean
  onToggle: () => void
  productName: string
  testId: string
}) {
  const numberSx = {
    fontSize: '1.25rem',
    lineHeight: 1.2,
    fontWeight: 700,
    fontVariantNumeric: 'tabular-nums',
  } as const
  if (count === 0) {
    return (
      <Typography component="span" sx={{ ...numberSx, color: 'text.disabled' }} data-testid={testId}>
        0
      </Typography>
    )
  }
  return (
    <ButtonBase
      onClick={onToggle}
      aria-expanded={open}
      aria-label={`КИЗ товара ${productName}: ${count}. ${open ? 'Скрыть' : 'Показать'} коды`}
      data-testid={testId}
      sx={{
        ...numberSx,
        px: 1,
        py: 0.25,
        borderRadius: 1,
        color: 'primary.main',
        '&:hover': { backgroundColor: 'action.hover' },
      }}
    >
      {count}
    </ButtonBase>
  )
}

/** Одна строка списка: код, номер приёмки второстепенным текстом, «Перепечатать» и ✕. */
function FboKizCodeRow({
  code,
  onReprint,
  onRemove,
}: {
  code: FboKizCode
  onReprint: (code: FboKizCode) => Promise<void>
  onRemove: (code: FboKizCode) => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const run = (action: (code: FboKizCode) => Promise<void>) => {
    setBusy(true)
    void action(code).finally(() => setBusy(false))
  }
  const display = kizDisplayCode(code.cis_code)
  return (
    <Stack
      direction="row"
      sx={{ alignItems: 'center', flexWrap: 'wrap', columnGap: 1, minWidth: 0 }}
      data-testid="pick-kiz-row"
      data-code-id={code.marking_code_id}
    >
      {/* Длинный код переносится внутри своей строки и не раздвигает таблицу. */}
      <Typography
        variant="body2"
        title={display}
        sx={{
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          minWidth: 0,
          maxWidth: '100%',
          overflowWrap: 'anywhere',
        }}
      >
        {display}
      </Typography>
      {code.intake_document_number ? (
        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}>
          Приёмка {code.intake_document_number}
        </Typography>
      ) : null}
      <Button
        size="small"
        disabled={busy}
        onClick={() => run(onReprint)}
        sx={{ textTransform: 'none', flexShrink: 0 }}
        data-testid="pick-kiz-reprint"
      >
        Перепечатать
      </Button>
      <IconButton
        size="small"
        aria-label="Отвязать код"
        title="Отвязать код"
        disabled={busy}
        onClick={() => run(onRemove)}
        data-testid="pick-kiz-remove"
      >
        <CloseOutlined fontSize="small" />
      </IconButton>
    </Stack>
  )
}

/** Вертикальный список кодов товара под строкой товара. */
export function FboKizList({
  codes,
  onReprint,
  onRemove,
  testId,
}: {
  codes: FboKizCode[]
  onReprint: (code: FboKizCode) => Promise<void>
  onRemove: (code: FboKizCode) => Promise<void>
  testId: string
}) {
  return (
    <Stack spacing={0.25} sx={{ py: 0.5, minWidth: 0 }} data-testid={testId}>
      {codes.map((code) => (
        <FboKizCodeRow key={code.marking_code_id} code={code} onReprint={onReprint} onRemove={onRemove} />
      ))}
    </Stack>
  )
}
