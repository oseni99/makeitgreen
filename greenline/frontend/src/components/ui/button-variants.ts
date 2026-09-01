import { cva } from 'class-variance-authority'

export const buttonVariants = cva(
  'inline-flex min-h-11 items-center justify-center gap-2 whitespace-nowrap font-medium transition-[background-color,color,border-color,box-shadow,transform] outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'rounded-full bg-primary px-6 py-2.5 text-primary-foreground hover:bg-primary-active',
        secondary:
          'rounded-full border border-border bg-card px-6 py-2.5 text-foreground shadow-soft hover:bg-muted',
        utility:
          'rounded-md border border-border bg-card px-3.5 py-1 text-sm text-foreground hover:bg-muted',
        ghost: 'rounded-md px-3 py-2 text-foreground hover:bg-muted',
        destructive:
          'rounded-md bg-destructive px-4 py-2 text-destructive-foreground hover:brightness-95',
      },
      size: {
        default: 'text-base',
        sm: 'min-h-9 text-sm',
        icon: 'size-11 rounded-full p-0',
      },
    },
    defaultVariants: {
      variant: 'utility',
      size: 'default',
    },
  },
)
