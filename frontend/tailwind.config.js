/**
 * Semantic token map. Step 2 of the wiring order in docs/design-system.md §7:
 * custom properties are declared in src/globals.css, named by INTENT here, and
 * only then referenced by components.
 *
 * Components use these names and nothing else. A hex literal or a raw palette
 * class (`bg-gray-50`, `text-red-700`) in a component is a rule violation —
 * see .claude/rules/frontend-ui.md — because an appearance name lets a component
 * reach for a colour for the wrong reason, and breaks the moment anything is
 * themed.
 */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: 'var(--color-ink)',
          muted: 'var(--color-ink-muted)',
          subtle: 'var(--color-ink-subtle)',
        },
        border: {
          DEFAULT: 'var(--color-border)',
          strong: 'var(--color-border-strong)',
        },
        surface: {
          DEFAULT: 'var(--color-surface)',
          sunken: 'var(--color-surface-sunken)',
          paper: 'var(--color-surface-paper)',
        },
        brand: {
          DEFAULT: 'var(--color-brand)',
          hover: 'var(--color-brand-hover)',
          subtle: 'var(--color-brand-subtle)',
        },
        // ONE accent. If something else needs to stand out, the answer is
        // spacing or weight, not a second hue (design-system.md §1).
        accent: 'var(--color-accent)',
        risk: {
          high: {
            DEFAULT: 'var(--color-risk-high)',
            bg: 'var(--color-risk-high-bg)',
            border: 'var(--color-risk-high-border)',
          },
          medium: {
            DEFAULT: 'var(--color-risk-medium)',
            bg: 'var(--color-risk-medium-bg)',
            border: 'var(--color-risk-medium-border)',
          },
          low: {
            DEFAULT: 'var(--color-risk-low)',
            bg: 'var(--color-risk-low-bg)',
            border: 'var(--color-risk-low-border)',
          },
          info: {
            DEFAULT: 'var(--color-risk-info)',
            bg: 'var(--color-risk-info-bg)',
            border: 'var(--color-risk-info-border)',
          },
        },
      },
      fontFamily: {
        serif: 'var(--font-serif)',
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      // 1.25 major third, design-system.md §2. Line heights ride with the size so
      // a component cannot pick 12px text with 1.6 leading by accident.
      fontSize: {
        xs: ['12px', { lineHeight: '1.4' }],
        sm: ['14px', { lineHeight: '1.5' }],
        base: ['16px', { lineHeight: '1.6' }],
        lg: ['18px', { lineHeight: '1.6' }],
        xl: ['20px', { lineHeight: '1.4' }],
        '2xl': ['25px', { lineHeight: '1.3' }],
        '3xl': ['31px', { lineHeight: '1.2' }],
      },
      borderRadius: {
        sm: '2px', // badges, inputs
        md: '6px', // buttons, cards
        lg: '8px', // modals, panels — hard ceiling
      },
      boxShadow: {
        sm: '0 1px 2px rgba(16,24,40,0.06)',
        md: '0 4px 8px rgba(16,24,40,0.08)',
        lg: '0 12px 24px rgba(16,24,40,0.10)', // modals/popovers only
      },
      // The readable band for long-form document text (design-system.md §2).
      maxWidth: {
        measure: '70ch',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
    },
  },
  plugins: [],
}
