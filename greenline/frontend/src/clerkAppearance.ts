import { shadcn } from '@clerk/ui/themes'

export const clerkAppearance = {
  theme: shadcn,
  variables: {
    colorPrimary: '#0075de',
    colorBackground: '#ffffff',
    colorForeground: '#000000',
    colorMutedForeground: '#615d59',
    borderRadius: '0.5rem',
    fontFamily: '"Inter Variable", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    spacingUnit: '1rem',
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
