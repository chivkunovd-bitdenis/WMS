import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { Box, CssBaseline, ThemeProvider } from '@mui/material'

import { muiTheme } from '../../../../mui/theme'
import { AuthedAppLayout } from '../../../../layouts/AuthedAppLayout'

/**
 * Обвязка для «живых макетов» базы знаний.
 *
 * Картинки в статьях и проигрыватель сценария показывают не отдельный экран,
 * а экран внутри настоящего шелла портала — с шапкой и левым меню. Иначе
 * сотрудник не узнаёт то, что видит перед собой, и не понимает, куда нажимать.
 * Компонент рендерит настоящий `AuthedAppLayout` с выдуманным пользователем и
 * полными правами: сервера под макетом нет, права здесь — только про то, какие
 * пункты меню видно.
 */

const ALL_PERMISSIONS = {
  settings: true,
  mp_shipments: true,
  reception: true,
  cells: true,
  inventory: true,
  packaging: true,
  shift_lead: true,
} as const

export const SCENE_USER_LABEL = 'sklad@korob-vms.ru'

type Props = {
  children: ReactNode
  /** Адрес, по которому подсвечивается активный пункт левого меню. */
  route?: string
}

export function SceneShell({ children, route = '/app/ff/reception' }: Props) {
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <MemoryRouter initialEntries={[route]}>
        <AuthedAppLayout
          portal="ff"
          meRole="fulfillment_admin"
          ffPermissions={ALL_PERMISSIONS}
          userLabel={SCENE_USER_LABEL}
          userRoleLabel="администратор"
          onLogout={() => {}}
        >
          <Box sx={{ minWidth: 0 }}>{children}</Box>
        </AuthedAppLayout>
      </MemoryRouter>
    </ThemeProvider>
  )
}
