import { Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { buttonVariants } from '@/components/ui/button-variants'
import { Button } from '@/components/ui/button'

function MobileNavigation() {
  const [open, setOpen] = useState(false)
  const menuId = 'mobile-primary-navigation'

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="ml-auto md:hidden"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
      </Button>
      {open && (
        <div
          id={menuId}
          className="absolute inset-x-0 top-full flex flex-col gap-2 border-b bg-card p-4 shadow-soft md:hidden"
        >
          <Link
            to="/challenges"
            className="flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-foreground hover:bg-muted"
            onClick={() => setOpen(false)}
          >
            Challenges
          </Link>
          <Link
            to="/challenges"
            className={buttonVariants({ variant: 'primary' })}
            onClick={() => setOpen(false)}
          >
            Run a real repo
          </Link>
        </div>
      )}
    </>
  )
}

export default function App() {
  const { pathname } = useLocation()
  const inWorkspace = /^\/c\/[^/]+$/.test(pathname)

  return (
    <>
      {!inWorkspace && (
        <nav
          aria-label="Primary navigation"
          className="sticky top-0 z-50 flex min-h-16 items-center gap-7 border-b bg-card/95 px-5 backdrop-blur-sm md:px-8"
        >
          <Link to="/" className="text-[15px] font-bold tracking-[-0.025em] text-foreground">
            MakeItGreen<span className="text-sticker-green">.</span>
          </Link>
          <Link
            to="/challenges"
            className="hidden min-h-11 items-center text-sm text-muted-foreground transition-colors hover:text-foreground md:flex"
          >
            Challenges
          </Link>
          <div className="hidden flex-1 md:block" />
          <Link
            to="/challenges"
            className={`${buttonVariants({ variant: 'utility' })} hidden md:inline-flex`}
          >
            Run a real repo
          </Link>
          <MobileNavigation key={pathname} />
        </nav>
      )}
      <Outlet />
    </>
  )
}
