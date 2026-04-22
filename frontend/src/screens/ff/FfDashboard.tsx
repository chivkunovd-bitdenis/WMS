import { useMemo, useState } from 'react'
import type { FormEventHandler } from 'react'
import type { ReactNode } from 'react'
import {
  Box,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { DashboardCard } from '../../components/DashboardCard'
import { FfWeekCalendar } from './FfWeekCalendar'

export type FfInboundSummary = {
  id: string
  status: string
  line_count: number
  planned_delivery_date: string | null
  seller_name?: string | null
  created_at?: string
}

export type FfOutboundSummary = {
  id: string
  status: string
  line_count: number
  planned_shipment_date?: string | null
  created_at?: string
  warehouse_name?: string
  goods_qty_total?: number
  marketplace_label?: string
  seller_name?: string | null
}

type Me = {
  email: string
  organization_name: string
  role: string
  seller_name?: string | null
}

type SellerRow = { id: string; name: string }

type Props = {
  me: Me
  isFulfillmentAdmin: boolean
  sellers: SellerRow[]
  catalogBusy: boolean
  catalogError: string | null
  onCreateSellerAccount: FormEventHandler<HTMLFormElement>
  inboundSummaries: FfInboundSummary[]
  outboundSummaries: FfOutboundSummary[]
  onOpenInbound: (id: string) => void
  onOpenOutbound: (id: string) => void
}

function outboundPlanDate(row: FfOutboundSummary): string | null {
  if (row.planned_shipment_date) {
    return row.planned_shipment_date
  }
  if (row.created_at) {
    return row.created_at.slice(0, 10)
  }
  return null
}

function FfDashboardSection({
  title,
  subtitle,
  testId,
  children,
}: {
  title: string
  subtitle: string
  testId?: string
  children: ReactNode
}) {
  return (
    <Paper
      elevation={0}
      data-testid={testId}
      sx={(theme) => ({
        overflow: 'hidden',
        border: `1px solid ${alpha(theme.palette.primary.main, 0.22)}`,
        borderRadius: 2,
        boxShadow: `0 4px 18px ${alpha(theme.palette.common.black, 0.07)}, 0 1px 3px ${alpha(theme.palette.common.black, 0.05)}`,
      })}
    >
      <Box
        sx={(theme) => ({
          px: 2.5,
          py: 2,
          borderBottom: `1px solid ${alpha(theme.palette.divider, 0.9)}`,
          background: `linear-gradient(118deg, ${alpha(theme.palette.primary.main, 0.14)} 0%, ${alpha(theme.palette.primary.light, 0.22)} 42%, ${alpha(theme.palette.primary.main, 0.07)} 100%)`,
        })}
      >
        <Typography
          variant="h6"
          component="h2"
          sx={{
            fontWeight: 800,
            color: 'text.primary',
            letterSpacing: '-0.02em',
            textShadow: '0 1px 0 rgba(255,255,255,0.45)',
          }}
        >
          {title}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            mt: 0.75,
            color: 'text.secondary',
            fontWeight: 500,
            lineHeight: 1.45,
            maxWidth: 720,
          }}
        >
          {subtitle}
        </Typography>
      </Box>
      <Box sx={{ px: 2, py: 2, bgcolor: 'background.paper' }}>{children}</Box>
    </Paper>
  )
}

