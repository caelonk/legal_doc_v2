import * as RadixTabs from '@radix-ui/react-tabs'

/**
 * Thin styled wrapper over Radix Tabs.
 *
 * Radix rather than hand-rolled, per .claude/rules/frontend-ui.md and
 * design-system.md §6: it supplies roving tabindex, arrow-key and Home/End
 * navigation, and the aria-selected / aria-controls wiring that a div-with-onClick
 * silently omits. This is the first component in the project that needed any of
 * that, which is why the Radix dependency arrives now rather than at scaffold time.
 *
 * Written directly instead of via the shadcn CLI: the CLI's generated components
 * are styled against its own token names (--background, --foreground), and this
 * project has its own semantic set. Rewriting generated files to match is more
 * work than the twenty lines below, and shadcn's actual promise — you own the
 * source — is satisfied either way.
 */

export const Tabs = RadixTabs.Root

export function TabsList({ children, label }) {
  return (
    <RadixTabs.List
      aria-label={label}
      className="flex shrink-0 items-stretch gap-1 border-b border-border bg-surface px-2"
    >
      {children}
    </RadixTabs.List>
  )
}

export function TabsTrigger({ value, children }) {
  return (
    <RadixTabs.Trigger
      value={value}
      // Accent on the active tab, per design-system.md §1, which reserves the one
      // accent hue for links, focus rings and active tabs. The indicator is a
      // border rather than a filled pill: 2px of colour, no new shape language.
      className="-mb-px border-b-2 border-transparent px-3 py-2.5 text-sm font-medium text-ink-muted transition hover:text-ink data-[state=active]:border-accent data-[state=active]:text-accent"
    >
      {children}
    </RadixTabs.Trigger>
  )
}

export function TabsContent({ value, children }) {
  return (
    // min-h-0 so a scrolling child inside a flex column resolves its own height
    // instead of growing the panel past the viewport.
    <RadixTabs.Content value={value} className="min-h-0 flex-1 focus-visible:outline-none">
      {children}
    </RadixTabs.Content>
  )
}
