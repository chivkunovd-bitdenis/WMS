import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { apiUrl } from '../../api'
import { useAuth } from '../../hooks/useAuth'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import { ProfileLoadingScreen } from '../../screens/ProfileLoadingScreen'
import { PublicAuthScreen } from '../../screens/PublicAuthScreen'
import { SellerDocumentsScreen } from '../../screens/v2/SellerDocumentsScreen'
import { SellerInboundDraftScreen } from '../../screens/v2/SellerInboundDraftScreen'
import { SellerProductsStockScreen } from '../../screens/v2/SellerProductsStockScreen'
import { SellerSettingsScreen } from '../../screens/v2/SellerSettingsScreen'
import { SellerLayout } from './SellerLayout'

type InboundSummaryRow = {
  id: string
  status: string
  line_count: number
  planned_delivery_date: string | null
}

type OutboundSummaryRow = {
  id: string
  status: string
  line_count: number
}

type WarehouseRow = { id: string; name: string; code: string }

export function SellerApp() {
  const {
    token,
    me,
    error,
    loading,
    authBusy,
    pendingPasswordSetupEmail,
    onLogin,
    onSetInitialPassword,
    onCancelPasswordSetup,
    logout,
  } = useAuth('seller')

  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(
    null,
  )

  const [opsBusy, setOpsBusy] = useState(false)
  const [opsError, setOpsError] = useState<string | null>(null)
  const [inboundSummaries, setInboundSummaries] = useState<InboundSummaryRow[]>(
    [],
  )
  const [outboundSummaries, setOutboundSummaries] = useState<OutboundSummaryRow[]>(
    [],
  )

  const authHeaders = useCallback(
    (t: string) => ({ Authorization: `Bearer ${t}` }),
    [],
  )

  const refreshWarehouses = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/warehouses'), { headers: authHeaders(t) })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      const rows = (await res.json()) as WarehouseRow[]
      setWarehouses(rows)
      setSelectedWarehouseId((prev) => {
        if (rows.length === 0) return null
        if (prev && rows.some((w) => w.id === prev)) return prev
        return rows[0]!.id
      })
    },
    [authHeaders],
  )

  const refreshInboundList = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/operations/inbound-intake-requests'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setInboundSummaries((await res.json()) as InboundSummaryRow[])
    },
    [authHeaders],
  )

  const refreshOutboundList = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/operations/outbound-shipment-requests'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setOutboundSummaries((await res.json()) as OutboundSummaryRow[])
    },
    [authHeaders],
  )

  useEffect(() => {
    if (!token || !me) {
      setWarehouses([])
      setSelectedWarehouseId(null)
      setOpsBusy(false)
      setOpsError(null)
      setInboundSummaries([])
      setOutboundSummaries([])
      return
    }

    if (me.role !== 'fulfillment_seller') {
      window.location.assign('/')
      return
    }

    setOpsError(null)
    void (async () => {
      try {
        await refreshWarehouses(token)
        await refreshInboundList(token)
        await refreshOutboundList(token)
      } catch (e) {
        setOpsError(e instanceof Error ? e.message : 'Не удалось загрузить данные.')
      }
    })()
  }, [me, refreshInboundList, refreshOutboundList, refreshWarehouses, token])

  const rootElement = (() => {
    if (!token) {
      return (
        <PublicAuthScreen
          variant="seller"
          error={error}
          authBusy={authBusy}
          pendingPasswordSetupEmail={pendingPasswordSetupEmail}
          onRegister={(e) => e.preventDefault()}
          onLogin={(e) => void onLogin(e)}
          onSetInitialPassword={(e) => void onSetInitialPassword(e)}
          onCancelPasswordSetup={onCancelPasswordSetup}
        />
      )
    }
    if (token && !me) {
      return <ProfileLoadingScreen loading={loading} onLogout={() => logout()} />
    }
    if (!me) {
      return null
    }
    if (me.role !== 'fulfillment_seller') {
      return (
        <main className="shell" data-testid="seller-wrong-role">
          <p>Этот портал доступен только селлеру.</p>
          <button type="button" onClick={() => window.location.assign('/')}>
            Перейти в портал фулфилмента
          </button>
        </main>
      )
    }

    return (
      <SellerLayout
        onLogout={() => logout()}
        title="Портал селлера"
        userLabel={me.email}
        userRoleLabel={me.role}
      >
        <Routes>
          <Route path="/" element={<Navigate to="/documents" replace />} />
          <Route
            path="/documents"
            element={
              <SellerDocumentsScreen
                busy={opsBusy}
                error={opsError}
                inboundSummaries={inboundSummaries}
                outboundSummaries={outboundSummaries}
                onCreateCorrection={() =>
                  setOpsError(
                    'Акт расхождений: будет реализован отдельным документом на следующем этапе.',
                  )
                }
              />
            }
          />
          <Route
            path="/inbound/new"
            element={
              token ? (
                <SellerInboundDraftScreen
                  token={token}
                  authHeaders={authHeaders}
                  warehouseId={selectedWarehouseId ?? (warehouses[0]?.id ?? null)}
                  onRefreshInboundList={() =>
                    token ? refreshInboundList(token) : undefined
                  }
                />
              ) : null
            }
          />
          <Route
            path="/inbound/:requestId"
            element={
              token ? (
                <SellerInboundDraftScreen
                  token={token}
                  authHeaders={authHeaders}
                  warehouseId={selectedWarehouseId ?? (warehouses[0]?.id ?? null)}
                  onRefreshInboundList={() =>
                    token ? refreshInboundList(token) : undefined
                  }
                />
              ) : null
            }
          />
          <Route
            path="/products"
            element={
              token ? (
                <SellerProductsStockScreen token={token} authHeaders={authHeaders} />
              ) : null
            }
          />
          <Route
            path="/settings"
            element={
              token ? (
                <SellerSettingsScreen token={token} authHeaders={authHeaders} />
              ) : null
            }
          />
          <Route path="*" element={<Navigate to="/documents" replace />} />
        </Routes>
      </SellerLayout>
    )
  })()

  return (
    <Routes>
      <Route path="*" element={rootElement} />
    </Routes>
  )
}

