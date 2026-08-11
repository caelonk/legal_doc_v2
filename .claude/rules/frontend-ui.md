---
paths:
  - "frontend/src/**/*.jsx"
  - "frontend/src/**/*.js"
  - "frontend/src/**/*.css"
  - "frontend/tailwind.config.js"
---

# Frontend UI Rules

Full reference: `docs/design-system.md`. Read it before significant visual work.

## Tokens
- Reference semantic Tailwind tokens only: `text-ink`, `text-ink-muted`, `bg-surface`,
  `bg-surface-sunken`, `border-border`, `text-brand`, `text-accent`, `text-risk-high`.
- NEVER hardcode a hex value in a component. NEVER use raw Tailwind palette classes
  (`bg-gray-50`, `text-red-700`) — they bypass the token system.
- A color or font not defined in `docs/design-system.md` requires asking first.

## Shape and motion
- Border radius: 2px inputs/badges, 6px buttons/cards, 8px modals. 8px is a hard ceiling.
- Shadows: `shadow-sm` for cards, `shadow-lg` for modals only.
- Transitions 150ms ease-out. Respect `prefers-reduced-motion`.
- No glassmorphism, gradient buttons, emoji, or celebratory animation.

## Typography
- Serif (`font-serif`) for H1–H3 and document titles only. Everything else sans.
- Mono for page references, clause IDs, defined terms.
- Long-form text: 16–18px, line-height 1.6, max-width ~70ch.

## Components
- Prefer shadcn/ui + Radix primitives over hand-rolled dialogs, tabs, tooltips, popovers.
- Icons from `lucide-react` only, 1.5px stroke, 16px in tables, 20px in navigation.
- Risk severity renders color + icon + text label, always. `RiskBadge` must not accept a
  prop that hides the label.
- Tables for risk flags and missing clauses. Cards for summary and metadata only.

## Accessibility (build requirement, not polish)
- 4.5:1 body text contrast, 3:1 for large text and UI component borders.
- Visible focus ring on every interactive element — never remove an outline without
  replacing it.
- Full keyboard operability; tab order follows visual order.
- 24×24px minimum target size.
- Analysis completion and errors announced via `aria-live="polite"`.

## States
- Every API-driven view handles loading, error, empty, and partial-success.
- Processing shows stage and count (`Analyzing 4 of 11 sections`), not a bare spinner.
- Skeletons match final layout shape.
- Never lose uploaded file state on a downstream error.
