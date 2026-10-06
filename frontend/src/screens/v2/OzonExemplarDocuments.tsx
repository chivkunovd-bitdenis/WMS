import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Alert, Box, Button, Checkbox, Collapse, FormControlLabel, Stack, TextField, Typography } from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Exemplar = {
  exemplar_id: number; ordinal: number; gtd_required: boolean; rnpt_required: boolean
  gtd?: string | null; rnpt?: string | null; is_gtd_absent?: boolean; is_rnpt_absent?: boolean
  state: string; errors: string[]
}
type Documents = {
  version: number; state: string; editable?: boolean; status?: string | null; errors?: string[]
  products: { product_id: number; sku: string; name: string; exemplars: Exemplar[] }[]
}
type Choice = { gtd: string; rnpt: string; is_gtd_absent: boolean; is_rnpt_absent: boolean }
const stateLabel: Record<string, string> = {
  preparing: 'Подготавливается', checking: 'Проверяется в Ozon', unknown: 'Результат Ozon пока неизвестен',
  accepted: 'Принято', rejected: 'Ozon отклонил сведения', editable: 'Можно изменить сведения',
}

export function OzonExemplarDocuments({ orderId, token, authHeaders }: {
  orderId: string; token: string; authHeaders: (token: string) => Record<string, string>
}) {
  const [expanded, setExpanded] = useState(false)
  const [data, setData] = useState<Documents | null>(null)
  const [drafts, setDrafts] = useState<Record<string, Choice>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestBusy = useRef(false)
  const mounted = useRef(true)
  const generation = useRef(0)
  const dirty = useRef(new Set<string>())
  const path = `/operations/fbs-orders/${orderId}/ozon-exemplar-documents`
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; generation.current += 1 }
  }, [orderId])

  async function request(method: string, body?: unknown, suffix = '') {
    if (requestBusy.current) return
    requestBusy.current = true
    const requestGeneration = generation.current
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(apiUrl(path + suffix), {
        method, headers: { ...authHeaders(token), ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      })
      if (!response.ok) throw new Error(await readApiErrorMessage(response))
      const next = await response.json() as Documents
      if (!mounted.current || requestGeneration !== generation.current) return
      setData(next)
      setDrafts((previous) => {
        const drafts = { ...previous }
        for (const product of next.products) for (const exemplar of product.exemplars) {
          const key = `${product.product_id}:${exemplar.exemplar_id}`
          if (!dirty.current.has(key)) drafts[key] = {
            gtd: exemplar.gtd ?? '', rnpt: exemplar.rnpt ?? '',
            is_gtd_absent: exemplar.is_gtd_absent === true, is_rnpt_absent: exemplar.is_rnpt_absent === true,
          }
        }
        return drafts
      })
    } catch (exc) {
      if (body && typeof body === 'object' && 'product_id' in body && 'exemplar_id' in body) dirty.current.add(`${body.product_id}:${body.exemplar_id}`)
      if (mounted.current && requestGeneration === generation.current) setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      requestBusy.current = false
      if (mounted.current && requestGeneration === generation.current) setBusy(false)
    }
  }
  const pending = data && ['preparing', 'checking', 'unknown'].includes(data.state)
  // Current cabinet checks can outlive a completed write; the server decides
  // whether another explicit action is allowed. Keep the legacy mock fallback.
  const writeBlocked = data?.editable === false || (Boolean(pending) && data?.editable !== true)
  useEffect(() => {
    if (!expanded || !pending) return
    const timer = window.setInterval(() => { void request('GET') }, 5000)
    return () => window.clearInterval(timer)
  })
  function change(key: string, value: Partial<Choice>) {
    dirty.current.add(key)
    setDrafts((current) => ({ ...current, [key]: { ...current[key], ...value } }))
  }
  return <Box data-testid={`ozon-documents-${orderId}`} sx={{ minWidth: 0, width: '100%', mt: 0.5 }}>
    <Button size="small" onClick={() => {
      setExpanded(!expanded)
      if (!expanded && !data) void request('GET')
    }}>ГТД / РНПТ</Button>
    <Collapse in={expanded}>
      <Stack spacing={1} sx={{ py: 1 }}>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {data ? <Typography variant="caption">{stateLabel[data.state] ?? 'Результат Ozon пока неизвестен'}{data.status === 'update_not_available' ? ' · Ozon не разрешает редактирование' : ''}</Typography> : null}
        {data?.errors?.length ? <Typography color="error" variant="caption">{data.errors.join('; ')}</Typography> : null}
        {data?.products.length === 0 || (!data && error) ? <>
          <Typography variant="caption">Ozon ещё не вернул экземпляры.</Typography>
          <Button disabled={busy || writeBlocked} onClick={() => void request('POST', undefined, '/prepare')}>Получить экземпляры</Button>
        </> : null}
        {data?.products.map((product) => <Stack key={product.product_id} spacing={1}>
          <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{product.name} · SKU {product.sku}</Typography>
          {product.exemplars.map((exemplar) => {
            if (!exemplar.gtd_required && !exemplar.rnpt_required) return null
            const key = `${product.product_id}:${exemplar.exemplar_id}`
            const choice = drafts[key] ?? { gtd: exemplar.gtd ?? '', rnpt: exemplar.rnpt ?? '', is_gtd_absent: exemplar.is_gtd_absent === true, is_rnpt_absent: exemplar.is_rnpt_absent === true }
            const disabled = busy || writeBlocked
            return <Stack key={exemplar.exemplar_id} spacing={0.5} sx={{ pl: 1, borderLeft: 1, borderColor: 'divider' }}>
              <Typography variant="caption">Экземпляр {exemplar.ordinal}</Typography>
              {(['gtd', 'rnpt'] as const).map((doc) => {
                if (!(doc === 'gtd' ? exemplar.gtd_required : exemplar.rnpt_required)) return null
                const name = doc === 'gtd' ? 'ГТД' : 'РНПТ'
                const absentKey = doc === 'gtd' ? 'is_gtd_absent' : 'is_rnpt_absent'
                const context = ` · SKU ${product.sku} · экземпляр ${exemplar.ordinal}`
                return <Stack key={doc} direction={{ xs: 'column', lg: 'row' }} spacing={1} sx={{ alignItems: { lg: 'center' } }}>
                  <TextField size="small" fullWidth label={`Номер ${name}`} value={choice[doc]} disabled={disabled || choice[absentKey]}
                    slotProps={{ htmlInput: { 'aria-label': `Номер ${name}${context}`, onInput: (event: FormEvent<HTMLInputElement>) => change(key, { [doc]: (event.target as HTMLInputElement).value, [absentKey]: false }) } }}
                    onChange={(event) => change(key, { [doc]: event.target.value, [absentKey]: false })} />
                  <FormControlLabel sx={{ flexShrink: 0 }} label={`Номера ${name} нет`} control={<Checkbox checked={choice[absentKey]} disabled={disabled}
                    slotProps={{ input: { 'aria-label': `Номера ${name} нет${context}` } }}
                    onChange={(_, checked) => change(key, { [absentKey]: checked, ...(checked ? { [doc]: '' } : {}) })} />} />
                </Stack>
              })}
              {exemplar.errors?.length ? <Typography variant="caption" color="error" sx={{ overflowWrap: 'anywhere' }}>{exemplar.errors.join('; ')}</Typography> : null}
              <Box><Button size="small" aria-label={`Сохранить ГТД / РНПТ · SKU ${product.sku} · экземпляр ${exemplar.ordinal}`} disabled={disabled || !dirty.current.has(key)} onClick={() => {
                dirty.current.delete(key)
                void request('PUT', { product_id: product.product_id, exemplar_id: exemplar.exemplar_id,
                  gtd: choice.gtd || null, is_gtd_absent: choice.is_gtd_absent,
                  rnpt: choice.rnpt || null, is_rnpt_absent: choice.is_rnpt_absent, expected_version: data.version })
              }}>Сохранить</Button></Box>
            </Stack>
          })}
        </Stack>)}
        {data ? <Box><Button size="small" disabled={busy} onClick={() => void request('GET')}>Проверить в Ozon</Button></Box> : null}
      </Stack>
    </Collapse>
  </Box>
}
