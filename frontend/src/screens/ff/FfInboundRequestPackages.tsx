import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined'
import { Accordion, AccordionDetails, AccordionSummary, Box, Button, Chip, Paper, Stack, Typography } from '@mui/material'
import { productDisplayMetaFromCatalog } from '../../types/wbProductCatalog'
import type { FfInboundRequestController } from './FfInboundRequestViewController'
import { InboundBoxContentLine } from './FfInboundRequestLineCells'

export function FfInboundRequestPackages({ controller }: { controller: FfInboundRequestController }) {
  const {
    isFulfillmentAdmin,
    busy,
    setBoxImportOpen,
    packagesExpanded,
    setPackagesExpanded,
    setCargoDialogOpen,
    setCargoError,
    sortingView,
    boxImportEnabled,
    receivingActive,
    catalogById,
    displayMetaByProductId,
    requestPrintInboundBox,
    requestPrintAllInboundBoxes,
    requestPrintInboundCargoPlace,
    requestPrintAllInboundCargoPlaces,
    openBoxAddDialog,
    handleCreateBox,
    deleteInboundBox,
    boxes,
    cargoPlaces,
  } = controller

  return (
    <>
          {isFulfillmentAdmin && !sortingView ? (
            <Accordion
              expanded={packagesExpanded}
              onChange={(_, expanded) => setPackagesExpanded(expanded)}
              sx={{ mt: 2, border: 1, borderColor: 'divider', boxShadow: 'none', '&:before': { display: 'none' } }}
              data-testid="ff-inbound-packages-accordion"
            >
              <AccordionSummary
                expandIcon={<ExpandMoreOutlined />}
                data-testid="ff-inbound-packages-toggle"
              >
                <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                    Короба и грузоместа
                  </Typography>
                  <Chip size="small" label={`Короба: ${boxes.length}`} />
                  <Chip size="small" label={`Грузоместа: ${cargoPlaces.length}`} />
                </Stack>
              </AccordionSummary>
              <AccordionDetails data-testid="ff-inbound-boxes-panel">
                <Stack spacing={1.5}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    spacing={1}
                    sx={{ alignItems: { sm: 'center' }, flexWrap: 'wrap' }}
                  >
                    <Button
                      variant="contained"
                      disabled={busy || !receivingActive}
                      onClick={() => void handleCreateBox()}
                      data-testid="ff-inbound-add-to-box"
                    >
                      Создать короба
                    </Button>
                    <Button
                      variant="contained"
                      disabled={busy || !receivingActive}
                      onClick={() => {
                        setCargoError(null)
                        setCargoDialogOpen(true)
                      }}
                      data-testid="ff-inbound-create-cargo-places"
                    >
                      Создать грузоместа
                    </Button>
                    {boxImportEnabled ? (
                      <Button
                        variant="outlined"
                        disabled={busy || !receivingActive}
                        onClick={() => setBoxImportOpen(true)}
                        data-testid="ff-inbound-import-boxes"
                      >
                        Загрузить по накладной
                      </Button>
                    ) : null}
                    <Button
                      variant="outlined"
                      disabled={busy || boxes.length === 0}
                      onClick={requestPrintAllInboundBoxes}
                      data-testid="ff-inbound-boxes-print-all"
                    >
                      Печать коробов
                    </Button>
                    <Button
                      variant="outlined"
                      disabled={busy || cargoPlaces.length === 0}
                      onClick={requestPrintAllInboundCargoPlaces}
                      data-testid="ff-inbound-cargo-places-print-all"
                    >
                      Печать грузомест
                    </Button>
                  </Stack>

                  <Stack spacing={1}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      Короба
                    </Typography>
                    {boxes.map((box) => {
                      const visibleLines = box.lines.filter((ln) => ln.quantity > 0)
                      return (
                        <Paper
                          key={box.id}
                          variant="outlined"
                          sx={{ overflow: 'hidden', bgcolor: 'background.paper' }}
                          data-testid="ff-inbound-box-row"
                        >
                          <Stack
                            direction={{ xs: 'column', sm: 'row' }}
                            spacing={1}
                            sx={{
                              alignItems: { sm: 'center' },
                              px: 1.25,
                              py: 1,
                              bgcolor: 'action.hover',
                              borderBottom: 1,
                              borderColor: 'divider',
                            }}
                            data-testid={`ff-inbound-box-header-${box.id}`}
                          >
                            <Typography variant="body2" sx={{ fontWeight: 700 }}>
                              Короб № {box.box_number}{' '}
                              <Typography component="code" variant="body2">
                                {box.internal_barcode}
                              </Typography>
                            </Typography>
                            <Box sx={{ flexGrow: 1 }} />
                            <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                              <Button
                                size="small"
                                variant="contained"
                                disabled={busy || !receivingActive}
                                onClick={() => openBoxAddDialog(box.id)}
                                data-testid={`ff-inbound-box-fill-${box.id}`}
                              >
                                Наполнить
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={busy || !receivingActive || visibleLines.length > 0}
                                onClick={() => void deleteInboundBox(box.id)}
                                data-testid={`ff-inbound-box-delete-${box.id}`}
                              >
                                Удалить
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                disabled={busy}
                                onClick={() => requestPrintInboundBox(box)}
                                data-testid={`ff-inbound-box-print-${box.id}`}
                              >
                                Печать
                              </Button>
                            </Stack>
                          </Stack>
                          {visibleLines.length > 0 ? (
                            <Stack spacing={0.75} sx={{ px: 1.25, py: 1, bgcolor: 'background.paper' }}>
                              {visibleLines.map((ln) => (
                                <InboundBoxContentLine
                                  key={ln.id}
                                  meta={
                                    displayMetaByProductId.get(ln.product_id) ??
                                    productDisplayMetaFromCatalog(ln.product_id, ln, catalogById)
                                  }
                                  quantity={ln.quantity}
                                />
                              ))}
                            </Stack>
                          ) : (
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{ px: 1.25, py: 1, bgcolor: 'background.paper' }}
                            >
                              Пока нет товаров
                            </Typography>
                          )}
                        </Paper>
                      )
                    })}
                  </Stack>

                  <Stack spacing={1}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>
                      Грузоместа
                    </Typography>
                    {cargoPlaces.map((place) => (
                      <Paper
                        key={place.id}
                        variant="outlined"
                        sx={{ px: 1.25, py: 1 }}
                        data-testid="ff-inbound-cargo-place-row"
                      >
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>
                            Грузоместо № {place.place_number}{' '}
                            <Typography component="code" variant="body2">
                              {place.internal_barcode}
                            </Typography>
                          </Typography>
                          <Box sx={{ flexGrow: 1 }} />
                          {place.label_printed_at ? (
                            <Chip size="small" color="success" label="Этикетка напечатана" />
                          ) : null}
                          <Button
                            size="small"
                            variant="outlined"
                            disabled={busy}
                            onClick={() => requestPrintInboundCargoPlace(place)}
                            data-testid={`ff-inbound-cargo-place-print-${place.id}`}
                          >
                            Печать
                          </Button>
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                </Stack>
              </AccordionDetails>
            </Accordion>
          ) : null}

    </>
  )
}
