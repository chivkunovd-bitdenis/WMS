import type { ReactNode } from 'react'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'
import 'dayjs/locale/ru'

type Props = {
  children: ReactNode
}

export function WmsDatePickersProvider({ children }: Props) {
  return (
    <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="ru">
      {children}
    </LocalizationProvider>
  )
}
