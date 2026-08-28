import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Snackbar, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { WbProductPickerDialog } from '../../components/WbProductPickerDialog'
import { BoxLabelPrintDialog } from '../../components/BoxLabelPrintDialog'
import { FfInboundBoxAddDialog } from './FfInboundBoxAddDialog'
import { BoxImportDialog } from '../../components/BoxImportDialog'
import { formatBoxesCountLabel } from './inboundReceivingHelpers'
import type { FfInboundRequestController } from './FfInboundRequestViewController'

export function FfInboundRequestDialogs({ controller }: { controller: FfInboundRequestController }) {
  const {
    token,
    requestId,
    onClose,
    detail,
    catalog,
    busy,
    pickerOpen,
    setPickerOpen,
    pickerInitialSearch,
    dimensionsLine,
    setDimensionsLine,
    dimensionDraft,
    setDimensionDraft,
    dimensionError,
    boxAddDialogBoxId,
    setBoxAddDialogBoxId,
    finishConfirmOpen,
    setFinishConfirmOpen,
    scanToastError,
    setScanToastError,
    scanAddBarcode,
    setScanAddBarcode,
    importSuccessMsg,
    setImportSuccessMsg,
    boxImportOpen,
    setBoxImportOpen,
    cargoDialogOpen,
    setCargoDialogOpen,
    cargoCount,
    setCargoCount,
    cargoError,
    closeConfirmOpen,
    setCloseConfirmOpen,
    saveSuccessMsg,
    setSaveSuccessMsg,
    boxImportEnabled,
    receivingActive,
    receivingTotals,
    discrepancyLines,
    loadDetail,
    catalogById,
    pickerDisabledProductIds,
    saveDimensions,
    openPicker,
    applyPicker,
    boxPrintTarget,
    setBoxPrintTarget,
    confirmInboundBoxPrint,
    createCargoPlaces,
    completeReceiving,
    boxAddDialogBox,
  } = controller

  return (
    <>
      <WbProductPickerDialog
        open={pickerOpen}
        busy={busy}
        catalog={catalog}
        disabledProductIds={pickerDisabledProductIds}
        testIdPrefix="ff-inbound-picker"
        variant="ff"
        qtyColumnLabel={detail?.status === 'draft' ? 'Кол-во в заявку' : 'Факт'}
        initialSearch={pickerInitialSearch}
        applyLabel={detail?.status === 'draft' ? 'Добавить в заявку' : 'Добавить товар'}
        emptyMessage="В каталоге селлера нет товаров по этому поиску."
        onClose={() => setPickerOpen(false)}
        onApply={applyPicker}
      />

      <Dialog
        open={dimensionsLine != null}
        onClose={() => {
          if (!busy) setDimensionsLine(null)
        }}
        fullWidth
        maxWidth="xs"
        data-testid="ff-inbound-dimensions-dialog"
      >
        <DialogTitle>Габариты товара</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {dimensionError ? (
              <Alert severity="error" data-testid="ff-inbound-dimensions-error">
                {dimensionError}
              </Alert>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {dimensionsLine?.product_name ?? ''}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField
                size="small"
                label="Длина, мм"
                type="number"
                value={dimensionDraft.length}
                onChange={(e) => setDimensionDraft((prev) => ({ ...prev, length: e.target.value }))}
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-length' } }}
              />
              <TextField
                size="small"
                label="Ширина, мм"
                type="number"
                value={dimensionDraft.width}
                onChange={(e) => setDimensionDraft((prev) => ({ ...prev, width: e.target.value }))}
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-width' } }}
              />
              <TextField
                size="small"
                label="Высота, мм"
                type="number"
                value={dimensionDraft.height}
                onChange={(e) => setDimensionDraft((prev) => ({ ...prev, height: e.target.value }))}
                slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-height' } }}
              />
            </Stack>
            <TextField
              size="small"
              label="Вес, г"
              type="number"
              value={dimensionDraft.weight}
              onChange={(e) => setDimensionDraft((prev) => ({ ...prev, weight: e.target.value }))}
              slotProps={{ htmlInput: { min: 1, 'data-testid': 'ff-inbound-dimensions-weight' } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setDimensionsLine(null)}>
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={busy}
            onClick={() => void saveDimensions()}
            data-testid="ff-inbound-dimensions-save"
          >
            Сохранить
          </Button>
        </DialogActions>
      </Dialog>

      {boxAddDialogBox && boxAddDialogBoxId ? (
        <FfInboundBoxAddDialog
          open
          onClose={() => setBoxAddDialogBoxId(null)}
          requestId={requestId}
          boxId={boxAddDialogBoxId}
          boxLabel={`Короб № ${boxAddDialogBox.box_number}`}
          readOnly={!receivingActive}
          token={token}
          requestLines={detail?.lines ?? []}
          boxLines={boxAddDialogBox.lines}
          catalogById={catalogById}
          onUpdated={async () => {
            await loadDetail()
          }}
        />
      ) : null}

      <Snackbar
        open={importSuccessMsg !== null}
        autoHideDuration={3500}
        onClose={() => setImportSuccessMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="success"
          variant="filled"
          onClose={() => setImportSuccessMsg(null)}
          data-testid="ff-inbound-import-success-snackbar"
          sx={{ width: '100%' }}
        >
          {importSuccessMsg}
        </Alert>
      </Snackbar>

      {boxImportEnabled && boxImportOpen ? (
        <BoxImportDialog
          open={boxImportOpen}
          token={token}
          requestId={requestId}
          importBasePath={`/operations/inbound-intake-requests/${requestId}/import-boxes`}
          testIdPrefix="ff-inbound-box-import"
          onClose={() => setBoxImportOpen(false)}
          onApplied={async (message) => {
            setImportSuccessMsg(message)
            await loadDetail()
          }}
        />
      ) : null}

      <Dialog
        open={cargoDialogOpen}
        onClose={() => {
          if (!busy) setCargoDialogOpen(false)
        }}
        maxWidth="xs"
        fullWidth
        data-testid="ff-inbound-cargo-places-dialog"
      >
        <DialogTitle>Создать грузоместа</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {cargoError ? (
              <Alert severity="error" data-testid="ff-inbound-cargo-places-error">
                {cargoError}
              </Alert>
            ) : null}
            <TextField
              size="small"
              label="Количество грузомест"
              type="number"
              value={cargoCount}
              disabled={busy}
              onChange={(e) => setCargoCount(e.target.value)}
              slotProps={{ htmlInput: { min: 1, max: 1000, 'data-testid': 'ff-inbound-cargo-places-count' } }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setCargoDialogOpen(false)}>
            Отмена
          </Button>
          <Button
            variant="contained"
            disabled={busy}
            onClick={() => void createCargoPlaces()}
            data-testid="ff-inbound-cargo-places-create"
          >
            Создать
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={scanToastError !== null}
        autoHideDuration={3500}
        onClose={() => {
          setScanToastError(null)
          setScanAddBarcode(null)
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="error"
          variant="filled"
          onClose={() => {
            setScanToastError(null)
            setScanAddBarcode(null)
          }}
          action={
            scanAddBarcode ? (
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  const barcode = scanAddBarcode
                  setScanToastError(null)
                  setScanAddBarcode(null)
                  void openPicker(barcode)
                }}
                data-testid="ff-inbound-scan-add-product"
              >
                Добавить товар
              </Button>
            ) : undefined
          }
          data-testid="ff-inbound-scan-error-snackbar"
          sx={{ width: '100%' }}
        >
          {scanToastError}
        </Alert>
      </Snackbar>

      <Snackbar
        open={saveSuccessMsg !== null}
        autoHideDuration={2500}
        onClose={() => setSaveSuccessMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="success"
          variant="filled"
          onClose={() => setSaveSuccessMsg(null)}
          data-testid="ff-inbound-save-success-snackbar"
          sx={{ width: '100%' }}
        >
          {saveSuccessMsg}
        </Alert>
      </Snackbar>

      <Dialog
        open={closeConfirmOpen}
        onClose={() => setCloseConfirmOpen(false)}
        maxWidth="xs"
        fullWidth
        data-testid="ff-inbound-close-confirm-dialog"
      >
        <DialogTitle>Закрыть без сохранения?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            В строке факта осталось несохранённое количество.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloseConfirmOpen(false)}>Остаться</Button>
          <Button
            color="warning"
            variant="contained"
            onClick={() => {
              setCloseConfirmOpen(false)
              onClose()
            }}
            data-testid="ff-inbound-close-confirm"
          >
            Закрыть
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={finishConfirmOpen}
        onClose={() => setFinishConfirmOpen(false)}
        data-testid="ff-inbound-discrepancy-dialog"
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Есть расхождения, провести приёмку?</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            {discrepancyLines.length > 0 ? (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small" data-testid="ff-inbound-discrepancy-lines">
                  <TableHead>
                    <TableRow>
                      <TableCell>SKU</TableCell>
                      <TableCell align="right">Ожидалось</TableCell>
                      <TableCell align="right">Принято</TableCell>
                      <TableCell align="right">Отклонение</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {discrepancyLines.map((line) => (
                      <TableRow key={line.productId} data-testid="ff-inbound-discrepancy-line">
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>
                            {line.skuCode}
                          </Typography>
                          {line.productName ? (
                            <Typography variant="caption" color="text.secondary">
                              {line.productName}
                            </Typography>
                          ) : null}
                        </TableCell>
                        <TableCell align="right">{line.expectedQty}</TableCell>
                        <TableCell align="right">{line.acceptedQty}</TableCell>
                        <TableCell align="right">
                          {line.shortage > 0 ? `Недостача ${line.shortage}` : `Излишек ${line.surplus}`}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="body2" color="text.secondary">
                По SKU расхождений нет.
              </Typography>
            )}

            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                bgcolor: receivingTotals.hasBoxDiscrepancy
                  ? (theme) => alpha(theme.palette.warning.main, 0.12)
                  : 'background.paper',
              }}
              data-testid="ff-inbound-discrepancy-box-summary"
            >
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                Короба: {formatBoxesCountLabel(receivingTotals.actualBoxes, receivingTotals.plannedBoxes)}
              </Typography>
              {receivingTotals.hasBoxDiscrepancy ? (
                <Typography variant="body2" color="warning.dark">
                  Количество коробов отличается от плана.
                </Typography>
              ) : null}
            </Paper>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFinishConfirmOpen(false)} disabled={busy}>
            Отмена
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={busy}
            onClick={() => void completeReceiving()}
            data-testid="ff-inbound-discrepancy-confirm"
          >
            Завершить приёмку
          </Button>
        </DialogActions>
      </Dialog>
      <BoxLabelPrintDialog
        open={boxPrintTarget !== null}
        title={
          boxPrintTarget?.kind === 'cargo' || boxPrintTarget?.kind === 'cargo-all'
            ? 'Печать этикетки грузоместа'
            : 'Печать этикетки короба'
        }
        busy={busy}
        onClose={() => setBoxPrintTarget(null)}
        onConfirm={(size) => void confirmInboundBoxPrint(size)}
        testId="ff-inbound-box-print-dialog"
      />
    </>
  )
}
