import { Menu, Moon, Sun, Bell } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useTheme } from '@/context/ThemeContext'
import { NAV_ITEMS } from './nav'

function currentTitle(pathname) {
  const item = NAV_ITEMS.find((n) =>
    n.end ? pathname === n.to : pathname.startsWith(n.to),
  )
  return item?.label ?? 'MediSense'
}

export default function Topbar({ onMenu }) {
  const { theme, toggle } = useTheme()
  const { pathname } = useLocation()

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-surface/80 px-4 backdrop-blur-md lg:px-8">
      <div className="flex items-center gap-3">
        <button
          className="rounded-lg p-2 text-muted hover:bg-surface-2 lg:hidden"
          onClick={onMenu}
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>
        <div>
          <h1 className="text-lg font-semibold text-foreground">
            {currentTitle(pathname)}
          </h1>
          <p className="hidden text-xs text-muted sm:block">
            Welcome back — here’s your clinical workspace
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <button
          className="relative rounded-xl p-2.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
          aria-label="Notifications"
        >
          <Bell size={19} />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-danger" />
        </button>
        <button
          onClick={toggle}
          className="rounded-xl p-2.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
        </button>
      </div>
    </header>
  )
}
