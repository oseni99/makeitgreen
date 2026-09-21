export const clerkAppearance = {
  variables: {
    colorPrimary: '#0075de',
    colorPrimaryForeground: '#ffffff',
    colorBackground: '#ffffff',
    colorForeground: '#000000',
    colorDanger: '#c9362b',
    colorInput: '#e6e6e6',
    colorInputForeground: '#000000',
    colorMuted: '#efeeec',
    colorMutedForeground: '#615d59',
    colorNeutral: '#000000',
    colorRing: 'rgb(0 117 222 / 50%)',
    borderRadius: '0.5rem',
    fontFamily: '"Inter Variable", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    spacingUnit: '1rem',
  },
  elements: {
    input: { backgroundColor: 'transparent' },
    cardBox: {
      border: '1px solid #e6e6e6',
      boxShadow: '0 1px 2px rgb(0 0 0 / 5%)',
    },
    popoverBox: {
      border: '1px solid #e6e6e6',
      boxShadow: '0 1px 2px rgb(0 0 0 / 5%)',
    },
    button: {
      '&[data-variant="solid"]::after': { display: 'none' },
    },
  },
  options: {
    // This only removes Clerk's local preview warning. Production instances do
    // not render the warning, and account security behavior is unchanged.
    unsafe_disableDevelopmentModeWarnings: true,
  },
} as const

export const signInAppearance = {
  ...clerkAppearance,
  options: {
    ...clerkAppearance.options,
    socialButtonsVariant: 'blockButton',
  },
  elements: {
    ...clerkAppearance.elements,
    rootBox: { width: '100%' },
    cardBox: {
      width: '100%',
      overflow: 'hidden',
      border: '1px solid #e6e6e6',
      borderRadius: '0.75rem',
      boxShadow: 'none',
    },
    card: {
      width: '100%',
      border: 'none',
      borderRadius: 0,
      backgroundColor: '#ffffff',
      boxShadow: 'none',
    },
    header: 'text-left',
    headerTitle: 'text-2xl font-bold tracking-[-0.025em]',
    headerSubtitle: 'text-sm text-muted-foreground',
    socialButtonsBlockButton: 'min-h-11 rounded-md border bg-background shadow-none',
    footer: {
      borderTop: '1px solid #e6e6e6',
      backgroundColor: '#ffffff',
      boxShadow: 'none',
    },
    footerActionLink: 'font-semibold text-primary',
  },
} as const
