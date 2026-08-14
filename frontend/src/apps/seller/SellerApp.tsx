import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Alert } from '@mui/material'
import { apiUrl } from '../../api'
import { useAuth } from '../../hooks/useAuth'
import { readApiErrorMessage } from '../../utils/readApiErrorMessage'
import {
  firstAllowedSellerPath,
  resolveSellerPermissions,
} from '../../utils/sellerPermissions'
import { ProfileLoadingScreen } from '../../screens/ProfileLoadingScreen'
import { PublicAuthScreen } from '../../screens/PublicAuthScreen'
import { SellerDocumentsScreen } from '../../screens/v2/SellerDocumentsScreen'
import { SellerInboundDraftScreen } from '../../screens/v2/SellerInboundDraftScreen'
import { SellerProductsStockScreen } from '../../screens/v2/SellerProductsStockScreen'
import { SellerHonestSignScreen } from '../../screens/v2/SellerHonestSignScreen'
import { SellerSettingsScreen } from '../../screens/v2/SellerSettingsScreen'
import { NotificationsPage } from '../../screens/shared/NotificationsPage'
import { SellerLayout } from './SellerLayout'

type InboundSummaryRow = {
  id: string
  waybill_number?: string | null
  warehouse_id: string
  warehouse_name?: string | null
  status: string
  operation_type?: string | null
  line_count: number
  goods_qty_total?: number
  planned_delivery_date: string | null
  planned_box_count?: number | null
}

type WarehouseRow = { id: string; name: string; code: string }

type SellerAppProps = {
  navigationBasePath?: string
}

