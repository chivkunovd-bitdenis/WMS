import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from '../../api'
import {
  ActionGroup,
  DataTable,
  ErrorNotice,
  PrimaryAction,
  SecondaryAction,
} from '../../ui-kit'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'

type TariffServiceState = { service_code: string; enabled: boolean }
type TariffMatrix = { revision: number; services: TariffServiceState[] }

type Props = {
  token: string
  authHeaders: (token: string) => Record<string, string>
  focusTariffs: boolean
  onSaved: () => void
}

const serviceName: Record<string, string> = {
  inbound: 'Приёмка',
  marketplace_outbound: 'Отгрузка',
  packing: 'Упаковка',
  return: 'Возврат',
}

export function FfBillingTariffMatrixPanel({ token, authHeaders, focusTariffs, onSaved }: Props) {
  const [matrix, setMatrix] = useState<TariffMatrix | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const anchorRef = useRef<HTMLElement>(null)

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(apiUrl('/billing/tariff-matrix'), { headers: authHeaders(token) })
      if (!response.ok) throw new Error(await readApiErrorMessage(response))
      setMatrix((await response.json()) as TariffMatrix)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить тарифы.')
    } finally {
      setLoading(false)
    }
  }, [authHeaders, token])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    if (!focusTariffs) return
    anchorRef.current?.scrollIntoView({ block: 'start' })
    anchorRef.current?.focus()
  }, [focusTariffs, loading, matrix])

  async function save() {
    if (!matrix) return
    setSaving(true)
    setError(null)
    try {
      const response = await fetch(apiUrl('/billing/tariff-matrix'), {
        method: 'PUT',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: matrix.revision, services: matrix.services, versions: [] }),
      })
      if (!response.ok) throw new Error(await readApiErrorMessage(response))
      setMatrix((await response.json()) as TariffMatrix)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить тарифы.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section ref={anchorRef} id="ff-settings-tariffs-panel" tabIndex={-1} data-testid="ff-settings-tariffs-panel">
      {error ? <ErrorNotice testId="ff-settings-tariffs-error">{error}</ErrorNotice> : null}
      <DataTable
        columns={[
          { key: 'service', header: 'Услуга', width: 220, render: (row) => serviceName[row.service_code] ?? row.service_code },
          { key: 'state', header: 'Состояние', width: 190, render: (row) => row.enabled ? 'Тарифицируется' : 'Не тарифицируется' },
          {
            key: 'action', header: 'Действие', width: 180,
            render: (row) => (
              <SecondaryAction
                aria-pressed={row.enabled}
                disabledReason={saving ? 'Матрица тарифов сохраняется' : undefined}
                onClick={() => setMatrix((current) => current ? {
                  ...current,
                  services: current.services.map((item) => item.service_code === row.service_code ? { ...item, enabled: !item.enabled } : item),
                } : current)}
                data-testid={`ff-settings-tariff-${row.service_code}`}
              >
                {row.enabled ? 'Выключить' : 'Включить'}
              </SecondaryAction>
            ),
          },
        ]}
        rows={matrix?.services ?? []}
        getRowKey={(row) => row.service_code}
        loading={loading}
        empty={{ title: 'Тарифы пока не настроены', hint: 'Сначала загрузите матрицу тарифов.' }}
        testId="ff-settings-tariffs-services"
      />
      <ActionGroup>
        <PrimaryAction
          disabledReason={saving || !matrix ? 'Матрица тарифов ещё не загружена' : undefined}
          onClick={() => void save()}
          data-testid="ff-settings-tariffs-save"
        >
          {saving ? 'Сохранение' : 'Сохранить'}
        </PrimaryAction>
      </ActionGroup>
    </section>
  )
}
