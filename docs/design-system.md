# Design System — Legal Document Analyzer

Reference document. Read this before any visual work. Do not paste it into CLAUDE.md.

**Aesthetic thesis:** institutional restraint. The product should read as a precision
instrument built for people whose professional liability is on the line. Gravitas comes
from the palette, typography, and spacing discipline. Modernity comes from interaction
quality — speed, crisp alignment, restrained motion — not from bright color, large
radii, or consumer-style delight.

The reference point is Harvey's stated design principle: deeply familiar to legal
professionals, yet unmistakably modern. The failure mode to avoid is a tool that looks
like a consumer AI wrapper — a risk-averse professional audience reads that as
untrustworthy, and for a portfolio project the reviewer *is* that audience.

---

## 1. Color

Define these as CSS custom properties and map them into `tailwind.config.js` as semantic
names. Components reference the semantic name, never the raw hex.

### Neutrals (the bulk of the interface)

| Token | Hex | Use |
|---|---|---|
| `ink` | `#111827` | Primary text. Never pure black on pure white — causes halation over long reading. |
| `ink-muted` | `#4B5563` | Secondary text, metadata, table labels |
| `ink-subtle` | `#6B7280` | Placeholder, disabled, timestamps |
| `border` | `#E5E7EB` | Hairline dividers, input borders |
| `border-strong` | `#D1D5DB` | Table header rules, active input borders |
| `surface` | `#FFFFFF` | Cards, panels, table rows |
| `surface-sunken` | `#F7F8FA` | App background, inactive panels |
| `surface-paper` | `#FAFAF7` | Document reading surface only — a warm off-white paper cue |

### Brand

| Token | Hex | Use |
|---|---|---|
| `brand` | `#0B2A4A` | Deep navy. Header chrome, primary buttons, logo lockup. |
| `brand-hover` | `#123A63` | Hover state |
| `brand-subtle` | `#EBF1F7` | Selected rows, active nav background |
| `accent` | `#0E7C86` | Deep teal. Links, focus rings, active tabs. ONE accent only. |

Navy is the legal-corporate anchor — roughly half of large firms use blue in their
branding, which is exactly why it reads as "this belongs in a law firm." The teal accent
is the modernizing move: it keeps the gravitas but sidesteps the navy/burgundy cliché.

Do not add a second accent. If something needs to stand out and `accent` is taken, the
answer is spacing or weight, not a new hue.

### Semantic / risk

Maps directly to your `HIGH | MEDIUM | LOW` severity enum.

| Severity | Text/icon | Background | Border |
|---|---|---|---|
| HIGH | `#B42318` | `#FEF3F2` | `#FDA29B` |
| MEDIUM | `#B54708` | `#FFFAEB` | `#FEC84B` |
| LOW | `#067647` | `#ECFDF3` | `#A6F4C5` |
| INFO | `#175CD3` | `#EFF8FF` | `#B2DDFF` |

**Non-negotiable:** severity always renders as color + icon + text label. Color alone
fails color-blind users and WCAG 1.4.1. `RiskBadge.jsx` should be physically incapable of
rendering without a label — no `showLabel` prop.

Use the muted background/border variants inside dense lists. Reserve saturated fills for
single-item emphasis.

### Dark mode

Out of scope for MVP. If added: `#121212`-family surfaces, never pure black; desaturate
`accent` to roughly `#3AA6AF`; keep 4.5:1. Light mode stays the default for document
reading regardless of what analytics say — positive polarity wins for long-form reading,
and there is no scientific consensus that dark mode helps.

---

## 2. Typography

### Recommended pairing

```
--font-serif: "Source Serif 4", Georgia, serif;      /* headings, brand, doc titles */
--font-sans:  "Inter", system-ui, sans-serif;        /* all UI, body, tables */
--font-mono:  "IBM Plex Mono", monospace;            /* clause IDs, page refs, defined terms */
```

Both Source Serif 4 and Inter are free (SIL OFL) and available via Google Fonts or
`@fontsource`. A fully valid alternative is all-IBM-Plex (Sans + Serif + Mono) — one
family, institutional and engineered-looking, slightly more "IBM" in feel.