export function SellerApp({ navigationBasePath = '' }: SellerAppProps) {
  const {
    token,
    me,
    error,
    portalMismatch,
    loading,
    authBusy,
    pendingPasswordSetupEmail,
    onLogin,
    onSetInitialPassword,
    onCancelPasswordSetup,
    logout,
    applyToken,
    reloadMe,
  } = useAuth('seller')

  const [shopsBusy, setShopsBusy] = useState(false)

  const [warehouses, setWarehouses] = useState<WarehouseRow[]>([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<string | null>(
    null,
  )

  const [opsBusy, setOpsBusy] = useState(false)
  const [opsError, setOpsError] = useState<string | null>(null)
  const [inboundSummaries, setInboundSummaries] = useState<InboundSummaryRow[]>(
    [],
  )
  const [mpUnloadSummaries, setMpUnloadSummaries] = useState<
    {
      id: string
      status: string
      line_count: number
      goods_qty_total?: number
      warehouse_id?: string
      warehouse_name?: string | null
      planned_shipment_date?: string | null
      created_at?: string
    }[]
  >([])

  const authHeaders = useCallback(
    (t: string) => ({ Authorization: `Bearer ${t}` }),
    [],
  )
  const sellerPath = useCallback(
    (path: string) => `${navigationBasePath}${path}`,
    [navigationBasePath],
  )

  useEffect(() => {
    const previousTitle = document.title
    document.title = 'WMS · Селлер'
    return () => {
      document.title = previousTitle
    }
  }, [])

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

  const refreshMpUnloadList = useCallback(
    async (t: string) => {
      const res = await fetch(apiUrl('/operations/marketplace-unload-requests'), {
        headers: authHeaders(t),
      })
      if (!res.ok) {
        throw new Error(await readApiErrorMessage(res))
      }
      setMpUnloadSummaries((await res.json()) as typeof mpUnloadSummaries)
    },
    [authHeaders],
  )

  const refreshAllOps = useCallback(
    async (t: string) => {
      await refreshWarehouses(t)
      await refreshInboundList(t)
      await refreshMpUnloadList(t)
    },
    [refreshInboundList, refreshMpUnloadList, refreshWarehouses],
  )

  const handleToggleShop = useCallback(
    async (sellerId: string, enabled: boolean) => {
      if (!token || !me?.can_manage_seller_shops) {
        return
      }
      const currentEnabled = (me.delegatable_shops ?? [])
        .filter((s) => s.enabled)
        .map((s) => s.id)
      const nextEnabled = enabled
        ? [...new Set([...currentEnabled, sellerId])]
        : currentEnabled.filter((id) => id !== sellerId)
      setShopsBusy(true)
      setOpsError(null)
      try {
        const res = await fetch(apiUrl('/auth/seller-shops'), {
          method: 'PUT',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ enabled_seller_ids: nextEnabled }),
        })
        if (!res.ok) {
          setOpsError(await readApiErrorMessage(res))
          return
        }
        await reloadMe()
      } catch (e) {
        setOpsError(
          e instanceof Error ? e.message : 'Не удалось обновить список магазинов.',
        )
      } finally {
        setShopsBusy(false)
      }
    },
    [authHeaders, me, reloadMe, token],
  )

  const handleSwitchShop = useCallback(
    async (sellerId: string | null) => {
      if (!token) {
        return
      }
      const homeId = me?.home_seller_id ?? me?.seller_id ?? null
      const targetId = sellerId ?? homeId
      if (!targetId || targetId === (me?.active_seller_id ?? me?.seller_id)) {
        return
      }
      setShopsBusy(true)
      setOpsError(null)
      try {
        const res = await fetch(apiUrl('/auth/switch-seller'), {
          method: 'POST',
          headers: {
            ...authHeaders(token),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            seller_id: sellerId,
          }),
        })
        if (!res.ok) {
          setOpsError(await readApiErrorMessage(res))
          return
        }
        const data = (await res.json()) as { access_token: string }
        applyToken(data.access_token)
        await reloadMe(data.access_token)
        await refreshAllOps(data.access_token)
      } catch (e) {
        setOpsError(
          e instanceof Error ? e.message : 'Не удалось переключить магазин.',
        )
      } finally {
        setShopsBusy(false)
      }
    },
    [applyToken, authHeaders, me, refreshAllOps, reloadMe, token],
  )

  useEffect(() => {
    if (!token || !me) {
      setWarehouses([])
      setSelectedWarehouseId(null)
      setOpsBusy(false)
      setOpsError(null)
      setInboundSummaries([])
      setMpUnloadSummaries([])
      return
    }

    setOpsError(null)
    void (async () => {
      try {
        await refreshWarehouses(token)
        await refreshInboundList(token)
        await refreshMpUnloadList(token)
      } catch (e) {
        setOpsError(e instanceof Error ? e.message : 'Не удалось загрузить данные.')
      }
    })()
  }, [me, refreshInboundList, refreshMpUnloadList, refreshWarehouses, token])

  const rootElement = (() => {
    if (!token) {
      return (
        <PublicAuthScreen
          variant="seller"
          error={portalMismatch ?? error}
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
    const catalogScopeKey = me.active_seller_id ?? me.seller_id ?? 'none'
    const sellerPermissions = resolveSellerPermissions(me.seller_permissions)
    const accessDenied = (
      <Alert severity="warning" data-testid="seller-access-denied">
        Нет доступа к этому разделу. Обратитесь к администратору селлера.
      </Alert>
    )
    return (
      <SellerLayout
        onLogout={() => logout()}
        title="Портал селлера"
        userLabel={me.email}
        userRoleLabel={
          me.active_seller_name && me.active_seller_name !== me.home_seller_name
            ? `${me.role} · ${me.active_seller_name}`
            : me.role
        }
        canManageSellerShops={Boolean(me.can_manage_seller_shops)}
        homeSellerId={me.home_seller_id ?? me.seller_id ?? null}
        activeSellerId={me.active_seller_id ?? me.seller_id ?? null}
        delegatableShops={me.delegatable_shops ?? []}
        switchableShops={me.switchable_shops ?? []}
        shopsBusy={shopsBusy}
        permissions={sellerPermissions}
        navigationBasePath={navigationBasePath}
        {...(me.can_manage_seller_shops ||
        (me.switchable_shops?.length ?? 0) > 1
          ? {
              onToggleShop: (sellerId: string, enabled: boolean) =>
                void handleToggleShop(sellerId, enabled),
              onSwitchShop: (sellerId: string | null) => void handleSwitchShop(sellerId),
            }
          : {})}
      >
        <Routes>
          <Route
            path="/"
            element={<Navigate to={sellerPath(firstAllowedSellerPath(sellerPermissions))} replace />}
          />
          <Route
            path="/documents"
            element={
              sellerPermissions.documents ? (
                <SellerDocumentsScreen
                  key={catalogScopeKey}
                  busy={opsBusy}
                  catalogScopeKey={catalogScopeKey}
                  error={opsError}
                  token={token}
                  authHeaders={authHeaders}
                  warehouseId={selectedWarehouseId ?? warehouses[0]?.id ?? null}
                  inboundSummaries={inboundSummaries}
                  mpUnloadSummaries={mpUnloadSummaries}
                  onRefreshInboundList={async () => {
                    if (token) {
                      await refreshInboundList(token)
                    }
                  }}
                  onCreateCorrection={() =>
                    setOpsError(
                      'Акт расхождений: будет реализован отдельным документом на следующем этапе.',
                    )
                  }
                  onCreateMpUnload={async () => {
                    if (!token) {
                      return null
                    }
                    const wid = selectedWarehouseId ?? warehouses[0]?.id
                    if (!wid) {
                      setOpsError('Склад ФФ не найден.')
                      return null
                    }
                    setOpsBusy(true)
                    setOpsError(null)
                    try {
                      const res = await fetch(
                        apiUrl('/operations/marketplace-unload-requests/seller'),
                        {
                          method: 'POST',
                          headers: {
                            ...authHeaders(token),
                            'Content-Type': 'application/json',
                          },
                          body: JSON.stringify({ warehouse_id: wid }),
                        },
                      )
                      if (!res.ok) {
                        setOpsError(await readApiErrorMessage(res))
                        return null
                      }
                      const created = (await res.json()) as { id: string }
                      await refreshMpUnloadList(token)
                      return created.id
                    } catch (e) {
                      setOpsError(
                        e instanceof Error ? e.message : 'Не удалось создать отгрузку на МП.',
                      )
                      return null
                    } finally {
                      setOpsBusy(false)
                    }
                  }}
                  onRefreshMpUnloadList={async () => {
                    if (token) {
                      await refreshMpUnloadList(token)
                    }
                  }}
                />
              ) : (
                accessDenied
              )
            }
          />
          <Route
            path="/inbound/new"
            element={
              token && sellerPermissions.documents ? (
                <SellerInboundDraftScreen
                  key={catalogScopeKey}
                  token={token}
                  authHeaders={authHeaders}
                  warehouseId={selectedWarehouseId ?? (warehouses[0]?.id ?? null)}
                  warehouses={warehouses}
                  onRefreshInboundList={() =>
                    token ? refreshInboundList(token) : undefined
                  }
                />
              ) : (
                accessDenied
              )
            }
          />
          <Route
            path="/inbound/:requestId"
            element={
              token && sellerPermissions.documents ? (
                <SellerInboundDraftScreen
                  key={catalogScopeKey}
                  token={token}
                  authHeaders={authHeaders}
                  warehouseId={selectedWarehouseId ?? (warehouses[0]?.id ?? null)}
                  warehouses={warehouses}
                  onRefreshInboundList={() =>
                    token ? refreshInboundList(token) : undefined
                  }
                />
              ) : (
                accessDenied
              )
            }
          />
          <Route
            path="/products"
            element={
              token && sellerPermissions.products ? (
                <SellerProductsStockScreen
                  key={catalogScopeKey}
                  token={token}
                  authHeaders={authHeaders}
                />
              ) : (
                accessDenied
              )
            }
          />
          <Route
            path="/honest-sign"
            element={
              token && sellerPermissions.honest_sign ? (
                <SellerHonestSignScreen
                  key={catalogScopeKey}
                  token={token}
                  sellerId={me.active_seller_id ?? me.seller_id ?? ''}
                />
              ) : (
                accessDenied
              )
            }
          />
          <Route
            path="/settings"
            element={
              token && (sellerPermissions.settings || sellerPermissions.staff) ? (
                <SellerSettingsScreen
                  key={catalogScopeKey}
                  token={token}
                  authHeaders={authHeaders}
                  permissions={sellerPermissions}
                  onStaffChanged={async () => {
                    await reloadMe()
                  }}
                />
              ) : (
                accessDenied
              )
            }
          />
          <Route
            path="/notifications"
            element={
              token ? (
                <NotificationsPage token={token} portal="seller" testId="seller-notifications-page" />
              ) : null
            }
          />
          <Route
            path="*"
            element={<Navigate to={sellerPath(firstAllowedSellerPath(sellerPermissions))} replace />}
          />
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
