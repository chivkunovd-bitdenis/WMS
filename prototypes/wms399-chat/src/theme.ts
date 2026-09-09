import { alpha, createTheme } from '@mui/material/styles'

export const chatTheme = createTheme({
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
    warning: {
      main: '#c2410c',
      light: '#fff7ed',
    },
    info: {
      main: '#0f766e',
      light: '#ecfeff',
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
  shape: { borderRadius: 12 },
  typography: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, ui-sans-serif, system-ui, "Apple Color Emoji", "Segoe UI Emoji", sans-serif',
    h5: { fontWeight: 800, letterSpacing: '-0.02em', color: '#0f172a' },
    h6: { fontWeight: 800, letterSpacing: '-0.015em', color: '#0f172a' },
    subtitle1: { fontWeight: 600, color: '#0f172a' },
    subtitle2: { fontWeight: 600, color: '#0f172a' },
    body2: { color: '#334155' },
    caption: { color: '#64748b' },
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
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
        },
      },
    },
    MuiTextField: {
      defaultProps: { size: 'small' },
    },
    MuiSelect: {
      defaultProps: { size: 'small' },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundImage: 'none',
        },
      },
    },
  },
})