export function FfDashboard({
  me,
  isFulfillmentAdmin,
  sellers,
  catalogBusy,
  catalogError,
  onCreateSellerAccount,
  inboundSummaries,
  outboundSummaries,
  onOpenInbound,
  onOpenOutbound,
}: Props) {
  const [weekOffset, setWeekOffset] = useState(0)

  const plannedInbound = useMemo(
    () =>
      inboundSummaries.filter(
        (r) => r.status !== 'draft' && r.planned_delivery_date,
      ),
    [inboundSummaries],
  )

  const plannedOutbound = useMemo(
    () => outboundSummaries.filter((r) => r.status === 'submitted'),
    [outboundSummaries],
  )

  const inboundBars = useMemo(() => {
    return plannedInbound
      .filter((r) => r.planned_delivery_date)
      .map((r) => ({
        id: r.id,
        dateKey: r.planned_delivery_date!,
        label: `${r.seller_name ?? 'Селлер'} · ${r.line_count} стр.`,
      }))
  }, [plannedInbound])

  const outboundBars = useMemo(() => {
    return plannedOutbound
      .map((r) => {
        const dk = outboundPlanDate(r)
        if (!dk) {
          return null
        }
        return {
          id: r.id,
          dateKey: dk,
          label: `${r.warehouse_name ?? 'Склад'} · ${r.goods_qty_total ?? r.line_count} шт.`,
        }
      })
      .filter((x): x is NonNullable<typeof x> => x !== null)
  }, [plannedOutbound])

  return (
    <Stack spacing={3} data-testid="dashboard">
      <Paper
        elevation={0}
        sx={(theme) => ({
          p: 2.5,
          border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
          borderRadius: 2,
          boxShadow: `0 2px 14px ${alpha(theme.palette.common.black, 0.06)}`,
          background: `linear-gradient(135deg, ${theme.palette.background.paper} 0%, ${alpha(theme.palette.primary.main, 0.04)} 100%)`,
        })}
      >
        <Typography
          variant="h5"
          component="h1"
          sx={{
            fontWeight: 800,
            color: 'text.primary',
            letterSpacing: '-0.025em',
          }}
        >
          Дашборд ФФ
        </Typography>
        <Typography
          variant="body2"
          sx={{ mt: 1, color: 'text.secondary', fontWeight: 600 }}
          data-testid="org-name"
        >
          {me.organization_name}
        </Typography>
        <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary', fontWeight: 500, lineHeight: 1.5 }}>
          Поставки селлеров (заявки селлер → ФФ) и отгрузки фулфилмента на маркетплейс — план по датам.
        </Typography>
      </Paper>

      <FfDashboardSection
        testId="ff-dashboard-inbound-block"
        title="Запланированные поставки (от селлеров)"
        subtitle="После выхода из черновика, с плановой датой привоза."
      >
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Плановая дата привоза</TableCell>
              <TableCell align="right">Строк</TableCell>
              <TableCell>Селлер</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {plannedInbound.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3}>
                  <Typography variant="body2" color="text.secondary">
                    Нет заявок в плане
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              plannedInbound.map((row) => (
                <TableRow
                  key={row.id}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => onOpenInbound(row.id)}
                  data-testid="ff-dash-inbound-row"
                >
                  <TableCell>{row.planned_delivery_date ?? '—'}</TableCell>
                  <TableCell align="right">{row.line_count}</TableCell>
                  <TableCell>{row.seller_name ?? '—'}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </FfDashboardSection>

      <FfDashboardSection
        testId="ff-dashboard-outbound-block"
        title="Запланированные отгрузки на склад МП"
        subtitle="Статус «submitted» (запланировано к отгрузке), плановая дата отвоза."
      >
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Дата отвоза</TableCell>
              <TableCell>Склад</TableCell>
              <TableCell>Маркетплейс</TableCell>
              <TableCell align="right">Товаров (шт.)</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {plannedOutbound.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4}>
                  <Typography variant="body2" color="text.secondary">
                    Нет отгрузок в плане
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              plannedOutbound.map((row) => (
                <TableRow
                  key={row.id}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => onOpenOutbound(row.id)}
                  data-testid="ff-dash-outbound-row"
                >
                  <TableCell>{outboundPlanDate(row) ?? '—'}</TableCell>
                  <TableCell>{row.warehouse_name ?? '—'}</TableCell>
                  <TableCell>{row.marketplace_label ?? 'Wildberries'}</TableCell>
                  <TableCell align="right">
                    {row.goods_qty_total ?? row.line_count}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </FfDashboardSection>

      <FfWeekCalendar
        weekOffset={weekOffset}
        onWeekOffsetChange={setWeekOffset}
        inboundBars={inboundBars}
        outboundBars={outboundBars}
        onInboundBarClick={onOpenInbound}
        onOutboundBarClick={onOpenOutbound}
      />

      {isFulfillmentAdmin ? (
        <Paper
          elevation={0}
          data-testid="ff-dashboard-admin-card"
          sx={(theme) => ({
            p: 2,
            border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
            borderRadius: 2,
            boxShadow: `0 4px 18px ${alpha(theme.palette.common.black, 0.07)}`,
            bgcolor: 'background.paper',
          })}
        >
          <DashboardCard
            me={me}
            isFulfillmentAdmin={isFulfillmentAdmin}
            sellers={sellers}
            catalogBusy={catalogBusy}
            catalogError={catalogError}
            onCreateSellerAccount={onCreateSellerAccount}
            embedded
          />
        </Paper>
      ) : null}
    </Stack>
  )
}
