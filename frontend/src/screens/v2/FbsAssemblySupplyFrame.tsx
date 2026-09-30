import type { PackingScanController } from './fbsSequentialPacking'
import type { ReactNode } from 'react'
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import PrintOutlinedIcon from '@mui/icons-material/PrintOutlined'
import type { FbsWorkspace } from './fbsApi'

// WMS-574 R12–R25: рамка поставки на вкладке «Упаковка и маркировка» окна
// сборки. Здесь только раскладка макета: шапка рамки, место под блок упаковки
// и список коробов. Содержимое — кнопки, строки, сканы, окна — даёт карточка
// поставки (FfFbsSupplyWorkspace в режиме рамки) своими же функциями и
// запросами: логика одна для карточки и для окна сборки.

/** Чем окно сборки управляет рамкой поставки. */
export type FbsAssemblyFrameControl = {
  packingHost?: HTMLElement | null
  registerScanner?: (supplyId: string, scanner: PackingScanController | null) => void
  onScanChange?: () => void

  /** Рамка активна: сканы принимает она, шапка светло-зелёная (R13). */
  active: boolean
  /** Рамка развёрнута — у неактивной видны её короба (R12). */
  expanded: boolean
  /** Вкладка «Упаковка и маркировка» сейчас открыта. */
  visible: boolean
  onToggleExpanded: () => void
  /** Рамка стала активной: окно сборки завершает работу прежней (R13, R15). */
  onActivate: () => void
  onDeactivate: () => void
  /** Свежий снимок поставки — для шапки окна сборки и «Состава». */
  onWorkspaceChange: (workspace: FbsWorkspace) => void
  /** Esc в окне сборки: рамка снимает ожидание ЧЗ, как Esc в карточке. */
  registerEscape: (handler: (() => boolean) | null) => void
}

export type FbsAssemblyFrameBoxes = {
  routeLabel: string
  rows: ReactNode[]
  printAllLabel: string
  printAllDisabled: boolean
  onPrintAll: () => void
  createDisabled: boolean
  creating: boolean
  onCreate: () => void
}

type Props = {
  supplyId: string
  title: string
  packed: number
  total: number
  honestSignSkipped: boolean
  transferred: boolean
  active: boolean
  expanded: boolean
  busy: boolean
  starting: boolean
  onToggleExpanded: () => void
  onStart: () => void
  onFinish: () => void
  transfer: { label: string; disabled: boolean; onClick: () => void } | null
  /** Сообщения и блок упаковки — только в активной рамке. */
  messages: ReactNode
  packing: ReactNode
  boxes: FbsAssemblyFrameBoxes | null
  /** После передачи — QR всей поставки, как на вкладке «Короба» карточки. */
  afterBoxes?: ReactNode
  children?: ReactNode
}

export function FbsAssemblySupplyFrame({
  supplyId,
  title,
  packed,
  total,
  honestSignSkipped,
  transferred,
  active,
  expanded,
  busy,
  starting,
  onToggleExpanded,
  onStart,
  onFinish,
  transfer,
  messages,
  packing,
  boxes,
  afterBoxes,
  children,
}: Props) {
  return (
    <Paper
      variant="outlined"
      sx={{
        overflow: 'hidden',
        borderColor: active ? 'success.main' : 'divider',
        borderWidth: active ? 2 : 1,
      }}
      data-testid={`fbs-assembly-supply-${supplyId}`}
      data-active={active ? 'true' : 'false'}
    >
      <Box
        sx={{
          px: 2,
          py: 1.5,
          bgcolor: active ? (theme) => alpha(theme.palette.success.main, 0.12) : 'background.paper',
          borderBottom: expanded ? 1 : 0,
          borderColor: 'divider',
        }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', minWidth: 0 }}>
            <IconButton size="small" onClick={onToggleExpanded} aria-label="Свернуть или развернуть поставку" data-testid={`fbs-assembly-supply-toggle-${supplyId}`}>
              {expanded ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
            </IconButton>
            <Box sx={{ minWidth: 0 }}>
              {/* Без noWrap: длинная шапка переносится целиком, без многоточия (R12). */}
              <Typography variant="subtitle1" sx={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                {title}
              </Typography>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 0.25, flexWrap: 'wrap' }} useFlexGap>
                <Typography variant="body2" color="text.secondary">
                  Упаковано {packed} из {total}
                </Typography>
                {honestSignSkipped ? <Chip size="small" color="warning" label="Сдаём без Честного знака" /> : null}
                {transferred ? <Chip size="small" color="success" label="Передана в WB" /> : null}
              </Stack>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
            {transfer ? (
              <Button variant="outlined" disabled={transfer.disabled} onClick={transfer.onClick} data-testid={`fbs-assembly-supply-transfer-${supplyId}`}>
                {transfer.label}
              </Button>
            ) : null}
            {active ? (
              <Button variant="contained" onClick={onFinish} data-testid={`fbs-assembly-supply-finish-${supplyId}`}>
                Завершить работу с поставкой
              </Button>
            ) : (
              <Button
                variant="contained"
                onClick={onStart}
                disabled={starting}
                startIcon={starting ? <CircularProgress size={18} color="inherit" /> : undefined}
                data-testid={`fbs-assembly-supply-start-${supplyId}`}
              >
                Начать работу с поставкой
              </Button>
            )}
          </Stack>
        </Stack>
      </Box>

      <Collapse in={expanded}>
        {active ? (
          <>
            {busy ? <LinearProgress /> : null}
            {messages ? <Box sx={{ px: 2, pt: 2 }}>{messages}</Box> : null}
            {packing}
          </>
        ) : null}
        {boxes ? (
          <Box sx={{ borderTop: active ? 1 : 0, borderColor: 'divider' }} data-testid={`fbs-assembly-boxes-${supplyId}`}>
            <Stack direction="row" spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: 'center', px: 2, pt: 1.75, pb: 0.5 }}>
              <Typography variant="subtitle2">Короба · {boxes.routeLabel}</Typography>
              {active ? (
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <Button
                    size="small"
                    startIcon={<PrintOutlinedIcon />}
                    disabled={boxes.printAllDisabled}
                    onClick={boxes.onPrintAll}
                    data-testid={`fbs-assembly-print-all-qr-${supplyId}`}
                  >
                    {boxes.printAllLabel}
                  </Button>
                  <Button
                    size="small"
                    disabled={boxes.createDisabled}
                    onClick={boxes.onCreate}
                    startIcon={boxes.creating ? <CircularProgress size={14} color="inherit" /> : undefined}
                    data-testid={`fbs-assembly-create-box-${supplyId}`}
                  >
                    Создать короб
                  </Button>
                </Stack>
              ) : null}
            </Stack>
            {boxes.rows.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 1.75, pt: 0.5 }}>
                Коробов пока нет.
              </Typography>
            ) : (
              <Stack divider={<Divider flexItem />} sx={{ pb: 0.5 }}>
                {boxes.rows}
              </Stack>
            )}
          </Box>
        ) : null}
        {afterBoxes ? (
          <Stack spacing={2} sx={{ px: 2, pb: 2, pt: 1 }} data-testid={`fbs-assembly-supply-qr-${supplyId}`}>
            {afterBoxes}
          </Stack>
        ) : null}
      </Collapse>
      {children}
    </Paper>
  )
}
