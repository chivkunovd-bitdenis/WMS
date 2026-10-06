import { useEffect, useRef, useState } from 'react'
import { Checkbox, FormControlLabel } from '@mui/material'
import { apiUrl } from '../../api'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type Documents = {
  version: number; state: string; absence_selected?: boolean; errors?: string[]
  products: { exemplars: {
    gtd_required: boolean; rnpt_required: boolean; is_gtd_absent?: boolean; is_rnpt_absent?: boolean
  }[] }[]
}
const pending = (data: Documents) => ['preparing', 'checking', 'unknown'].includes(data.state)
function selected(data: Documents): boolean {
  if (data.absence_selected !== undefined) return data.absence_selected
  const required = data.products.flatMap(product => product.exemplars)
    .filter(exemplar => exemplar.gtd_required || exemplar.rnpt_required)
  return required.length > 0 && required.every(exemplar =>
    (!exemplar.gtd_required || exemplar.is_gtd_absent === true)
    && (!exemplar.rnpt_required || exemplar.is_rnpt_absent === true))
}

export function OzonDocumentsAbsence({ orderIds, token, authHeaders, onError }: {
  orderIds: string[]; token: string; authHeaders: (token: string) => Record<string, string>
  onError: (error: string | null) => void
}) {
  const [documents, setDocuments] = useState<Record<string, Documents>>({})
  const [busy, setBusy] = useState(true)
  const active = useRef(true)
  const working = useRef(false)
  const generation = useRef(0)
  const current = useRef(documents)
  current.current = documents
  const ids = orderIds.join(',')
  const read = useRef<(method: string, id: string, version?: number) => Promise<Documents>>(undefined)
  read.current = async (method, id, version) => {
    const response = await fetch(apiUrl(`/operations/fbs-orders/${id}/ozon-exemplar-documents${method === 'POST' ? '/absent' : ''}`), {
      method, headers: { ...authHeaders(token), ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}) },
      ...(method === 'POST' ? { body: JSON.stringify({ expected_version: version }) } : {}),
    })
    if (!response.ok) throw new Error(await readApiErrorMessage(response))
    return await response.json() as Documents
  }
  function retain(id: string, data: Documents) {
    if (!active.current) return
    current.current = { ...current.current, [id]: data }
    setDocuments(current.current)
    if (data.errors?.length) onError(data.errors.join('; '))
    else if (pending(data)) onError('Результат Ozon пока неизвестен')
  }
  useEffect(() => {
    active.current = true
    const scope = ++generation.current
    const exactIds = ids.split(',').filter(Boolean)
    void (async () => {
      try {
        for (const id of exactIds) {
          const data = await read.current!('GET', id)
          if (!active.current || scope !== generation.current) return
          retain(id, data)
        }
      } catch (error) {
        if (active.current) onError(error instanceof Error ? error.message : String(error))
      } finally { if (active.current) setBusy(false) }
    })()
    return () => { active.current = false; generation.current += 1 }
    // The supply-specific component key replaces this reader when the context changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids])
  const checked = orderIds.length > 0 && orderIds.every(id => documents[id] && selected(documents[id]))
  const partial = !checked && orderIds.some(id => documents[id] && selected(documents[id]))
  const unresolved = Object.values(documents).some(pending)
  useEffect(() => {
    if (!unresolved) return
    const timer = window.setInterval(() => {
      if (working.current) return
      working.current = true
      void (async () => {
        try {
          for (const id of orderIds) if (current.current[id] && pending(current.current[id])) {
            retain(id, await read.current!('GET', id))
          }
        } catch (error) {
          if (active.current) onError(error instanceof Error ? error.message : String(error))
        } finally { working.current = false }
      })()
    }, 5000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unresolved, ids])
  async function choose() {
    if (working.current || busy) return
    const scope = generation.current
    working.current = true
    setBusy(true)
    onError(null)
    try {
      for (const id of orderIds) {
        let data = current.current[id]
        if (!data) { data = await read.current!('GET', id); retain(id, data) }
        if (!active.current || scope !== generation.current) return
        if (pending(data) || selected(data)) {
          retain(id, await read.current!('GET', id))
          continue
        }
        try {
          const result = await read.current!('POST', id, data.version)
          if (!active.current || scope !== generation.current) return
          retain(id, result)
        }
        catch (error) {
          // A lost HTTP result cannot authorize a second write. Recover the saved intent by GET.
          try { retain(id, await read.current!('GET', id)) } catch { /* Preserve the original failure. */ }
          throw error
        }
      }
    } catch (error) {
      if (active.current) onError(error instanceof Error ? error.message : String(error))
    } finally {
      working.current = false
      if (active.current) setBusy(false)
    }
  }
  return <FormControlLabel label="Без ГТД и РНПТ" control={<Checkbox
    checked={checked} indeterminate={partial} disabled={busy || orderIds.length === 0}
    onChange={(_, enabled) => { if (enabled) void choose() }}
  />} />
}
