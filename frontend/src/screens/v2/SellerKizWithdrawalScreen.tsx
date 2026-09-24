import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  Link,
  Paper,
  Radio,
  RadioGroup,
  Snackbar,
  Stack,
  Switch,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  CloseOutlined,
  KeyOutlined,
  OpenInNewOutlined,
  RefreshOutlined,
  SearchOutlined,
} from '@mui/icons-material'

import {
  CryptoProCadesAdapter,
  CryptoProError,
  type CryptoProCertificate,
  type CryptoProReadiness,
  type DetachedDocumentSignature,
  type DetachedDocumentToSign,
} from '../../integrations/cryptoProCades'
import { loadCryptoProBrowserPlugin } from '../../integrations/loadCryptoProBrowserPlugin'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { getMoscowDateString } from '../../utils/moscowDate'
import {
  SameOriginSellerWithdrawalApi,
  type SellerWithdrawalApi,
  type WithdrawalCertificateBinding,
  type WithdrawalOperation,
  type WithdrawalOperationItem,
  type WithdrawalProductOption,
  type WithdrawalRow,
  withdrawalApiErrorMessage,
  withdrawalErrorMessage,
} from './sellerKizWithdrawalApi'
import {
  compactKiz,
  failedWithdrawalItems,
  getOrCreateClientRequest,
  isTerminalWithdrawalOperation,
  normalizeThumbprint,
  parsePendingRequest,
  sha256Base64Payload,
  shouldPollWithdrawalOperation,
} from './sellerKizWithdrawalState'

type AuthChallengeToSign = {
  challengeData: string
  certificateThumbprint: string
}

type AuthChallengeSignature = {
  signatureBase64: string
  certificateThumbprint: string
}

export interface WithdrawalSigningAdapter {
  checkReadiness(): Promise<CryptoProReadiness>
  listCertificates(): Promise<CryptoProCertificate[]>
  signAttachedAuthChallenge(input: AuthChallengeToSign): Promise<AuthChallengeSignature>
  signDetachedDocument(input: DetachedDocumentToSign): Promise<DetachedDocumentSignature>
}

type Props = {
  token: string
  sellerId: string
  api?: SellerWithdrawalApi
  signingAdapter?: WithdrawalSigningAdapter
  pluginLoader?: () => Promise<void>
  routeBase?: string
}

type OperationFailure = WithdrawalOperationItem & { operationId: string; attempt: number }

const statusView = {
  not_withdrawn: { label: 'Не выведен', color: 'warning' as const },
  withdrawn: { label: 'Выведен', color: 'success' as const },
  error: { label: 'Ошибка', color: 'error' as const },
}

const formatDate = (value: string): string =>
  new Intl.DateTimeFormat('ru-RU').format(new Date(value))

const daysBefore = (date: string, days: number): string => {
  const value = new Date(`${date}T12:00:00+03:00`)
  value.setUTCDate(value.getUTCDate() - days)
  return value.toISOString().slice(0, 10)
}

const certificateName = (subject: string): string => {
  const match = subject.match(/(?:^|,\s*)CN=([^,]+)/i)
  return match?.[1]?.trim() || subject
}

const shortThumbprint = (thumbprint: string): string => {
  const value = normalizeThumbprint(thumbprint)
  return value.length <= 16 ? value : `${value.slice(0, 8)}…${value.slice(-8)}`
}

const certificateBinding = (certificate: CryptoProCertificate): WithdrawalCertificateBinding => ({
  thumbprint: normalizeThumbprint(certificate.thumbprint),
  expires_at: certificate.validTo,
  subject: certificate.subject,
  issuer: certificate.issuer,
})

const createUuid = (): string => globalThis.crypto.randomUUID()

const storageKeys = (sellerId: string) => ({
  operation: `wms517:withdrawal:operation:${sellerId}`,
  request: `wms517:withdrawal:request:${sellerId}`,
})

