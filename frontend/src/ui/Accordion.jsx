import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Collapsible section. Hidden by default unless `defaultOpen`. */
export default function Accordion({ title, subtitle, icon: Icon, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-surface-2"
      >
        <span className="flex items-center gap-2.5">
          {Icon && <Icon size={18} className="text-muted" />}
          <span>
            <span className="block font-semibold text-foreground">{title}</span>
            {subtitle && <span className="block text-xs text-muted">{subtitle}</span>}
          </span>
        </span>
        <ChevronDown
          size={18}
          className={cn('shrink-0 text-muted transition-transform', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="animate-fade-up border-t border-border px-5 py-5">{children}</div>
      )}
    </div>
  )
}
