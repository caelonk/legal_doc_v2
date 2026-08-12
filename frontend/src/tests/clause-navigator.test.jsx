import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ClauseNavigator from '../components/ClauseNavigator'
import { analysisResult, riskFlag, section } from './fixtures'

const flag = (clause_type, severity, page) => riskFlag({ clause_type, severity, page_reference: page })

const resultWith = (flags) => analysisResult({ sections: [section({ risk_flags: flags })] })

function renderNavigator(flags, onNavigate = () => {}) {
  return render(<ClauseNavigator result={resultWith(flags)} onNavigate={onNavigate} />)
}

const entryNames = () =>
  screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))

describe('ordering', () => {
  it('lists findings in document order, not severity order', () => {
    // The whole reason this exists beside the risk table. If it sorted by
    // severity too, it would be a second copy of the same view.
    renderNavigator([
      flag('Holdover', 'LOW', 5),
      flag('Indemnification', 'HIGH', 2),
      flag('Assignment', 'MEDIUM', 3),
    ])
    const order = entryNames().map((label) => label.split(',')[0])
    expect(order).toEqual(['Indemnification', 'Assignment', 'Holdover'])
  })

  it('does not lead with the highest severity', () => {
    renderNavigator([flag('Late Page High', 'HIGH', 9), flag('Early Page Low', 'LOW', 1)])
    expect(entryNames()[0]).toMatch(/Early Page Low/)
  })
})

describe('severity presentation', () => {
  it('renders a text label on every entry, not colour alone', () => {
    // A compact rail is exactly where the temptation is to drop to a coloured
    // dot. .claude/rules/frontend-ui.md forbids it.
    renderNavigator([flag('Indemnification', 'HIGH', 2), flag('Holdover', 'MEDIUM', 3)])
    expect(screen.getByText('High')).toBeInTheDocument()
    expect(screen.getByText('Medium')).toBeInTheDocument()
  })

  it('renders an icon on every entry', () => {
    const { container } = renderNavigator([flag('Indemnification', 'HIGH', 2)])
    expect(container.querySelectorAll('svg').length).toBeGreaterThan(0)
  })

  it('names severity and page in the accessible label', () => {
    renderNavigator([flag('Indemnification', 'HIGH', 4)])
    expect(
      screen.getByRole('button', { name: /Indemnification, high severity, page 4/i }),
    ).toBeInTheDocument()
  })
})

describe('navigation', () => {
  it('jumps to the page when an entry is activated', () => {
    const onNavigate = vi.fn()
    renderNavigator([flag('Indemnification', 'HIGH', 4)], onNavigate)
    screen.getByRole('button').click()
    expect(onNavigate).toHaveBeenCalledWith(4)
  })

  it('is a navigation landmark', () => {
    renderNavigator([flag('Indemnification', 'HIGH', 4)])
    expect(screen.getByRole('navigation', { name: /flagged clauses/i })).toBeInTheDocument()
  })
})

describe('unlocated findings', () => {
  const flags = [flag('Indemnification', 'HIGH', 2), flag('Confession of Judgment', 'HIGH', null)]

  it('still lists a finding with no page', () => {
    // Dropping it would quietly contradict the count in the header, and would
    // hide a real finding because its citation was the untrustworthy part.
    renderNavigator(flags)
    expect(screen.getByText('Confession of Judgment')).toBeInTheDocument()
  })

  it('groups them under their own heading', () => {
    renderNavigator(flags)
    expect(screen.getByRole('heading', { name: /source not located \(1\)/i })).toBeInTheDocument()
  })

  it('does not offer them as a jump', () => {
    renderNavigator(flags)
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0].getAttribute('aria-label')).toMatch(/Indemnification/)
  })

  it('shows no heading when everything is located', () => {
    renderNavigator([flag('Indemnification', 'HIGH', 2)])
    expect(screen.queryByText(/source not located/i)).not.toBeInTheDocument()
  })
})

describe('counts and empty state', () => {
  it('reports counts per severity, never an aggregate score', () => {
    renderNavigator([
      flag('A', 'HIGH', 1),
      flag('B', 'HIGH', 2),
      flag('C', 'MEDIUM', 3),
    ])
    expect(screen.getByText('2 high · 1 medium · 0 low')).toBeInTheDocument()
  })

  it('counts unlocated findings in the header too', () => {
    renderNavigator([flag('A', 'HIGH', 1), flag('B', 'HIGH', null)])
    const header = screen.getByText(/high ·/)
    expect(within(header).queryByText).toBeDefined()
    expect(header.textContent).toMatch(/^2 high/)
  })

  it('says so plainly when there is nothing to navigate', () => {
    renderNavigator([])
    expect(screen.getByText(/No risk-flagged clauses to navigate/i)).toBeInTheDocument()
    expect(screen.getByText(/not a clean bill of health/i)).toBeInTheDocument()
  })
})
