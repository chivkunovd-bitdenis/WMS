import { alpha, createTheme } from '@mui/material/styles'

export const muiTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#5b21b6',
      light: '#7c3aed',
      dark: '#4c1d95',
    },
    secondary: {
      main: '#475569',
    },
    text: {
      primary: '#0f172a',
      secondary: '#475569',
    },
    background: {
      default: '#e8ecf4',
      paper: '#ffffff',
    },
    divider: 'rgba(15, 23, 42, 0.11)',
  },
  shape: {
    borderRadius: 12,
  },
  typography: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji"',
    h5: { fontWeight: 800, letterSpacing: '-0.02em', color: '#0f172a' },
    h6: { fontWeight: 800, letterSpacing: '-0.015em', color: '#0f172a' },
    subtitle1: { fontWeight: 600, color: '#0f172a' },
    subtitle2: { fontWeight: 600, color: '#0f172a' },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
      defaultProps: {
        disableElevation: true,
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 14,
        },
        outlined: ({ theme }) => ({
          borderColor: alpha(theme.palette.primary.main, 0.2),
          boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
        }),
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: ({ theme }) => ({
          fontWeight: 700,
          fontSize: '0.8125rem',
          color: theme.palette.text.primary,
          backgroundColor: alpha(theme.palette.primary.main, 0.08),
          borderBottom: `2px solid ${alpha(theme.palette.primary.main, 0.18)}`,
        }),
      },
    },
    MuiTextField: {
      defaultProps: {
        size: 'small',
      },
    },
    MuiSelect: {
      defaultProps: {
        size: 'small',
      },
    },
  },
})