const safeStorageGet = (key: string): string | null => {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

const safeStorageSet = (key: string, value: string): void => {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // The durable source is the backend. Storage only accelerates tab recovery.
  }
}

const safeStorageRemove = (key: string): void => {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // Best-effort cleanup only.
  }
}

export function SellerHonestSignTabs({ active, routeBase = '/seller' }: { active: 'pools' | 'withdrawals'; routeBase?: string }) {
  const navigate = useNavigate()
  return (
    <Paper variant="outlined">
      <Tabs
        value={active}
        onChange={(_, value: 'pools' | 'withdrawals') =>
          navigate(value === 'pools' ? `${routeBase}/honest-sign` : `${routeBase}/honest-sign/withdrawals`)
        }
        aria-label="Разделы Честного знака"
        variant="scrollable"
        scrollButtons="auto"
      >
        <Tab value="pools" label="Пулы КИЗ" />
        <Tab value="withdrawals" label="Вывод из оборота" />
      </Tabs>
    </Paper>
  )
}

function RowStatus({ row }: { row: WithdrawalRow }) {
  const view = statusView[row.status]
  const detail = row.status === 'error' ? withdrawalErrorMessage(row.error) : ''
  return (
    <Stack spacing={0.25} sx={{ minWidth: 116 }}>
      <Chip size="small" color={view.color} label={view.label} sx={{ alignSelf: 'flex-start', height: 22 }} />
      {detail ? (
        <Typography variant="caption" color="error.dark" sx={{ lineHeight: 1.2 }}>
          {detail}
        </Typography>
      ) : null}
    </Stack>
  )
}

