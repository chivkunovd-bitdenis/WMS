import { Alert, Box, Button, Chip, Divider, Drawer, IconButton, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/CloseOutlined'
import OpenInNewIcon from '@mui/icons-material/OpenInNewOutlined'
import { useStore } from '../state/store'
import { StatusChip, docKindLabel } from '../common/StatusChip'
import { Row } from '../common/Row'
import { fmtRelative, fmtTime } from '../utils/format'

const KIND_TO_MODULE: Record<string, string> = {
  inbound: 'Раздел «Приёмка»',
  mp_outbound: 'Раздел «Отгрузки»',
  fbs_batch: 'Раздел «FBS»',
  return: 'Раздел «Возвраты»',
}

export function DocumentPreviewDrawer() {
  const { ui, dispatch, documentById, sellerById, warehouseById, actorById } = useStore()

  const doc = ui.openDocumentId ? documentById.get(ui.openDocumentId) : null

  const close = () => dispatch({ type: 'open_document', documentId: null })

  const outdated = ui.demo.documentOutdated
  const permissionDenied = ui.demo.permissionDenied

  return (
    <Drawer
      anchor="right"
      open={!!ui.openDocumentId}
      onClose={close}
      slotProps={{ paper: { sx: { width: { xs: '100%', md: 520 } } } }}
      data-testid="doc-preview-drawer"
    >
      <Box sx={{ p: 2.5, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Row align="center" justify="space-between">
          <Stack>
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
              Предпросмотр документа
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Из чата документ только показываем. Все действия — в соответствующем разделе портала.
            </Typography>
          </Stack>
          <IconButton onClick={close} aria-label="Закрыть">
            <CloseIcon />
          </IconButton>
        </Row>
      </Box>

      {!doc ? (
        <Box sx={{ p: 3 }}>
          <Typography variant="body2">Документ не выбран.</Typography>
        </Box>
      ) : permissionDenied ? (
        <Box sx={{ p: 3 }}>
          <Alert severity="warning">Нет доступа к документу для текущей роли (403 в демо).</Alert>
        </Box>
      ) : doc.deleted ? (
        <Box sx={{ p: 3 }}>
          <Alert severity="error">Документ удалён. Ссылка недействительна.</Alert>
        </Box>
      ) : (
        <Stack sx={{ p: 2.5, gap: 2 }}>
          <Row align="center" spacing={1} wrap>
            <Typography variant="h6" sx={{ fontWeight: 800 }}>
              {docKindLabel(doc.kind)} · {doc.number}
            </Typography>
            <StatusChip status={doc.status} />
          </Row>
          {outdated ? (
            <Alert severity="warning">
              Документ обновился после отправки. Здесь версия на момент открытия.
            </Alert>
          ) : null}
          <Typography variant="body2" color="text.secondary">
            {doc.summary}
          </Typography>
          <Row spacing={1} wrap>
            {(() => {
              const seller = sellerById.get(doc.sellerId)
              const warehouse = warehouseById.get(doc.warehouseId)
              return (
                <>
                  {seller ? <Chip size="small" label={`Селлер · ${seller.brand}`} sx={{ bgcolor: 'action.hover' }} /> : null}
                  {warehouse ? <Chip size="small" label={`Склад · ${warehouse.name}`} sx={{ bgcolor: 'action.hover' }} /> : null}
                  <Chip size="small" label={`План ${doc.totalPlanned} шт`} sx={{ bgcolor: 'action.hover' }} />
                  <Chip size="small" label={`Факт ${doc.totalFact} шт`} sx={{ bgcolor: 'action.hover' }} />
                </>
              )
            })()}
          </Row>
          <Divider />
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
              Строки
            </Typography>
            <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Артикул</TableCell>
                    <TableCell>Наименование</TableCell>
                    <TableCell align="right">План</TableCell>
                    <TableCell align="right">Факт</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {doc.lines.map((l) => (
                    <TableRow key={l.sku}>
                      <TableCell sx={{ fontFamily: 'ui-monospace, monospace', fontWeight: 700 }}>{l.sku}</TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {l.name}
                        </Typography>
                        {l.note ? (
                          <Typography variant="caption" color="warning.main">
                            {l.note}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right">{l.planned}</TableCell>
                      <TableCell align="right">
                        {l.fact ?? '—'}
                        {l.fact != null && l.fact < l.planned ? (
                          <Typography variant="caption" color="error" sx={{ ml: 0.5 }}>
                            (−{l.planned - l.fact})
                          </Typography>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Box>
          <Divider />
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
              Таймлайн
            </Typography>
            <Stack spacing={0.75}>
              {doc.timeline.map((ev) => {
                const actor = actorById.get(ev.by)
                return (
                  <Box key={ev.id} sx={{ p: 1, borderRadius: 1.5, bgcolor: 'action.hover' }}>
                    <Typography variant="caption" color="text.secondary">
                      {fmtTime(ev.at)} · {actor?.name ?? '—'}
                    </Typography>
                    <Typography variant="body2">{ev.text}</Typography>
                  </Box>
                )
              })}
            </Stack>
          </Box>
          <Alert severity="info" icon={<OpenInNewIcon />}>
            Для действий над документом откройте {KIND_TO_MODULE[doc.kind] ?? 'нужный раздел портала'}.
            Из чата ничего не списывается и не переводится.
          </Alert>
          <Row justify="flex-end" spacing={1}>
            <Button variant="outlined" onClick={close}>
              Закрыть
            </Button>
            <Button variant="contained" startIcon={<OpenInNewIcon />} onClick={close}>
              Перейти в раздел (демо)
            </Button>
          </Row>
          <Typography variant="caption" color="text.secondary">
            Обновлено {fmtRelative(doc.updatedAt)} · создано {fmtRelative(doc.createdAt)}.
          </Typography>
        </Stack>
      )}
    </Drawer>
  )
}
