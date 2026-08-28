import { useEffect, useMemo, useRef, useState } from 'react'
import { inboundOperationTypeReceptionLabel } from '../../utils/inboundOperationType'
import { buildInboundDiscrepancyLines, buildInboundReceivingTotals, isDoneStatus, isReceivingStatus, isSortingStatus } from './inboundReceivingHelpers'
import { formatHumanDocumentNumber } from './documentDisplay'
import { createSerialScanQueue } from './inboundReceivingRuntime'
import { type CellLocationHint, type DiscrepancyActDetail, type DistributionLineDraft, type FfInboundRequestViewProps, type InboundDetail, type InboundLine, type LocationRow, type WarehouseRow, type WbCatalogRow, inboundWorkspaceTitle } from './FfInboundRequestViewTypes'

export function useFfInboundRequestState({ token, workspace = 'full', onDirtyChange }: FfInboundRequestViewProps) {
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token])

  const [detail, setDetail] = useState<InboundDetail | null>(null)
  const [catalog, setCatalog] = useState<WbCatalogRow[] | null>(null)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actualDraftByLineId, setActualDraftByLineId] = useState<Record<string, string>>({})
  const [actualDraftErrorByLineId, setActualDraftErrorByLineId] = useState<Record<string, string>>({})
  const actualDraftRef = useRef(actualDraftByLineId)
  const actualInputRefs = useRef<Record<string, HTMLInputElement | null>>({})

  const [distOpen, setDistOpen] = useState(false)
  const [distBusy, setDistBusy] = useState(false)
  const [distError, setDistError] = useState<string | null>(null)
  const [distLines, setDistLines] = useState<DistributionLineDraft[]>([])
  const [cellHintsByProductId, setCellHintsByProductId] = useState<Record<string, CellLocationHint[]>>({})

  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerInitialSearch, setPickerInitialSearch] = useState('')
  const [dimensionsLine, setDimensionsLine] = useState<InboundLine | null>(null)
  const [dimensionDraft, setDimensionDraft] = useState({ length: '', width: '', height: '', weight: '' })
  const [dimensionError, setDimensionError] = useState<string | null>(null)
  const [returnAutoPrint, setReturnAutoPrint] = useState(false)

  const [plannedDateDraft, setPlannedDateDraft] = useState<string>('')
  const [manualEditLineId, setManualEditLineId] = useState<string | null>(null)
  const [boxAddDialogBoxId, setBoxAddDialogBoxId] = useState<string | null>(null)
  const [finishConfirmOpen, setFinishConfirmOpen] = useState(false)
  const [scanToastError, setScanToastError] = useState<string | null>(null)
  const [scanAddBarcode, setScanAddBarcode] = useState<string | null>(null)
  const [lastScannedLineId, setLastScannedLineId] = useState<string | null>(null)
  const [importSuccessMsg, setImportSuccessMsg] = useState<string | null>(null)
  const [boxImportOpen, setBoxImportOpen] = useState(false)
  const [packagesExpanded, setPackagesExpanded] = useState(false)
  const [cargoDialogOpen, setCargoDialogOpen] = useState(false)
  const [cargoCount, setCargoCount] = useState('1')
  const [cargoError, setCargoError] = useState<string | null>(null)
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false)
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null)
  const [newLocationCode, setNewLocationCode] = useState('')
  const [requestWarehouse, setRequestWarehouse] = useState<WarehouseRow | null>(null)
  const [linkedDiscrepancyActs, setLinkedDiscrepancyActs] = useState<DiscrepancyActDetail[]>([])
  const [discrepancyActsBusy, setDiscrepancyActsBusy] = useState(false)
  const [discrepancyActsError, setDiscrepancyActsError] = useState<string | null>(null)
  const loadDetailSeq = useRef(0)
  const receivingScanQueue = useRef(createSerialScanQueue()).current

  const sortingView = workspace === 'sorting'

  useEffect(() => {
    if (!sortingView) {
      onDirtyChange?.(false)
    }
    return () => onDirtyChange?.(false)
  }, [onDirtyChange, sortingView])
  const plannedDateFieldEnabled = false
  const waybillPrintEnabled = true
  const boxImportEnabled = false
  const documentDistributionEnabled = false
  const receptionClosed =
    detail != null && (isSortingStatus(detail.status) || isDoneStatus(detail.status))
  const receivingActive = detail != null && isReceivingStatus(detail.status)
  const waitingForFfStart = detail?.status === 'submitted'
  const sellerCreatedDraft = detail?.status === 'draft' && detail.created_by_seller_id != null
  const isReturnOperation = detail?.operation_type === 'return'
  const isOzonReturn = isReturnOperation && detail?.marketplace === 'ozon'
  const usesReturnShortcut = isReturnOperation && detail?.marketplace !== 'ozon'
  const operationTypeLabel = inboundOperationTypeReceptionLabel(detail?.operation_type)
  // На экране сортировки товары уже показаны интерактивными карточками
  // FfInboundSortingPanel; таблица «Состав приёмки» дублировала те же строки,
  // поэтому в режиме сортировки она намеренно скрыта (решение подтверждено
  // заказчиком 17.08.2026). На обычной приёмке таблица остаётся видна всегда.
  const showInboundLinesTable = !sortingView

  const defaultPutawayBoxId = useMemo(() => {
    const withQty = (detail?.boxes ?? []).filter((b) =>
      b.lines.some((ln) => ln.quantity > 0),
    )
    if (withQty.length === 1) {
      return withQty[0]!.id
    }
    return ''
  }, [detail?.boxes])

  const sortingRemainingTotal = useMemo(() => {
    if (!detail) return 0
    if (detail.sorting_remaining_qty != null) {
      return detail.sorting_remaining_qty
    }
    return detail.lines.reduce((sum, ln) => {
      const accepted = ln.actual_qty ?? 0
      return sum + Math.max(0, accepted - ln.posted_qty)
    }, 0)
  }, [detail])

  const processTitle = inboundWorkspaceTitle(workspace)
  const displayDocumentNumber = useMemo(
    () => formatHumanDocumentNumber(detail),
    [detail],
  )

  const receivingTotals = useMemo(
    () =>
      buildInboundReceivingTotals(
        detail?.lines ?? [],
        detail?.boxes ?? [],
        detail?.status,
        detail?.planned_box_count ?? null,
      ),
    [detail?.boxes, detail?.lines, detail?.planned_box_count, detail?.status],
  )

  const discrepancyLines = useMemo(
    () => buildInboundDiscrepancyLines(detail?.lines ?? [], detail?.boxes ?? [], detail?.status),
    [detail?.boxes, detail?.lines, detail?.status],
  )


  return {
    authHeaders,
    detail,
    setDetail,
    catalog,
    setCatalog,
    locations,
    setLocations,
    busy,
    setBusy,
    error,
    setError,
    actualDraftByLineId,
    setActualDraftByLineId,
    actualDraftErrorByLineId,
    setActualDraftErrorByLineId,
    actualDraftRef,
    actualInputRefs,
    distOpen,
    setDistOpen,
    distBusy,
    setDistBusy,
    distError,
    setDistError,
    distLines,
    setDistLines,
    cellHintsByProductId,
    setCellHintsByProductId,
    pickerOpen,
    setPickerOpen,
    pickerInitialSearch,
    setPickerInitialSearch,
    dimensionsLine,
    setDimensionsLine,
    dimensionDraft,
    setDimensionDraft,
    dimensionError,
    setDimensionError,
    returnAutoPrint,
    setReturnAutoPrint,
    plannedDateDraft,
    setPlannedDateDraft,
    manualEditLineId,
    setManualEditLineId,
    boxAddDialogBoxId,
    setBoxAddDialogBoxId,
    finishConfirmOpen,
    setFinishConfirmOpen,
    scanToastError,
    setScanToastError,
    scanAddBarcode,
    setScanAddBarcode,
    lastScannedLineId,
    setLastScannedLineId,
    importSuccessMsg,
    setImportSuccessMsg,
    boxImportOpen,
    setBoxImportOpen,
    packagesExpanded,
    setPackagesExpanded,
    cargoDialogOpen,
    setCargoDialogOpen,
    cargoCount,
    setCargoCount,
    cargoError,
    setCargoError,
    closeConfirmOpen,
    setCloseConfirmOpen,
    saveSuccessMsg,
    setSaveSuccessMsg,
    newLocationCode,
    setNewLocationCode,
    requestWarehouse,
    setRequestWarehouse,
    linkedDiscrepancyActs,
    setLinkedDiscrepancyActs,
    discrepancyActsBusy,
    setDiscrepancyActsBusy,
    discrepancyActsError,
    setDiscrepancyActsError,
    loadDetailSeq,
    receivingScanQueue,
    sortingView,
    plannedDateFieldEnabled,
    waybillPrintEnabled,
    boxImportEnabled,
    documentDistributionEnabled,
    receptionClosed,
    receivingActive,
    waitingForFfStart,
    sellerCreatedDraft,
    isReturnOperation,
    isOzonReturn,
    usesReturnShortcut,
    operationTypeLabel,
    showInboundLinesTable,
    defaultPutawayBoxId,
    sortingRemainingTotal,
    processTitle,
    displayDocumentNumber,
    receivingTotals,
    discrepancyLines,
  }
}

export type FfInboundRequestState = ReturnType<typeof useFfInboundRequestState>