**Serif for headings, sans for body** is the safest professional default. Empirical
readability research finds essentially no legibility difference between serif and sans on
screen — so this is a gravitas/brand decision, not a legibility mandate. Reserve serif for
H1–H3, the app wordmark, and document titles. Everything functional is sans.

### Scale (1.25 major third)

| Token | Size | Line height | Use |
|---|---|---|---|
| `xs` | 12px | 1.4 | Table metadata, badge text, captions |
| `sm` | 14px | 1.5 | UI labels, table body, buttons |
| `base` | 16px | 1.6 | Body copy, summaries |
| `lg` | 18px | 1.6 | Extracted document text |
| `xl` | 20px | 1.4 | Section headings (serif) |
| `2xl` | 25px | 1.3 | Page headings (serif) |
| `3xl` | 31px | 1.2 | Hero / marketing only (serif) |

### Long-form reading

The extracted clause text and the plain-English summary are the two surfaces users
actually read. Both get: 16–18px, line-height 1.6, max-width ~70ch (roughly 45–75
characters is the readable band), left-aligned. Never justify. Never full-bleed the
summary across a 1400px viewport.

Monospace earns its place on `page_reference` values, clause identifiers, and defined
terms — it signals precision and aligns cleanly in tables.

---

## 3. Spacing, density, layout

8px base grid; 4px for fine optical adjustment.

```
space: 4, 8, 12, 16, 24, 32, 48, 64
```

Professional tools carry **more** information density than consumer apps, but density is
earned through consistent spacing, not by crowding. The test: could a reviewer scan the
risk list and find the HIGH items in under two seconds?

- Table/list rows: 48px comfortable, 40px compact. Ship comfortable for MVP.
- 1px `border` dividers once a list exceeds ~10 rows; below that, whitespace is enough.
- Panel padding: 24px desktop, 16px mobile.
- Gap between stacked cards: 16px. Between page sections: 32–48px.

**Layout for `Analysis.jsx`:** split pane — document/extracted text on the left (~60%),
`ResultsPanel` on the right (~40%), `ClauseNavigator` as a left rail or a tab within the
results panel. This side-by-side arrangement is the dominant pattern in legal review tools
because it lets the user check a claim against the source without losing their place.
Below `lg` breakpoint, collapse to stacked tabs — do not try to keep two panes on mobile.

**Tables vs cards:** use a table for the risk flag list and the missing-clause list.
Cards are for the top-level summary and document metadata only. Decorative cards where a
scannable table would serve is the single most common way analytics UIs look amateurish.

---

## 4. Shape, elevation, iconography

| Token | Value |
|---|---|
| `radius-sm` | 2px (badges, inputs) |
| `radius-md` | 6px (buttons, cards) |
| `radius-lg` | 8px (modals, panels) — hard ceiling |
| `shadow-sm` | `0 1px 2px rgba(16,24,40,0.06)` |
| `shadow-md` | `0 4px 8px rgba(16,24,40,0.08)` |
| `shadow-lg` | `0 12px 24px rgba(16,24,40,0.10)` — modals/popovers only |

Icons: `lucide-react` (already in your deps), monoline, 16px in tables and badges, 20px in
navigation, 1.5px stroke. Do not mix icon sets. Do not use duotone or filled variants.

**Traditional levers** (use these): hairline borders, minimal shadow, small radii,
restrained line icons, a subtle page frame on the document surface.

**Modern levers** (use these): consistent 8px rhythm, fast transitions (~150ms), skeleton
loaders, generous type sizing, a command palette if you get there.

**Banned outright:** glassmorphism, gradient buttons, radii above 8px, heavy drop shadows,
emoji in UI copy, confetti or celebratory animation, gavel/scales-of-justice imagery,
faux-parchment or leather textures, stock photos of handshakes. Every one of these reads
as either dated or consumer-grade, and both are fatal in this category.

Light paper metaphor is the one skeuomorphic cue that works: a faint white page with
`shadow-sm` on `surface-sunken` orients the reader. Stop there.

---

## 5. Motion

Modernity lives here more than anywhere else in this document.

