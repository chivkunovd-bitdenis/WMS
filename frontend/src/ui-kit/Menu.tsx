import MoreVert from '@mui/icons-material/MoreVert'
import { ListItemIcon, ListItemText, Menu, MenuItem } from '@mui/material'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { IconAction } from './Actions'

export type MenuOption = {
  label: string
  onClick: () => void
  icon?: ReactNode
  disabledReason?: string
  danger?: boolean
}

export function ActionMenu({
  title,
  options,
  testId,
}: {
  title: string
  options: MenuOption[]
  testId?: string
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const open = Boolean(anchor)

  return (
    <>
      <IconAction title={title} onClick={(event) => setAnchor(event.currentTarget)} testId={testId}>
        <MoreVert fontSize="small" />
      </IconAction>
      <Menu anchorEl={anchor} open={open} onClose={() => setAnchor(null)}>
        {options.map((option) => (
          <MenuItem
            key={option.label}
            disabled={Boolean(option.disabledReason)}
            onClick={() => {
              setAnchor(null)
              option.onClick()
            }}
            sx={option.danger ? { color: 'error.main' } : undefined}
          >
            {option.icon ? <ListItemIcon sx={option.danger ? { color: 'error.main' } : undefined}>{option.icon}</ListItemIcon> : null}
            <ListItemText primary={option.label} secondary={option.disabledReason} />
          </MenuItem>
        ))}
      </Menu>
    </>
  )
}
