import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PageReference from '../components/PageReference'
import RiskBadge from '../components/RiskBadge'

describe('RiskBadge', () => {
  it.each([
    ['HIGH', 'High'],
    ['MEDIUM', 'Medium'],
    ['LOW', 'Low'],
  ])('renders a text label for %s', (severity, label) => {
    render(<RiskBadge severity={severity} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('renders an icon alongside the label', () => {
    // Colour + icon + text, always. Colour alone fails colour-blind users and
    // WCAG 1.4.1, so the icon is not decoration.
    const { container } = render(<RiskBadge severity="HIGH" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('hides the icon from assistive tech, since the label already says it', () => {
    const { container } = render(<RiskBadge severity="HIGH" />)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('accepts no prop that could suppress the label', () => {
    // The rule in .claude/rules/frontend-ui.md is that this component must be
    // physically incapable of rendering without its label. Passing the props
    // someone would reach for must change nothing.
    render(<RiskBadge severity="HIGH" showLabel={false} iconOnly compact />)
    expect(screen.getByText('High')).toBeInTheDocument()
  })

  it('still renders something for an unrecognised severity', () => {
    // An empty cell would read as "no risk here", which is the opposite of
    // "we did not understand this value".
    render(<RiskBadge severity="CRITICAL" />)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('does not render an empty label when severity is missing entirely', () => {
    const { container } = render(<RiskBadge severity={undefined} />)
    expect(container.textContent.trim()).not.toBe('')
  })
})

describe('PageReference', () => {
  it('renders a clickable citation for a real page', () => {
    render(<PageReference page={12} onNavigate={() => {}} />)
    expect(screen.getByRole('button', { name: /go to page 12/i })).toBeInTheDocument()
    expect(screen.getByText(/p\. 12/)).toBeInTheDocument()
  })

  it('calls onNavigate with the page number', () => {
    const onNavigate = vi.fn()
    render(<PageReference page={4} onNavigate={onNavigate} />)
    screen.getByRole('button').click()
    expect(onNavigate).toHaveBeenCalledWith(4)
  })

  it('renders an explicit "Source not located" for a null page', () => {
    // Never hidden and never guessed. A visibly missing citation is honest; a
    // silently absent one looks like the claim was verified when it was not.
    render(<PageReference page={null} onNavigate={() => {}} />)
    expect(screen.getByText('Source not located')).toBeInTheDocument()
  })

  it('does not offer a null citation as clickable', () => {
    render(<PageReference page={null} onNavigate={() => {}} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('treats undefined the same as null rather than rendering "p. undefined"', () => {
    render(<PageReference page={undefined} onNavigate={() => {}} />)
    expect(screen.getByText('Source not located')).toBeInTheDocument()
  })

  it('does not treat page 0 as missing', () => {
    // Guards the `page || fallback` bug. Page 0 should never come from the
    // parser, but if it ever did, silently relabelling it "Source not located"
    // would hide a real parser fault.
    render(<PageReference page={0} onNavigate={() => {}} />)
    expect(screen.queryByText('Source not located')).not.toBeInTheDocument()
  })
})