- Transitions: 150ms, `ease-out`. State changes (hover, focus, expand) only.
- Panel/route transitions: 200ms max. No slide-in theatrics.
- Loading: skeleton shapes matching final layout, not spinners, for anything over ~400ms.
- Respect `prefers-reduced-motion` — disable all non-essential transitions.
- Zero animation on anything that communicates risk. A HIGH severity flag does not pulse,
  bounce, or fade in dramatically. It is simply there.

---

## 6. Accessibility (build requirement)

WCAG 2.2 AA. This is not polish — it is a procurement gate in real legal/government
buying, and it is a visible quality signal in a portfolio review.

- 4.5:1 contrast for body text, 3:1 for large text (≥24px, or 18.66px bold) and for
  non-text UI components like input borders and icons.
- Visible focus indicator on every interactive element. Use `accent` at 2px offset — do
  not remove default outlines without replacing them.
- Full keyboard operability: upload, navigate clauses, expand a risk flag, dismiss a
  modal. Tab order follows visual order.
- 24×24px minimum target size (WCAG 2.2 SC 2.5.8).
- Layout survives 200% browser zoom without horizontal scroll.
- Announce analysis completion and errors via an `aria-live="polite"` region — a screen
  reader user should not have to poll the page.
- shadcn/ui is built on Radix primitives, which handle focus management, ARIA roles, and
  keyboard interaction correctly. Use them rather than hand-rolling dialogs, tabs, or
  tooltips.

---

## 7. Implementation notes for this stack

**Stack conflict — resolved:** `CLAUDE.md` previously listed shadcn/ui in the tech stack
but `@headlessui/react` in the frontend deps. shadcn/ui is built on Radix, not Headless UI,
and running both means two focus-management systems and two sets of unstyled primitives.
`@headlessui/react` has been dropped; the Radix packages arrive per component via shadcn's
CLI. Do not reintroduce Headless UI.

**Why shadcn/ui is right here:** you own the component source, so you can hit a bespoke
institutional aesthetic instead of shipping a recognizable house style (the giveaway with
MUI or Ant Design), while Radix underneath gives you the accessibility for free. For a
portfolio project the "this doesn't look like a template" quality is a large share of the
value.

**Token wiring order (do this before building components):**
1. Define the color/type/spacing/radius tokens as CSS custom properties in `globals.css`.
2. Map them to semantic names in `tailwind.config.js` (`text-ink`, `bg-surface-sunken`,
   `border-border`, `text-risk-high`).
3. Point shadcn's generated components at those semantic names.
4. Only then build `RiskBadge`, `ResultsPanel`, etc.

Name tokens by intent, not appearance — `surface-sunken` not `gray-50`, `risk-high` not
`red-700`. Appearance names break the moment you theme anything, and they let a component
reference a color for the wrong reason.

**Document rendering:** MVP renders extracted text from pdfplumber, so this is a
typography problem, not a PDF-viewer problem — style it as prose per §2 and move on. If
you later want true PDF display with highlight overlays, `react-pdf` (a React wrapper over
pdf.js) is the free path; it renders and paginates but ships no annotation layer, so
highlighting means building a text-layer overlay yourself. Commercial SDKs (Nutrient,
Apryse) solve that properly but are priced for enterprise and are overkill here.

---

## 8. Anti-patterns

These are the specific things that make legal software look untrustworthy:

- AI output with no provenance — a conclusion with nothing to check it against.
- Severity communicated by color alone.
- Hover-only actions; controls that appear only on mouseover.
- Wiping a form or losing uploaded state on a single validation error.
- Raw tracebacks or JSON surfaced to the user (already covered in CLAUDE.md — keep it).
- Opaque spinners for long operations with no sense of progress or stage.
- Empty states that are literally empty instead of telling the user what to do.
- Badge clutter — a wall of trust seals reads as compensating. A few real signals beat many.
- Pure `#000` on pure `#FFF` for sustained reading.
- Copying a dark, neon, high-contrast "modern SaaS" look wholesale. Borrow the spacing and
  performance discipline from tools like Linear or Stripe; do not borrow their skin.
