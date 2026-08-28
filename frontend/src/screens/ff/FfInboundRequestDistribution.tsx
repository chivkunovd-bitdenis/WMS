import PrintOutlined from '@mui/icons-material/PrintOutlined'
import { Alert, Box, Button, Chip, FormControl, IconButton, InputLabel, MenuItem, Paper, Select, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Tooltip, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { isSortingStatus } from './inboundReceivingHelpers'
import type { FfInboundRequestController } from './FfInboundRequestViewController'

export function FfInboundRequestDistribution({ controller }: { controller: FfInboundRequestController }) {
  if (!controller.detail) return null

  const {
    isFulfillmentAdmin,
    workspace,
    addressStorageEnabled,
    detail,
    locations,
    distOpen,
    distBusy,
    distError,
    distLines,
    setDistLines,
    cellHintsByProductId,
    newLocationCode,
    setNewLocationCode,
    requestWarehouse,
    sortingView,
    documentDistributionEnabled,
    defaultPutawayBoxId,
    createWarehouseLocation,
    loadCellHints,
    acceptedQtyByProductId,
    distributableProducts,
    distSumByProductId,
    noCellRemainingLines,
    hasNoCellPending,
    distributionCompleted,
    distributionEditable,
    canReopenDistribution,
    saveDistribution,
    reopenDistribution,
    completeDistribution,
    printDistributionLocationLabel,
  } = controller

  return (
    <>
          {isFulfillmentAdmin && !sortingView ? (
            <Box sx={{ mt: 2 }}>
              {workspace === 'reception' && isSortingStatus(detail.status) ? (
                <Alert severity="success" sx={{ mt: 2 }} data-testid="ff-inbound-moved-to-sorting">
                  {addressStorageEnabled
                    ? 'Приёмка завершена. Остаток принят на склад ФФ (зона «Сортировка»). Разложение по ячейкам — в разделе Сортировка.'
                    : 'Приёмка завершена. Остаток принят на склад ФФ (зона «Сортировка»).'}
                </Alert>
              ) : null}

              {documentDistributionEnabled &&
              addressStorageEnabled &&
              isSortingStatus(detail.status) &&
              workspace === 'full' ? (
                <Paper variant="outlined" sx={{ p: 2 }} data-testid="ff-inbound-admin-distribution">
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
                        Распределение по ячейкам
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {distributionCompleted
                          ? hasNoCellPending
                            ? 'Распределение зафиксировано без ячеек — товар остаётся в зоне сортировки. Откройте заново и разложите принятое.'
                            : 'Всё принятое разложено по ячейкам хранения.'
                          : 'Разложите принятое по ячейкам хранения. Можно частями: разложенное сразу доступно к резерву, пока не разложено всё — приёмка остаётся в этом разделе.'}
                      </Typography>
                      {requestWarehouse ? (
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          sx={{ mt: 0.5 }}
                          data-testid="ff-inbound-distribution-warehouse"
                        >
                          Склад этой заявки:{' '}
                          <strong>
                            {requestWarehouse.name} ({requestWarehouse.code})
                          </strong>
                          . В списке «Ячейка» — только ячейки этого склада (
                          {locations.length === 0
                            ? 'пока нет'
                            : locations.map((l) => l.code).join(', ')}
                          ).
                        </Typography>
                      ) : null}
                    </Box>
                  </Stack>

                  {distError ? (
                    <Alert severity="error" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-error">
                      {distError}
                    </Alert>
                  ) : null}

                  {distributionCompleted && hasNoCellPending ? (
                    <Alert severity="warning" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-stuck-empty">
                      Распределение зафиксировано, но принятый товар не разложен по ячейкам — в разделе{' '}
                      <strong>Каталог</strong> остатков не будет. Откройте распределение заново и укажите ячейки
                      для всего принятого количества.
                    </Alert>
                  ) : null}

                  {locations.length === 0 &&
                  !distributionCompleted &&
                  (distOpen || isSortingStatus(detail.status)) ? (
                    <Alert severity="warning" sx={{ mt: 2 }} data-testid="ff-inbound-distribution-no-locations">
                      <Typography variant="body2" sx={{ mb: 1 }}>
                        На складе этой заявки <strong>нет ячеек</strong> — поэтому список «Ячейка» пустой и
                        не открывается. Создайте ячейку здесь или в разделе{' '}
                        <strong>Ячейки</strong> (тот же склад).
                      </Typography>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                        <TextField
                          size="small"
                          label="Код новой ячейки"
                          value={newLocationCode}
                          onChange={(e) => setNewLocationCode(e.target.value)}
                          disabled={distBusy}
                          placeholder="A-01"
                          slotProps={{
                            htmlInput: { 'data-testid': 'ff-inbound-distribution-new-location-code' },
                          }}
                        />
                        <Button
                          variant="contained"
                          disabled={distBusy || !newLocationCode.trim()}
                          onClick={() => void createWarehouseLocation()}
                          data-testid="ff-inbound-distribution-create-location"
                        >
                          Создать ячейку
                        </Button>
                      </Stack>
                    </Alert>
                  ) : null}

                  {distOpen || distributionCompleted ? (
                    <Box sx={{ mt: 2 }}>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1.5, alignItems: { sm: 'center' } }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          Таблица распределения {distributionCompleted ? ' (зафиксировано)' : ''}
                        </Typography>
                        <Box sx={{ flexGrow: 1 }} />
                        {distributionEditable ? (
                          <>
                            <Button
                              variant="outlined"
                              disabled={distBusy}
                              onClick={() =>
                                setDistLines((prev) => [
                                  ...prev,
                                  {
                                    box_id: defaultPutawayBoxId,
                                    product_id: '',
                                    storage_location_id: '',
                                    quantity: '',
                                  },
                                ])
                              }
                              data-testid="ff-inbound-distribution-add-row"
                            >
                              Добавить строку
                            </Button>
                            <Button
                              variant="outlined"
                              disabled={distBusy}
                              onClick={() => void saveDistribution()}
                              data-testid="ff-inbound-distribution-save"
                            >
                              Сохранить
                            </Button>
                            <Button
                              variant="contained"
                              disabled={distBusy}
                              onClick={() => void completeDistribution()}
                              data-testid="ff-inbound-distribution-complete"
                            >
                              {hasNoCellPending ? 'Применить раскладку' : 'Завершить распределение'}
                            </Button>
                          </>
                        ) : canReopenDistribution ? (
                          <Button
                            variant="outlined"
                            color="warning"
                            disabled={distBusy}
                            onClick={() => void reopenDistribution()}
                            data-testid="ff-inbound-distribution-reopen"
                          >
                            Открыть распределение заново
                          </Button>
                        ) : null}
                      </Stack>

                      <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
                        <Table size="small" data-testid="ff-inbound-distribution-table">
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ width: 420 }}>Товар</TableCell>
                              <TableCell align="right" sx={{ width: 140 }}>Кол-во</TableCell>
                              <TableCell sx={{ width: 260 }}>Ячейка</TableCell>
                              {distributionEditable ? <TableCell align="right" sx={{ width: 84 }} /> : null}
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {distLines.map((row, idx) => {
                              const accepted = acceptedQtyByProductId.get(row.product_id) ?? 0
                              const usedOther = (distSumByProductId.get(row.product_id) ?? 0) - (Math.floor(Number(row.quantity)) || 0)
                              const maxForRow = Math.max(accepted - usedOther, 0)
                              return (
                                <TableRow key={idx} data-testid="ff-inbound-distribution-row">
                                  <TableCell>
                                    <FormControl size="small" fullWidth>
                                      <InputLabel id={`ff-dist-prod-${idx}`}>Товар</InputLabel>
                                      <Select
                                        labelId={`ff-dist-prod-${idx}`}
                                        label="Товар"
                                        value={row.product_id}
                                        disabled={distBusy || !distributionEditable}
                                        onChange={(e) => {
                                          const v = String(e.target.value)
                                          setDistLines((prev) =>
                                            prev.map((r, i) => (i === idx ? { ...r, product_id: v } : r)),
                                          )
                                          if (v) void loadCellHints(v)
                                        }}
                                        data-testid="ff-inbound-distribution-product"
                                      >
                                        <MenuItem value="">
                                          <em>Выберите товар</em>
                                        </MenuItem>
                                        {distributableProducts.map((p) => (
                                          <MenuItem key={p.product_id} value={p.product_id}>
                                            {p.sku_code} · {p.product_name} (принято {p.accepted_qty})
                                          </MenuItem>
                                        ))}
                                      </Select>
                                    </FormControl>
                                  </TableCell>
                                  <TableCell align="right">
                                    <TextField
                                      type="number"
                                      size="small"
                                      value={row.quantity}
                                      disabled={distBusy || !distributionEditable}
                                      onChange={(e) =>
                                        setDistLines((prev) =>
                                          prev.map((r, i) => (i === idx ? { ...r, quantity: e.target.value } : r)),
                                        )
                                      }
                                      slotProps={{ htmlInput: { min: 1, max: maxForRow, 'data-testid': 'ff-inbound-distribution-qty' } }}
                                    />
                                  </TableCell>
                                  <TableCell>
                                    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                                      <FormControl size="small" sx={{ flexGrow: 1 }}>
                                        <InputLabel id={`ff-dist-loc-${idx}`}>Ячейка</InputLabel>
                                        <Select
                                          labelId={`ff-dist-loc-${idx}`}
                                          label="Ячейка"
                                          value={row.storage_location_id}
                                          disabled={distBusy || !distributionEditable || locations.length === 0}
                                          onChange={(e) => {
                                            const v = String(e.target.value)
                                            setDistLines((prev) =>
                                              prev.map((r, i) =>
                                                i === idx ? { ...r, storage_location_id: v } : r,
                                              ),
                                            )
                                          }}
                                          data-testid="ff-inbound-distribution-location"
                                        >
                                          <MenuItem value="">
                                            <em>Выберите ячейку</em>
                                          </MenuItem>
                                          {locations.map((loc) => (
                                            <MenuItem key={loc.id} value={loc.id}>
                                              <Box>
                                                <Typography variant="body2" component="span">
                                                  {loc.code}
                                                </Typography>
                                                <Typography
                                                  variant="caption"
                                                  color="text.secondary"
                                                  component="div"
                                                >
                                                  {loc.barcode}
                                                </Typography>
                                              </Box>
                                            </MenuItem>
                                          ))}
                                        </Select>
                                      </FormControl>
                                      {row.storage_location_id ? (
                                        <Tooltip title="Печать ШК ячейки">
                                          <span>
                                            <IconButton
                                              size="small"
                                              aria-label="Печать ШК ячейки"
                                              disabled={distBusy || !distributionEditable}
                                              onClick={() =>
                                                printDistributionLocationLabel(row.storage_location_id)
                                              }
                                              data-testid="ff-inbound-distribution-location-print"
                                            >
                                              <PrintOutlined fontSize="small" />
                                            </IconButton>
                                          </span>
                                        </Tooltip>
                                      ) : null}
                                    </Stack>
                                    {row.product_id && (cellHintsByProductId[row.product_id]?.length ?? 0) > 0 ? (
                                      <Stack
                                        direction="row"
                                        spacing={0.5}
                                        sx={{ mt: 0.75, flexWrap: 'wrap' }}
                                        data-testid="ff-inbound-cell-hints"
                                      >
                                        <Typography
                                          variant="caption"
                                          color="text.secondary"
                                          sx={{ alignSelf: 'center', mr: 0.5 }}
                                        >
                                          Уже лежит:
                                        </Typography>
                                        {cellHintsByProductId[row.product_id]!.map((h) => (
                                          <Chip
                                            key={h.storage_location_id}
                                            size="small"
                                            variant="outlined"
                                            label={`${h.storage_location_code} (${h.available})`}
                                            disabled={distBusy || !distributionEditable}
                                            onClick={() => {
                                              setDistLines((prev) =>
                                                prev.map((r, i) =>
                                                  i === idx
                                                    ? { ...r, storage_location_id: h.storage_location_id }
                                                    : r,
                                                ),
                                              )
                                            }}
                                            data-testid="ff-inbound-cell-hint"
                                          />
                                        ))}
                                      </Stack>
                                    ) : null}
                                  </TableCell>
                                  {distributionEditable ? (
                                    <TableCell align="right">
                                      <Button
                                        variant="text"
                                        color="error"
                                        disabled={distBusy}
                                        onClick={() => setDistLines((prev) => prev.filter((_, i) => i !== idx))}
                                        data-testid="ff-inbound-distribution-remove-row"
                                      >
                                        Удалить
                                      </Button>
                                    </TableCell>
                                  ) : null}
                                </TableRow>
                              )
                            })}
                            {distLines.length === 0 ? (
                              <TableRow>
                                <TableCell colSpan={distributionEditable ? 4 : 3}>
                                  <Typography variant="body2" color="text.secondary">
                                    Пока нет строк распределения.
                                  </Typography>
                                </TableCell>
                              </TableRow>
                            ) : null}
                          </TableBody>
                        </Table>
                      </TableContainer>

                      <Paper
                        variant="outlined"
                        sx={{
                          p: 2,
                          ...(hasNoCellPending
                            ? {
                                bgcolor: (theme) => alpha(theme.palette.warning.main, 0.14),
                                borderColor: (theme) => alpha(theme.palette.warning.main, 0.45),
                              }
                            : null),
                        }}
                        data-testid="ff-inbound-distribution-no-cell"
                        data-pending={hasNoCellPending ? '1' : '0'}
                      >
                        <Typography
                          variant="body2"
                          sx={{ fontWeight: 700, mb: 1 }}
                          color={hasNoCellPending ? 'warning.dark' : 'text.primary'}
                        >
                          Остаток «Без ячейки»
                        </Typography>
                        <Stack spacing={0.5}>
                          {noCellRemainingLines.map((p) => (
                            <Typography
                              key={p.product_id}
                              variant="body2"
                              color="warning.dark"
                              data-testid="ff-inbound-distribution-no-cell-line"
                            >
                              {p.sku_code} · {p.product_name}: {p.remaining}
                            </Typography>
                          ))}
                          {!hasNoCellPending ? (
                            <Typography variant="body2" color="text.secondary">
                              Остатков нет.
                            </Typography>
                          ) : null}
                        </Stack>
                      </Paper>
                    </Box>
                  ) : null}
                </Paper>
              ) : null}
            </Box>
          ) : null}

    </>
  )
}
