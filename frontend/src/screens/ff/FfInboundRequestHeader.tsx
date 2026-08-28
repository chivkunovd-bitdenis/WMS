import EditOutlined from '@mui/icons-material/EditOutlined'
import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { Button, Chip, FormControlLabel, Stack, Switch, Typography } from '@mui/material'
import { WmsDateField } from '../../components/WmsDateField'
import { OzonReturnActions } from '../../components/OzonReturnDocumentUi'
import { MarketplaceChip } from '../../ui-kit'
import { formatProductBarcodeDisplay, productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import { printInboundReceivingSheet } from '../../utils/printInboundReceivingSheet'
import { formatBoxesCountLabel, inboundStatusRu, isSortingStatus } from './inboundReceivingHelpers'
import type { FfInboundRequestController } from './FfInboundRequestViewController'
import { inboundStatusChipColor } from './FfInboundRequestViewTypes'

export function FfInboundRequestHeader({ controller }: { controller: FfInboundRequestController }) {
  if (!controller.detail) return null

  const {
    isFulfillmentAdmin,
    workspace,
    addressStorageEnabled,
    detail,
    busy,
    setDistOpen,
    distBusy,
    returnAutoPrint,
    setReturnAutoPrint,
    plannedDateDraft,
    setPlannedDateDraft,
    requestWarehouse,
    plannedDateFieldEnabled,
    waybillPrintEnabled,
    documentDistributionEnabled,
    receivingActive,
    waitingForFfStart,
    sellerCreatedDraft,
    isReturnOperation,
    isOzonReturn,
    usesReturnShortcut,
    operationTypeLabel,
    processTitle,
    displayDocumentNumber,
    receivingTotals,
    catalogById,
    ozonReturn,
    draftLocked,
    distributionCompleted,
    patchPlannedDate,
    openPicker,
    submitToWarehouse,
    beginReceiving,
    reopenReceiving,
    requestCompleteReceiving,
    handleSaveDocument,
    handleClose,
    canReopenReceiving,
  } = controller

  return (
    <>
          <Stack spacing={2} sx={{ mb: 2 }}>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={2}
              useFlexGap
              sx={{ alignItems: { xs: 'flex-start', sm: 'flex-end' }, justifyContent: 'space-between' }}
            >
              <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 700 }}>
                  {processTitle}
                </Typography>
                {displayDocumentNumber ? (
                  <Typography
                    variant="h5"
                    sx={{ fontWeight: 800, lineHeight: 1.1 }}
                    data-testid="ff-inbound-document-number"
                  >
                    {displayDocumentNumber}
                  </Typography>
                ) : null}
                {detail.waybill_number?.trim() ? (
                  <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-waybill-number">
                    Накладная: <strong>{detail.waybill_number.trim()}</strong>
                  </Typography>
                ) : null}
              </Stack>

              <Stack
                direction="row"
                spacing={1.5}
                useFlexGap
                sx={{
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  justifyContent: { xs: 'flex-start', sm: 'flex-end' },
                }}
                data-testid="ff-inbound-compact-summary"
              >
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-operation-type">
                  Тип: <strong>{operationTypeLabel}</strong>
                </Typography>
                {detail.marketplace ? <MarketplaceChip marketplace={detail.marketplace === 'wildberries' ? 'wb' : 'ozon'} testId="ff-inbound-marketplace-chip" /> : null}
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-seller-name">
                  Селлер: <strong>{detail.seller_name ?? '—'}</strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-received-summary">
                  Принято: <strong>{receivingTotals.acceptedQty} из {receivingTotals.expectedQty}</strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-boxes-summary">
                  Короба:{' '}
                  <strong data-testid="ff-inbound-planned-boxes">
                    {formatBoxesCountLabel(receivingTotals.actualBoxes, receivingTotals.plannedBoxes)}
                  </strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-volume-summary">
                  Литраж: <strong>{receivingTotals.totalVolumeLiters.toFixed(2)} л</strong>
                </Typography>
                <Typography variant="body2" color="text.secondary" data-testid="ff-inbound-weight-summary">
                  Вес:{' '}
                  <strong>
                    {receivingTotals.hasKnownWeight ? `${receivingTotals.totalWeightKg.toFixed(2)} кг` : 'не указан'}
                  </strong>
                </Typography>
              </Stack>
            </Stack>

            <Stack
              direction="row"
              spacing={2}
              useFlexGap
              sx={{ alignItems: 'center', flexWrap: 'wrap' }}
            >
              {plannedDateFieldEnabled ? (
                <WmsDateField
                  label="Дата приёмки (план)"
                  value={plannedDateDraft || null}
                  onChange={(iso) => {
                    const next = iso ?? ''
                    setPlannedDateDraft(next)
                    if ((next || '') !== (detail.planned_delivery_date ?? '')) {
                      void patchPlannedDate(next)
                    }
                  }}
                  disabled={draftLocked || busy}
                  required
                  testId="ff-inbound-planned-date"
                  slotProps={{ textField: { fullWidth: false, sx: { minWidth: 220 } } }}
                />
              ) : null}
              <Chip
                label={inboundStatusRu(detail.status)}
                color={inboundStatusChipColor(detail.status)}
                data-testid="ff-inbound-status-chip"
              />
            </Stack>

            <Stack
              direction="row"
              spacing={1}
              useFlexGap
              sx={{
                justifyContent: { xs: 'stretch', sm: 'flex-end' },
                alignItems: 'center',
                flexWrap: 'wrap',
              }}
            >
              {isFulfillmentAdmin &&
              workspace !== 'sorting' &&
              receivingActive ? (
                <>
                  <Button
                    variant="contained"
                    disabled={busy}
                    onClick={() => void openPicker()}
                    data-testid="ff-inbound-receiving-add-products"
                  >
                    Добавить товар
                  </Button>
                  {isReturnOperation ? (
                    <FormControlLabel
                      control={
                        <Switch
                          size="small"
                          checked={returnAutoPrint}
                          onChange={(e) => setReturnAutoPrint(e.target.checked)}
                          data-testid="ff-inbound-return-autoprint"
                        />
                      }
                      label="Печатать ШК при скане"
                    />
                  ) : null}
                </>
              ) : null}

              {isFulfillmentAdmin &&
              workspace !== 'sorting' &&
              receivingActive ? (
                <Button
                  variant="contained"
                  disabled={busy}
                  onClick={() => void requestCompleteReceiving()}
                  data-testid="ff-inbound-verify-complete"
                >
                  Завершить приёмку
                </Button>
              ) : null}

              {documentDistributionEnabled &&
              isFulfillmentAdmin &&
              addressStorageEnabled &&
              isSortingStatus(detail.status) &&
              workspace === 'full' ? (
                <Button
                  variant="contained"
                  disabled={distBusy || distributionCompleted}
                  onClick={() => setDistOpen(true)}
                  data-testid="ff-inbound-distribute-open"
                >
                  Распределить по ячейкам
                </Button>
              ) : null}

              {detail.status === 'draft' ? (
                <>
                  <Button
                    variant="contained"
                    disabled={draftLocked || busy}
                    onClick={() => void openPicker()}
                    data-testid="ff-inbound-add-products"
                  >
                    Добавить товар
                  </Button>
                  {isFulfillmentAdmin && sellerCreatedDraft ? null : (
                    <Button
                      variant="contained"
                      color="secondary"
                      disabled={busy || detail.lines.length === 0}
                      onClick={() =>
                        isFulfillmentAdmin
                          ? void beginReceiving()
                          : void submitToWarehouse()
                      }
                      data-testid="ff-inbound-submit-warehouse"
                    >
                      {isFulfillmentAdmin
                        ? usesReturnShortcut
                          ? 'Завершить подбор возврата'
                          : 'Начать приёмку'
                        : 'Передать на склад'}
                    </Button>
                  )}
                </>
              ) : null}

              {isFulfillmentAdmin && isOzonReturn ? <OzonReturnActions busy={busy} showPickerAction={detail.status === 'draft'} workflow={ozonReturn} /> : null}

              {isFulfillmentAdmin && workspace !== 'sorting' && waitingForFfStart ? (
                <Button
                  variant="contained"
                  color="secondary"
                  disabled={busy || detail.lines.length === 0}
                  onClick={() => void beginReceiving()}
                  data-testid="ff-inbound-submit-warehouse"
                >
                  Начать приёмку
                </Button>
              ) : null}

              {canReopenReceiving ? (
                <Button
                  variant="outlined"
                  startIcon={<EditOutlined />}
                  disabled={busy}
                  onClick={() => void reopenReceiving()}
                  data-testid="ff-inbound-reopen-receiving"
                >
                  Редактировать
                </Button>
              ) : null}

              {waybillPrintEnabled && detail.lines.length > 0 ? (
                <Button
                  variant="outlined"
                  startIcon={<PrintOutlined />}
                  disabled={busy}
                  data-testid="ff-inbound-print-waybill"
                  onClick={() => {
                    const wh = requestWarehouse
                    printInboundReceivingSheet({
                      documentNumber: displayDocumentNumber,
                      sellerName: detail.seller_name ?? null,
                      warehouseName: wh ? `${wh.name} (${wh.code})` : '—',
                      plannedDate: detail.planned_delivery_date,
                      items: detail.lines.map((ln) => {
                        const meta = productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                        return {
                          product_name: meta.product_name,
                          vendor_code: meta.wb_vendor_code ?? '',
                          sku_code: meta.sku_code,
                          barcode: formatProductBarcodeDisplay(meta),
                          wb_nm_id: meta.wb_nm_id,
                          photo_url: meta.wb_primary_image_url,
                          expected_qty: ln.expected_qty,
                        }
                      }),
                    })
                  }}
                >
                  Печать накладной
                </Button>
              ) : null}

              <Button
                variant="outlined"
                disabled={busy}
                onClick={() => void handleSaveDocument()}
                data-testid="ff-inbound-save"
              >
                Сохранить
              </Button>

              <Button variant="outlined" disabled={busy} onClick={handleClose} data-testid="ff-inbound-close">
                Закрыть
              </Button>
            </Stack>
          </Stack>

    </>
  )
}
