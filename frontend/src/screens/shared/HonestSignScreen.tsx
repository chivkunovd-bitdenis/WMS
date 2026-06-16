import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import UploadFileOutlined from '@mui/icons-material/UploadFileOutlined'
import { apiUrl } from '../../api'
import { PageHeader } from '../../ui/PageHeader'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

export type MarkingInventoryRow = {
  product_id: string
  sku_code: string
  product_name: string
  requires_honest_sign: boolean
  available_count: number
  printed_count: number
}

type Props = {
  token: string
  /** FF admin: filter by seller; seller portal: omit */
  sellerId?: string | null
  sellerIdRequiredForImport?: boolean
  sellers?: { id: string; name: string }[]
  selectedSellerId?: string | null
  onSelectedSellerIdChange?: (id: string | null) => void
  testIdPrefix?: string
}

export function HonestSignScreen({
  token,
  sellerId,
  sellerIdRequiredForImport = false,
  sellers = [],
  selectedSellerId = null,
  onSelectedSellerIdChange,
  testIdPrefix = 'honest-sign',
}: Props) {
  const [rows, setRows] = useState<MarkingInventoryRow[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [importMsg, setImportMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const effectiveSellerId = sellerId ?? selectedSellerId

  const authHeaders = {
    Authorization: `Bearer ${token}`,
  }

  const loadInventory = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const q =
        effectiveSellerId && !sellerId
          ? `?seller_id=${encodeURIComponent(effectiveSellerId)}`
          : sellerId
            ? ''
            : effectiveSellerId
              ? `?seller_id=${encodeURIComponent(effectiveSellerId)}`
              : ''
      const res = await fetch(apiUrl(`/operations/marking-codes/inventory${q}`), {
        headers: authHeaders,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      setRows((await res.json()) as MarkingInventoryRow[])
    } finally {
      setBusy(false)
    }
  }, [effectiveSellerId, sellerId, token])

  useEffect(() => {
    if (sellerIdRequiredForImport && !effectiveSellerId) {
      setRows([])
      return
    }
    void loadInventory()
  }, [effectiveSellerId, loadInventory, sellerIdRequiredForImport])

  const onPickFile = () => fileRef.current?.click()

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) {
      return
    }
    const importSellerId = sellerId ?? effectiveSellerId
    if (!importSellerId) {
      setError('Выберите селлера для загрузки кодов.')
      return
    }
    setBusy(true)
    setError(null)
    setImportMsg(null)
    try {
      const form = new FormData()
      form.append('file', file)
      if (sellerIdRequiredForImport) {
        form.append('seller_id', importSellerId)
      }
      const res = await fetch(apiUrl('/operations/marking-codes/import'), {
        method: 'POST',
        headers: authHeaders,
        body: form,
      })
      if (!res.ok) {
        setError(await readApiErrorMessage(res))
        return
      }
      const data = (await res.json()) as {
        accepted_count: number
        skipped_count: number
      }
      setImportMsg(
        `Загружено кодов: ${data.accepted_count}. Пропущено: ${data.skipped_count}.`,
      )
      await loadInventory()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack spacing={2} data-testid={`${testIdPrefix}-page`}>
      <PageHeader
        title="Честный знак"
        description="Загрузка кодов (CSV или PDF) и остатки по товарам с маркировкой."
      />
      {sellerIdRequiredForImport && sellers.length > 0 ? (
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Селлер:
          </Typography>
          {sellers.map((s) => (
            <Button
              key={s.id}
              size="small"
              variant={selectedSellerId === s.id ? 'contained' : 'outlined'}
              onClick={() => onSelectedSellerIdChange?.(s.id)}
              data-testid={`${testIdPrefix}-seller-${s.id}`}
            >
              {s.name}
            </Button>
          ))}
        </Stack>
      ) : null}
      {error ? (
        <Alert severity="error" data-testid={`${testIdPrefix}-error`}>
          {error}
        </Alert>
      ) : null}
      {importMsg ? (
        <Alert severity="success" data-testid={`${testIdPrefix}-import-success`}>
          {importMsg}
        </Alert>
      ) : null}
      <Box>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.txt,.tsv,.pdf"
          hidden
          data-testid={`${testIdPrefix}-file-input`}
          onChange={(ev) => void onFileChange(ev)}
        />
        <Button
          variant="contained"
          startIcon={<UploadFileOutlined />}
          disabled={busy || (sellerIdRequiredForImport && !effectiveSellerId)}
          onClick={onPickFile}
          data-testid={`${testIdPrefix}-upload`}
        >
          Загрузить коды (CSV / PDF)
        </Button>
      </Box>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small" data-testid={`${testIdPrefix}-inventory-table`}>
          <TableHead>
            <TableRow>
              <TableCell>Товар</TableCell>
              <TableCell>Артикул</TableCell>
              <TableCell align="right">Нужен ЧЗ</TableCell>
              <TableCell align="right">Доступно</TableCell>
              <TableCell align="right">Напечатано</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5}>
                  <Typography variant="body2" color="text.secondary">
                    {busy ? 'Загрузка…' : 'Нет данных по маркировке.'}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.product_id} data-testid={`${testIdPrefix}-row-${r.product_id}`}>
                  <TableCell>{r.product_name}</TableCell>
                  <TableCell>{r.sku_code}</TableCell>
                  <TableCell align="right">{r.requires_honest_sign ? 'Да' : 'Нет'}</TableCell>
                  <TableCell align="right">{r.available_count}</TableCell>
                  <TableCell align="right">{r.printed_count}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  )
}
