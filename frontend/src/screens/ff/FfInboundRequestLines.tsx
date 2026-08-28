import { Fragment, type FocusEvent, type KeyboardEvent } from 'react'
import EditOutlined from '@mui/icons-material/EditOutlined'
import StraightenOutlined from '@mui/icons-material/StraightenOutlined'
import { Box, IconButton, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { OzonReturnGroupRow, OzonReturnOrphanGroupRows, ReturnDefectiveQtyCell } from '../../components/OzonReturnDocumentUi'
import { ozonReturnGroupAt, ozonReturnUnrepresentedGroups } from '../../components/ozonReturnPickerHelpers'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import { effectiveActualQty, isDoneStatus } from './inboundReceivingHelpers'
import { isLatestScannedInboundLine } from './inboundReceivingRuntime'
import type { FfInboundRequestController } from './FfInboundRequestViewController'
import { InboundProductLineCell } from './FfInboundRequestLineCells'
import { formatLineDiscrepancy } from './FfInboundRequestViewTypes'

export function FfInboundRequestLines({ controller }: { controller: FfInboundRequestController }) {
  if (!controller.detail) return null

  const {
    isFulfillmentAdmin,
    detail,
    busy,
    actualDraftByLineId,
    setActualDraftByLineId,
    actualDraftErrorByLineId,
    setActualDraftErrorByLineId,
    actualDraftRef,
    actualInputRefs,
    manualEditLineId,
    setManualEditLineId,
    lastScannedLineId,
    sortingView,
    receptionClosed,
    isReturnOperation,
    isOzonReturn,
    showInboundLinesTable,
    catalogById,
    ozonReturn,
    displayMetaByProductId,
    formatLineDimensions,
    openDimensionsEditor,
    saveManualLineActual,
    actualEditable,
  } = controller

  return (
    <>
          {showInboundLinesTable ? (
            <TableContainer
              sx={{
                width: '100%',
                maxWidth: '100%',
                minWidth: 0,
                overflowX: 'auto',
                WebkitOverflowScrolling: 'touch',
              }}
            >
              {sortingView && receptionClosed ? (
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                  Состав приёмки
                </Typography>
              ) : null}
              <Table
                size="small"
                data-testid="ff-inbound-lines-table"
                sx={{
                  tableLayout: 'fixed',
                  width: '100%',
                  minWidth: 760,
                  '& th': { py: 1.25 },
                  '& td': { py: 1.25 },
                  '& th, & td': { verticalAlign: 'middle' },
                }}
              >
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ minWidth: 0, overflow: 'hidden' }}>
                      Товар
                    </TableCell>
                    <TableCell sx={{ width: 188 }}>
                      Габариты
                    </TableCell>
                    <TableCell align="right" sx={{ width: 112 }}>
                      План
                    </TableCell>
                    <TableCell align="right" sx={{ width: 200 }}>
                      Принято
                    </TableCell>
                    {isReturnOperation ? <TableCell align="right" sx={{ width: 120 }}>Брак</TableCell> : null}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {detail.lines.map((ln, lineIndex) => {
                  const displayMeta =
                    displayMetaByProductId.get(ln.product_id) ??
                    productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                  const boxes = detail.boxes ?? []
                  const effective = effectiveActualQty(ln, boxes, detail.status)
                  const hasDiscrepancy = effective !== ln.expected_qty
                  const matchesExpected = effective === ln.expected_qty && effective > 0
                  const discrepancyLabel = formatLineDiscrepancy(ln.expected_qty, effective)
                  const rowTestId = matchesExpected
                    ? 'ff-inbound-line-row-match'
                    : hasDiscrepancy
                      ? 'ff-inbound-line-row-discrepancy'
                      : 'ff-inbound-line-row'
                  const manualOpen = manualEditLineId === ln.id
                  const { group: ozonGroup, showHeader: showOzonGroupHeader } =
                    ozonReturnGroupAt(ozonReturn.groups, detail.lines, lineIndex)
                  return (
                    <Fragment key={ln.id}>
                      {showOzonGroupHeader && ozonGroup ? <OzonReturnGroupRow group={ozonGroup} documentDone={isDoneStatus(detail.status)} colSpan={isReturnOperation ? 5 : 4} /> : null}
                    <TableRow
                      hover
                      data-testid={rowTestId}
                      sx={{
                        '& td': { px: 1.25 },
                        '& td:first-of-type': { pl: 1 },
                        '& td:last-of-type': { pr: 1 },
                        ...(matchesExpected
                          ? {
                              backgroundColor: (theme) =>
                                alpha(theme.palette.success.main, 0.12),
                            }
                          : null),
                        ...(hasDiscrepancy
                          ? {
                              backgroundColor: (theme) =>
                                alpha(theme.palette.error.main, 0.08),
                          }
                          : null),
                        ...(isLatestScannedInboundLine(ln.id, lastScannedLineId)
                          ? {
                              backgroundColor: (theme) => alpha(theme.palette.success.main, 0.16),
                              boxShadow: (theme) =>
                                `inset 0 0 0 1px ${alpha(theme.palette.success.main, 0.6)}`,
                            }
                          : null),
                      }}
                    >
                      <InboundProductLineCell
                        meta={displayMeta}
                        productId={ln.product_id}
                        printTestId={`ff-inbound-line-print-${ln.id}`}
                      />
                      <TableCell sx={{ width: 188, minWidth: 0 }}>
                        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', minWidth: 0 }}>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              flex: '1 1 auto',
                              minWidth: 0,
                              whiteSpace: 'normal',
                              wordBreak: 'break-word',
                            }}
                            title={formatLineDimensions(ln)}
                            data-testid="ff-inbound-line-dimensions"
                          >
                            {formatLineDimensions(ln)}
                          </Typography>
                          {isFulfillmentAdmin ? (
                            <Tooltip title="Габариты">
                              <Box component="span" sx={{ flex: '0 0 40px', display: 'inline-flex' }}>
                                <IconButton
                                  size="small"
                                  disabled={busy}
                                  onClick={() => openDimensionsEditor(ln)}
                                  data-testid="ff-inbound-line-dimensions-edit"
                                  aria-label="Габариты"
                                  sx={{ width: 40, height: 40 }}
                                >
                                  <StraightenOutlined fontSize="small" />
                                </IconButton>
                              </Box>
                            </Tooltip>
                          ) : null}
                        </Stack>
                      </TableCell>
                      <TableCell align="right" sx={{ width: 112, minWidth: 0 }}>
                        <Stack spacing={0.25} sx={{ alignItems: 'flex-end' }}>
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 600 }}
                            data-testid="ff-inbound-line-expected"
                          >
                            {ln.expected_qty}
                          </Typography>
                          {ln.added_by_fulfillment ? (
                            <Typography
                              variant="caption"
                              color="error.dark"
                              sx={{ whiteSpace: 'nowrap' }}
                              data-testid="ff-inbound-line-added-by-ff"
                            >
                              Добавлено ФФ
                            </Typography>
                          ) : null}
                        </Stack>
                      </TableCell>
                      <TableCell align="right" sx={{ width: 200, minWidth: 0 }}>
                        <Stack
                          direction="row"
                          spacing={0.75}
                          sx={{ justifyContent: 'flex-end', alignItems: 'center', minWidth: 0 }}
                        >
                          {manualOpen && actualEditable ? (
                            <TextField
                              type="text"
                              size="small"
                              value={
                                actualDraftByLineId[ln.id] ??
                                String(effectiveActualQty(ln, boxes, detail.status))
                              }
                              disabled={busy}
                              error={Boolean(actualDraftErrorByLineId[ln.id])}
                              helperText={actualDraftErrorByLineId[ln.id] || ' '}
                              inputRef={(node) => {
                                actualInputRefs.current[ln.id] = node
                              }}
                              onChange={(e) => {
                                const nextVal = e.target.value
                                actualDraftRef.current = {
                                  ...actualDraftRef.current,
                                  [ln.id]: nextVal,
                                }
                                setActualDraftErrorByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: '',
                                }))
                                setActualDraftByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: nextVal,
                                }))
                              }}
                              slotProps={{
                                htmlInput: {
                                  inputMode: 'numeric',
                                  pattern: '[0-9]*',
                                  'data-testid': 'ff-inbound-line-actual',
                                  onBlur: (e: FocusEvent<HTMLInputElement>) => {
                                    if (manualEditLineId !== ln.id) {
                                      return
                                    }
                                    void saveManualLineActual(ln.id, e.currentTarget.value)
                                  },
                                  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => {
                                    if (e.key === 'Enter') {
                                      e.preventDefault()
                                      void saveManualLineActual(ln.id, e.currentTarget.value)
                                    }
                                  },
                                },
                              }}
                              sx={{
                                flex: '0 0 116px',
                                width: 116,
                                '& .MuiFormHelperText-root': { mx: 0 },
                              }}
                            />
                          ) : (
                            <Stack spacing={0.1} sx={{ alignItems: 'flex-end', minWidth: 0, flex: '1 1 auto' }}>
                              <Typography
                                variant="body2"
                                sx={{ fontWeight: 700, minWidth: 24, textAlign: 'right' }}
                                data-testid="ff-inbound-line-actual-display"
                              >
                                {effective}
                              </Typography>
                              {discrepancyLabel ? (
                                <Typography
                                  variant="caption"
                                  color="error.dark"
                                  sx={{ lineHeight: 1.15, whiteSpace: 'nowrap' }}
                                  data-testid="ff-inbound-line-discrepancy"
                                >
                                  {discrepancyLabel}
                                </Typography>
                              ) : null}
                            </Stack>
                          )}
                          {actualEditable ? (
                            <IconButton
                              size="small"
                              aria-label="Править количество"
                              disabled={busy}
                              sx={{ flex: '0 0 40px', width: 40, height: 40 }}
                              onMouseDown={(e) => {
                                if (manualOpen) {
                                  e.preventDefault()
                                }
                              }}
                              onClick={() => {
                                if (manualOpen) {
                                  void saveManualLineActual(ln.id)
                                  return
                                }
                                setManualEditLineId(ln.id)
                                setActualDraftByLineId((prev) => ({
                                  ...prev,
                                  [ln.id]: String(effectiveActualQty(ln, boxes, detail.status)),
                                }))
                              }}
                              data-testid="ff-inbound-line-manual-edit"
                            >
                              <EditOutlined fontSize="small" />
                            </IconButton>
                          ) : null}
                        </Stack>
                      </TableCell>
                      {isReturnOperation ? <ReturnDefectiveQtyCell lineId={ln.id} defectiveQty={ln.defective_qty ?? 0} acceptedQty={effective} disabled={busy || ln.posted_qty > 0 || isDoneStatus(detail.status)} onSave={ozonReturn.saveDefective} /> : null}
                    </TableRow>
                    </Fragment>
                  )
                })}
                {isOzonReturn ? <OzonReturnOrphanGroupRows groups={ozonReturnUnrepresentedGroups(ozonReturn.groups, detail.lines)} documentDone={isDoneStatus(detail.status)} colSpan={isReturnOperation ? 5 : 4} /> : null}
                {detail.lines.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={isReturnOperation ? 5 : 4}>
                      <Typography variant="body2" color="text.secondary">
                        Товаров пока нет. Нажмите «Добавить товар» или отсканируйте ШК товара из каталога селлера.
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </TableContainer>
          ) : null}

    </>
  )
}
