import { AlertCircle, AlertTriangle, Info } from 'lucide-react'

/**
 * Severity as colour + icon + text label. Always all three.
 *
 * There is deliberately no `showLabel` prop and no icon-only mode. Colour alone
 * fails colour-blind users and WCAG 1.4.1, and the rule in
 * .claude/rules/frontend-ui.md is that this component must be physically
 * incapable of rendering without its label. A prop that could suppress it would
 * eventually be passed.
 *
 * Used for both RiskFlag.severity and MissingClause.importance — the same ordinal
 * scale, so the same visual language.
 */
const VARIANTS = {
  HIGH: {
    label: 'High',
    Icon: AlertTriangle,
    className: 'text-risk-high bg-risk-high-bg border-risk-high-border',
  },
  MEDIUM: {
    label: 'Medium',
    Icon: AlertCircle,
    className: 'text-risk-medium bg-risk-medium-bg border-risk-medium-border',
  },
  LOW: {
    label: 'Low',
    Icon: Info,
    className: 'text-risk-low bg-risk-low-bg border-risk-low-border',
  },
}

export default function RiskBadge({ severity }) {
  // An unrecognised value must still render something honest rather than a blank
  // cell that reads as "no risk".
  const variant = VARIANTS[severity] ?? {
    label: severity || 'Unknown',
    Icon: Info,
    className: 'text-ink-muted bg-surface-sunken border-border',
  }
  const { label, Icon, className } = variant

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-medium ${className}`}
    >
      <Icon size={16} strokeWidth={1.5} aria-hidden="true" className="shrink-0" />
      {label}
    </span>
  )
}
