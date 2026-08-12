# Frontend tests

```bash
npm test          # once
npm run test:watch
```

Vitest + jsdom + Testing Library. These exist because three accessibility defects
shipped in the first frontend pass and nothing would have caught any of them coming
back: 29×17px citation targets, an `aria-live` region that unmounted at the exact
moment it had something to announce, and a results view with no `h1`. All three were
found by poking at the rendered page by hand. That does not scale and does not repeat.

## What is covered

Each test maps to a rule that was previously only prose in `CLAUDE.md`,
`.claude/rules/ai-output.md`, or `docs/`:

| File | Guards |
|---|---|
| `severity.test.js` | HIGH before MEDIUM before LOW (never alphabetical); unlocated findings sort **last within** their severity, not first; no de-duplication across the chunk overlap |
| `components.test.jsx` | `RiskBadge` always renders a text label and an icon, and has no prop that can suppress either; `PageReference` renders `Source not located` for a null page and never guesses |
| `results-panel.test.jsx` | Disclosure always present and not dismissible; per-severity counts rather than an aggregate score; skipped sections disclosed with correct singular/plural pages; `ChunkFailure.detail` never rendered; risk flags and missing clauses kept in separate tables |
| `a11y-structure.test.jsx` | Exactly one `h1`, no skipped heading level, every table has `th[scope="col"]`, every button has an accessible name |
| `analysis-page.test.jsx` | A live region exists in **every** branch — loading, running, complete, failed, error; a FAILED run renders no findings table |

Every one of these was verified by mutation: break the rule in the source, confirm the
matching test goes red, restore. A test that has never failed is not evidence.

## What is NOT covered, and why

**jsdom has no layout engine.** It computes no geometry, so the following cannot be
tested here and are verified in a browser instead:

- **24×24px minimum target size** (WCAG 2.2 SC 2.5.8). Asserting that `min-h-6` appears
  in a class list would look like coverage while proving nothing — it passes just as
  happily if the class stops resolving to 24px, if a parent overrides it, or if Tailwind
  is misconfigured. The rule is about rendered geometry, so only rendered geometry can
  check it.
- **Reflow at 200% zoom** — no horizontal scroll at a 640px viewport.
- **Contrast ratios.** Colours come from CSS custom properties that jsdom does not resolve.
- **Real scroll positioning.** `Element.scrollTo` is stubbed in `setup.js`; the tests
  confirm the citation lookup and the highlight, not the resulting offset.

### Browser checklist

Run against `npm run dev` with the backend up, on a completed analysis:

1. Every focusable element measures at least 24×24 —
   `[...document.querySelectorAll('a,button,input,[tabindex]')]` filtered on
   `getBoundingClientRect()`.
2. No horizontal scroll at 640px width:
   `document.documentElement.scrollWidth === clientWidth`.
3. A citation click scrolls the source pane and lands the target near the top.
4. Keyboard-only: reach the upload control, submit, tab the risk table, activate a
   citation. Focus ring visible throughout.

Playwright would automate all four and is the natural next addition. It was not worth a
browser binary for this pass.