export function SellerKizWithdrawalScreen({
  token,
  sellerId,
  api: apiOverride,
  signingAdapter: signingAdapterOverride,
  pluginLoader,
  routeBase = '/seller',
}: Props) {
  const defaultApi = useMemo(() => new SameOriginSellerWithdrawalApi(token), [token])
  const defaultSigningAdapter = useMemo(() => new CryptoProCadesAdapter(), [])
  const api = apiOverride ?? defaultApi
  const signingAdapter = signingAdapterOverride ?? defaultSigningAdapter
  const loadPlugin = useMemo(
    () => pluginLoader ?? (signingAdapterOverride ? async () => undefined : loadCryptoProBrowserPlugin),
    [pluginLoader, signingAdapterOverride],
  )
  const keys = useMemo(() => storageKeys(sellerId), [sellerId])
  const today = useMemo(() => getMoscowDateString(), [])

  const [dateFrom, setDateFrom] = useState(() => daysBefore(today, 6))
  const [dateTo, setDateTo] = useState(today)
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebouncedValue(query, 300)
  const [productSearch, setProductSearch] = useState('')
  const debouncedProductSearch = useDebouncedValue(productSearch, 300)
  const [productId, setProductId] = useState<string | null>(null)
  const [onlyNotWithdrawn, setOnlyNotWithdrawn] = useState(true)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState<50 | 100 | 250>(50)
  const [rows, setRows] = useState<WithdrawalRow[]>([])
  const [total, setTotal] = useState(0)
  const [products, setProducts] = useState<WithdrawalProductOption[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [details, setDetails] = useState<WithdrawalRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [readiness, setReadiness] = useState<CryptoProReadiness | null>(null)
  const [readinessError, setReadinessError] = useState('')
  const [certificateOpen, setCertificateOpen] = useState(false)
  const [certificatesLoading, setCertificatesLoading] = useState(false)
  const [certificates, setCertificates] = useState<CryptoProCertificate[]>([])
  const [selectedCertificateThumbprint, setSelectedCertificateThumbprint] = useState('')
  const [certificateError, setCertificateError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [activeOperationId, setActiveOperationId] = useState<string | null>(null)
  const [retryTarget, setRetryTarget] = useState<{ operationId: string; attempt: number } | null>(null)
  const [failedItems, setFailedItems] = useState<OperationFailure[]>([])
  const [toast, setToast] = useState('')

  const selectedRows = useMemo(
    () => rows.filter((row) => selected.includes(row.row_id) && row.status !== 'withdrawn'),
    [rows, selected],
  )
  const eligibleIds = useMemo(
    () => rows.filter((row) => row.status !== 'withdrawn').map((row) => row.row_id),
    [rows],
  )
  const allVisibleSelected =
    eligibleIds.length > 0 && eligibleIds.every((rowId) => selected.includes(rowId))
  const someVisibleSelected =
    eligibleIds.some((rowId) => selected.includes(rowId)) && !allVisibleSelected

  const refreshRegistry = useCallback(async (signal?: AbortSignal) => {
    const response = await api.list(
      {
        dateFrom,
        dateTo,
        search: debouncedQuery,
        productId,
        onlyNotWithdrawn,
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      },
      signal,
    )
    setRows(response.rows)
    setTotal(response.total)
  }, [api, dateFrom, dateTo, debouncedQuery, onlyNotWithdrawn, page, productId, rowsPerPage])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setPageError('')
    void refreshRegistry(controller.signal)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setPageError(withdrawalApiErrorMessage(error))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [refreshRegistry])

  useEffect(() => {
    const controller = new AbortController()
    void api.listProducts(debouncedProductSearch, controller.signal)
      .then(setProducts)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setPageError(withdrawalApiErrorMessage(error))
        }
      })
    return () => controller.abort()
  }, [api, debouncedProductSearch])

  useEffect(() => {
    let cancelled = false
    setReadinessError('')
    void loadPlugin()
      .then(() => signingAdapter.checkReadiness())
      .then((value) => {
        if (!cancelled) setReadiness(value)
      })
      .catch((error: unknown) => {
        if (!cancelled) setReadinessError(withdrawalApiErrorMessage(error))
      })
    return () => {
      cancelled = true
    }
  }, [loadPlugin, signingAdapter])

  useEffect(() => {
    const maxPage = Math.max(0, Math.ceil(total / rowsPerPage) - 1)
    if (page > maxPage) {
      setPage(maxPage)
      setSelected([])
    }
  }, [page, rowsPerPage, total])

  const applyTerminalOperation = useCallback((operation: WithdrawalOperation) => {
    const failures = failedWithdrawalItems(operation).map((item) => ({
      ...item,
      operationId: operation.operation_id,
      attempt: operation.attempt,
    }))
    const succeeded = operation.items.filter((item) => item.status === 'withdrawn').length
    setFailedItems(failures)
    if (succeeded > 0) {
      setToast(
        failures.length > 0
          ? `Выведено: ${succeeded}. Ошибок: ${failures.length}`
          : `КИЗ выведены из оборота: ${succeeded}`,
      )
    } else if (operation.auth_error) {
      setPageError(withdrawalErrorMessage(operation.auth_error))
    }
    setActiveOperationId(null)
    safeStorageRemove(keys.operation)
    safeStorageRemove(keys.request)
    void refreshRegistry().catch((error: unknown) => setPageError(withdrawalApiErrorMessage(error)))
  }, [keys.operation, keys.request, refreshRegistry])

  useEffect(() => {
    const storedOperationId = safeStorageGet(keys.operation)
    setActiveOperationId(storedOperationId)
  }, [keys.operation])

  useEffect(() => {
    if (!activeOperationId) return
    const controller = new AbortController()
    let timerId: number | undefined
    const read = async () => {
      try {
        const operation = await api.getOperation(activeOperationId, controller.signal)
        if (isTerminalWithdrawalOperation(operation)) {
          applyTerminalOperation(operation)
          return
        }
        if (shouldPollWithdrawalOperation(operation)) {
          timerId = window.setTimeout(() => void read(), 3_000)
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setPageError(withdrawalApiErrorMessage(error))
      }
    }
    void read()
    return () => {
      controller.abort()
      if (timerId !== undefined) window.clearTimeout(timerId)
    }
  }, [activeOperationId, api, applyTerminalOperation])

  const resetSelectionAndPage = () => {
    setSelected([])
    setPage(0)
  }

  const toggleAllVisible = () => {
    setSelected(allVisibleSelected ? [] : eligibleIds)
  }

  const openCertificateDialog = async (retry?: { operationId: string; attempt: number }) => {
    setRetryTarget(retry ?? null)
    setCertificateOpen(true)
    setCertificatesLoading(true)
    setCertificateError('')
    setSelectedCertificateThumbprint('')
    try {
      const available = await signingAdapter.listCertificates()
      setCertificates(available)
      if (available.length === 0) setCertificateError('На компьютере не найден действующий сертификат с закрытым ключом.')
    } catch (error) {
      setCertificates([])
      setCertificateError(withdrawalApiErrorMessage(error))
    } finally {
      setCertificatesLoading(false)
    }
  }

  const closeCertificate = () => {
    if (submitting) return
    setCertificateOpen(false)
    setCertificateError('')
    setSelectedCertificateThumbprint('')
    setRetryTarget(null)
  }

  const rememberOperation = (operation: WithdrawalOperation) => {
    safeStorageSet(keys.operation, operation.operation_id)
    setActiveOperationId(operation.operation_id)
  }

  const startOrResumeOperation = async (
    certificate: CryptoProCertificate,
  ): Promise<WithdrawalOperation> => {
    const binding = certificateBinding(certificate)
    if (retryTarget) {
      return api.retryOperation({
        operationId: retryTarget.operationId,
        expectedAttempt: retryTarget.attempt,
        certificate: binding,
      })
    }

    const operationIds = new Set(
      selectedRows.map((row) => row.operation_id).filter((value): value is string => Boolean(value)),
    )
    if (operationIds.size === 1 && selectedRows.every((row) => row.operation_id)) {
      const operation = await api.getOperation([...operationIds][0])
      if (operation.state === 'failed' || operation.state === 'partial_failed') {
        return api.retryOperation({
          operationId: operation.operation_id,
          expectedAttempt: operation.attempt,
          certificate: binding,
        })
      }
      return operation
    }

    const rowIds = selectedRows.map((row) => row.row_id)
    const pending = getOrCreateClientRequest(
      rowIds,
      parsePendingRequest(safeStorageGet(keys.request)),
      createUuid,
    )
    safeStorageSet(keys.request, JSON.stringify(pending))
    return api.createOperation({
      rowIds,
      clientRequestId: pending.clientRequestId,
      certificate: binding,
    })
  }

  const submitOperation = async () => {
    if (submitting) return
    const certificate = certificates.find(
      (candidate) => normalizeThumbprint(candidate.thumbprint) === normalizeThumbprint(selectedCertificateThumbprint),
    )
    if (!certificate) return
    setSubmitting(true)
    setCertificateError('')
    try {
      let operation = await startOrResumeOperation(certificate)
      rememberOperation(operation)

      if (isTerminalWithdrawalOperation(operation)) {
        setCertificateOpen(false)
        applyTerminalOperation(operation)
        return
      }
      if (operation.integration_gate) {
        throw new Error(
          'Подписание авторизации Честного знака пока закрыто: браузерный профиль подписи не подтверждён.',
        )
      }

      if (operation.auth_challenge) {
        const signedAuth = await signingAdapter.signAttachedAuthChallenge({
          challengeData: operation.auth_challenge.data,
          certificateThumbprint: certificate.thumbprint,
        })
        if (
          normalizeThumbprint(signedAuth.certificateThumbprint) !==
          normalizeThumbprint(certificate.thumbprint)
        ) {
          throw new CryptoProError('certificate_not_found')
        }
        operation = await api.submitAuthSignature({
          operationId: operation.operation_id,
          thumbprint: certificate.thumbprint,
          signature: signedAuth.signatureBase64,
          challengeUuid: operation.auth_challenge.uuid,
          expectedAttempt: operation.attempt,
        })
        rememberOperation(operation)
      }

      if (isTerminalWithdrawalOperation(operation)) {
        setCertificateOpen(false)
        applyTerminalOperation(operation)
        return
      }
      if (operation.documents.length === 0) {
        throw new Error('Честный знак не подготовил документы для подписи. Повторите позже.')
      }

      const signatures = []
      for (const document of operation.documents) {
        if (
          normalizeThumbprint(document.thumbprint) !== normalizeThumbprint(certificate.thumbprint)
        ) {
          throw new CryptoProError('certificate_not_found')
        }
        const payloadHash = await sha256Base64Payload(document.payload_base64)
        if (payloadHash !== document.payload_sha256.toLowerCase()) {
          throw new Error('Данные документа изменились до подписи. Операция остановлена.')
        }
        const signed = await signingAdapter.signDetachedDocument({
          payloadBase64: document.payload_base64,
          certificateThumbprint: certificate.thumbprint,
        })
        if (
          normalizeThumbprint(signed.certificateThumbprint) !==
          normalizeThumbprint(certificate.thumbprint)
        ) {
          throw new CryptoProError('certificate_not_found')
        }
        signatures.push({
          document_id: document.document_id,
          payload_sha256: document.payload_sha256,
          thumbprint: certificate.thumbprint,
          signature: signed.signatureBase64,
        })
      }

      operation = await api.submitDocumentSignatures({
        operationId: operation.operation_id,
        documents: signatures,
      })
      rememberOperation(operation)
      setSelected([])
      setCertificateOpen(false)
      setSelectedCertificateThumbprint('')
      setRetryTarget(null)
      safeStorageRemove(keys.request)
      if (isTerminalWithdrawalOperation(operation)) applyTerminalOperation(operation)
      else void refreshRegistry().catch((error: unknown) => setPageError(withdrawalApiErrorMessage(error)))
    } catch (error) {
      setCertificateError(withdrawalApiErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  const retryFailure = () => {
    const operationIds = new Set(failedItems.map((item) => item.operationId))
    const attempts = new Set(failedItems.map((item) => item.attempt))
    if (operationIds.size !== 1 || attempts.size !== 1) return
    const retry = { operationId: [...operationIds][0], attempt: [...attempts][0] }
    setFailedItems([])
    void openCertificateDialog(retry)
  }

  const retryAvailable =
    new Set(failedItems.map((item) => item.operationId)).size === 1 &&
    new Set(failedItems.map((item) => item.attempt)).size === 1

  return (
    <Stack spacing={2.5} sx={{ minWidth: 0, maxWidth: '100%' }} data-testid="seller-kiz-withdrawal-page">
      <SellerHonestSignTabs active="withdrawals" routeBase={routeBase} />

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { md: 'flex-start' } }}>
        <Box>
          <Typography variant="overline" color="text.secondary">Честный знак</Typography>
          <Typography variant="h5">Вывод КИЗ из оборота</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, maxWidth: 760 }}>
            Только КИЗ FBS-заказов, по которым в WMS уже зафиксирована передача Wildberries. Период считается по дате передачи.
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={loading ? <CircularProgress size={16} /> : <RefreshOutlined />}
          disabled={loading}
          onClick={() => void refreshRegistry().catch((error: unknown) => setPageError(withdrawalApiErrorMessage(error)))}
        >
          Обновить
        </Button>
      </Stack>

      {pageError ? <Alert severity="error" onClose={() => setPageError('')}>{pageError}</Alert> : null}
      {readinessError ? <Alert severity="warning">{readinessError}</Alert> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1.5} sx={{ alignItems: { lg: 'center' } }}>
            <TextField
              size="small"
              label="Передано WB с"
              type="date"
              value={dateFrom}
              onChange={(event) => { setDateFrom(event.target.value); resetSelectionAndPage() }}
              slotProps={{ inputLabel: { shrink: true } }}
              sx={{ minWidth: 168 }}
            />
            <TextField
              size="small"
              label="по"
              type="date"
              value={dateTo}
              onChange={(event) => { setDateTo(event.target.value); resetSelectionAndPage() }}
              slotProps={{ inputLabel: { shrink: true } }}
              sx={{ minWidth: 168 }}
            />
            <Autocomplete
              size="small"
              options={products}
              value={products.find((option) => option.id === productId) ?? null}
              onChange={(_, value) => { setProductId(value?.id ?? null); resetSelectionAndPage() }}
              onInputChange={(_, value, reason) => {
                if (reason === 'input' || reason === 'clear') setProductSearch(value)
              }}
              getOptionLabel={(option) => `${option.name} · ${option.sku}`}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              renderInput={(params) => <TextField {...params} label="Товар" />}
              noOptionsText="Товары не найдены"
              sx={{ width: { xs: '100%', lg: 'auto' }, flex: { xs: '0 0 auto', lg: '1 1 240px' }, minWidth: 0 }}
            />
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ alignItems: { md: 'center' } }}>
            <TextField
              size="small"
              value={query}
              onChange={(event) => { setQuery(event.target.value); resetSelectionAndPage() }}
              label="Поиск"
              placeholder="КИЗ, заказ, артикул или товар"
              slotProps={{ input: { startAdornment: <SearchOutlined color="action" sx={{ mr: 1 }} /> } }}
              sx={{ flex: 1 }}
            />
            <FormControlLabel
              control={(
                <Switch
                  checked={onlyNotWithdrawn}
                  onChange={(event) => { setOnlyNotWithdrawn(event.target.checked); resetSelectionAndPage() }}
                />
              )}
              label="Только не выведенные"
            />
          </Stack>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ minWidth: 0, overflow: 'hidden' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={0.5} sx={{ px: 1.5, py: 1, justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>Найдено: {total}</Typography>
          <Typography variant="caption" color="text.secondary">Выбор действует только на текущей странице</Typography>
        </Stack>
        <Divider />
        <TableContainer sx={{ maxWidth: '100%', maxHeight: { xs: '62vh', md: 560 }, overflow: 'auto' }}>
          <Table stickyHeader size="small" aria-label="КИЗ для вывода из оборота" sx={{ minWidth: 980, '& .MuiTableCell-root': { py: 0.5, px: 1, fontSize: '0.78rem' } }}>
            <TableHead sx={{ '& .MuiTableCell-head': { bgcolor: 'background.paper', zIndex: 3 } }}>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={allVisibleSelected}
                    indeterminate={someVisibleSelected}
                    disabled={eligibleIds.length === 0}
                    onChange={toggleAllVisible}
                    slotProps={{ input: { 'aria-label': 'Выбрать все доступные КИЗ на текущей странице' } }}
                  />
                </TableCell>
                <TableCell sx={{ width: 112, whiteSpace: 'nowrap' }}>Передано WB</TableCell>
                <TableCell sx={{ width: 122, whiteSpace: 'nowrap' }}>Заказ WB</TableCell>
                <TableCell sx={{ minWidth: 176, whiteSpace: 'nowrap' }}>Артикул</TableCell>
                <TableCell sx={{ minWidth: 230 }}>Наименование</TableCell>
                <TableCell sx={{ minWidth: 205, whiteSpace: 'nowrap' }}>КИЗ</TableCell>
                <TableCell sx={{ minWidth: 150 }}>Статус</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={7} sx={{ py: 5, textAlign: 'center' }}><CircularProgress size={28} /></TableCell></TableRow>
              ) : rows.length === 0 ? (
                <TableRow><TableCell colSpan={7} sx={{ py: 5, textAlign: 'center' }}>
                  <Typography variant="subtitle2">По выбранным фильтрам ничего не найдено</Typography>
                </TableCell></TableRow>
              ) : rows.map((row) => {
                const eligible = row.status !== 'withdrawn'
                const checked = selected.includes(row.row_id)
                return (
                  <TableRow key={row.row_id} hover selected={checked}>
                    <TableCell padding="checkbox">
                      <Tooltip title={eligible ? 'Выбрать КИЗ' : 'КИЗ уже выведен'}>
                        <span>
                          <Checkbox
                            checked={checked}
                            disabled={!eligible}
                            onChange={() => setSelected((current) => checked ? current.filter((id) => id !== row.row_id) : [...current, row.row_id])}
                            slotProps={{ input: { 'aria-label': `Выбрать КИЗ товара ${row.product_name}` } }}
                          />
                        </span>
                      </Tooltip>
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(row.delivered_at)}</TableCell>
                    <TableCell>
                      <Link component="button" type="button" underline="hover" onClick={() => setDetails(row)} sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25, whiteSpace: 'nowrap', fontSize: '0.78rem' }}>
                        {row.wb_order_id}<OpenInNewOutlined sx={{ fontSize: 13 }} />
                      </Link>
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{row.sku}</TableCell>
                    <TableCell><Typography variant="caption" sx={{ display: 'block', lineHeight: 1.25 }}>{row.product_name}</Typography></TableCell>
                    <TableCell>
                      <Tooltip title="Полный КИЗ доступен в деталях заказа">
                        <Typography component="code" variant="body2" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', overflowWrap: 'anywhere' }}>{compactKiz(row.cis)}</Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell><RowStatus row={row} /></TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={(_, nextPage) => { setPage(nextPage); setSelected([]) }}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(event) => { setRowsPerPage(Number(event.target.value) as 50 | 100 | 250); setPage(0); setSelected([]) }}
          rowsPerPageOptions={[50, 100, 250]}
          labelRowsPerPage="На странице"
          labelDisplayedRows={({ from, to, count }) => `${from}–${to} из ${count}`}
          sx={{ '& .MuiTablePagination-toolbar': { minHeight: 44, flexWrap: 'wrap', justifyContent: 'flex-end' } }}
        />
      </Paper>

      <Paper variant="outlined" sx={{ position: 'sticky', bottom: 12, zIndex: 2, p: 1.5, boxShadow: '0 10px 30px rgba(15,23,42,.14)' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
          <Typography variant="subtitle2">Выбрано КИЗ: {selectedRows.length}</Typography>
          <Tooltip title={readinessError || ''} disableHoverListener={!readinessError}>
            <span>
              <Button
                variant="contained"
                disabled={selectedRows.length === 0 || Boolean(readinessError) || !readiness}
                onClick={() => void openCertificateDialog()}
                startIcon={<KeyOutlined />}
              >
                Вывести из оборота ({selectedRows.length})
              </Button>
            </span>
          </Tooltip>
        </Stack>
      </Paper>

      <Dialog open={Boolean(details)} onClose={() => setDetails(null)} fullWidth maxWidth="sm" aria-labelledby="withdrawal-details-title">
        {details ? <>
          <DialogTitle id="withdrawal-details-title" sx={{ pr: 6 }}>
            Заказ WB № {details.wb_order_id}
            <IconButton aria-label="Закрыть" onClick={() => setDetails(null)} sx={{ position: 'absolute', right: 12, top: 12 }}><CloseOutlined /></IconButton>
          </DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <Chip variant="outlined" label={`Передано WB ${formatDate(details.delivered_at)}`} sx={{ alignSelf: 'flex-start' }} />
              <Box><Typography variant="caption" color="text.secondary">Товар</Typography><Typography>{details.product_name}</Typography><Typography variant="body2" color="text.secondary">{details.sku}</Typography></Box>
              <Box><Typography variant="caption" color="text.secondary">Привязанный КИЗ</Typography><Typography component="code" sx={{ display: 'block', overflowWrap: 'anywhere' }}>{details.cis}</Typography></Box>
              <Divider />
              <RowStatus row={details} />
            </Stack>
          </DialogContent>
          <DialogActions><Button onClick={() => setDetails(null)}>Закрыть</Button></DialogActions>
        </> : null}
      </Dialog>

      <Dialog open={certificateOpen} onClose={closeCertificate} fullWidth maxWidth="sm" aria-labelledby="certificate-dialog-title">
        <DialogTitle id="certificate-dialog-title" sx={{ pr: 6 }}>
          Выберите сертификат
          <IconButton aria-label="Закрыть" disabled={submitting} onClick={closeCertificate} sx={{ position: 'absolute', right: 12, top: 12 }}><CloseOutlined /></IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            {certificatesLoading ? <Box sx={{ py: 3, textAlign: 'center' }}><CircularProgress size={28} /></Box> : null}
            {!certificatesLoading ? (
              <RadioGroup value={selectedCertificateThumbprint} onChange={(event) => setSelectedCertificateThumbprint(event.target.value)}>
                {certificates.map((certificate) => (
                  <Paper key={certificate.thumbprint} variant="outlined" sx={{ mb: 1, px: 1.5, py: 1 }}>
                    <FormControlLabel
                      value={certificate.thumbprint}
                      control={<Radio />}
                      sx={{ m: 0, width: '100%', alignItems: 'flex-start' }}
                      label={(
                        <Box sx={{ pt: 0.5, minWidth: 0 }}>
                          <Typography variant="subtitle2">{certificateName(certificate.subject)}</Typography>
                          <Typography variant="body2" color="text.secondary">Выдан: {certificate.issuer}</Typography>
                          <Typography variant="caption" color="text.secondary">До {formatDate(certificate.validTo)} · {shortThumbprint(certificate.thumbprint)}</Typography>
                        </Box>
                      )}
                    />
                  </Paper>
                ))}
              </RadioGroup>
            ) : null}
            {certificateError ? <Alert severity="error">{certificateError}</Alert> : null}
            <Typography variant="body2" color="text.secondary">Закрытый ключ и PIN остаются на этом компьютере.</Typography>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, py: 2 }}>
          <Button disabled={submitting} onClick={closeCertificate}>Отмена</Button>
          <Button
            variant="contained"
            disabled={!selectedCertificateThumbprint || submitting || certificatesLoading}
            startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <KeyOutlined />}
            onClick={() => void submitOperation()}
          >
            {submitting ? 'Подписываем и отправляем…' : 'Подписать и отправить'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={failedItems.length > 0} onClose={() => setFailedItems([])} fullWidth maxWidth="md" aria-labelledby="withdrawal-error-dialog-title">
        <DialogTitle id="withdrawal-error-dialog-title" sx={{ pr: 6 }}>
          Не удалось вывести часть КИЗ
          <IconButton aria-label="Закрыть" onClick={() => setFailedItems([])} sx={{ position: 'absolute', right: 12, top: 12 }}><CloseOutlined /></IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ p: { xs: 1, sm: 2 } }}>
          <TableContainer sx={{ maxWidth: '100%', overflowX: 'auto' }}>
            <Table size="small" aria-label="Ошибки вывода из оборота" sx={{ minWidth: 680 }}>
              <TableHead><TableRow><TableCell>КИЗ</TableCell><TableCell>Заказ WB</TableCell><TableCell>Причина</TableCell></TableRow></TableHead>
              <TableBody>
                {failedItems.map((item) => (
                  <TableRow key={`${item.operationId}:${item.row_id}`}>
                    <TableCell><Tooltip title={item.cis}><Typography component="code" variant="caption" sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{compactKiz(item.cis)}</Typography></Tooltip></TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>№ {item.wb_order_id}</TableCell>
                    <TableCell>{withdrawalErrorMessage(item.error) || 'Причина не передана'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFailedItems([])}>Закрыть</Button>
          {retryAvailable ? <Button variant="contained" onClick={retryFailure}>Повторить</Button> : null}
        </DialogActions>
      </Dialog>

      <Snackbar open={Boolean(toast)} autoHideDuration={3200} onClose={() => setToast('')} message={toast} />
    </Stack>
  )
}
