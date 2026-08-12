import { Link, Route, Routes } from 'react-router-dom'
import { Scale } from 'lucide-react'
import Analysis from './pages/Analysis'
import Home from './pages/Home'

function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="font-serif text-2xl text-ink">Page not found</h1>
      <Link to="/" className="mt-4 inline-block text-sm text-accent underline underline-offset-2">
        Back to upload
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-surface-sunken">
      <header className="h-14 border-b border-border bg-brand">
        <div className="flex h-full items-center px-4">
          <Link to="/" className="flex items-center gap-2 rounded-sm text-surface">
            {/* The one permitted use of a scales glyph: a 20px monoline nav icon.
                design-system.md §4 bans gavel/scales IMAGERY — decorative legal
                clip art — not a wordmark lockup. Keep it at this weight. */}
            <Scale size={20} strokeWidth={1.5} aria-hidden="true" />
            <span className="font-serif text-lg">Legal Document Analyzer</span>
          </Link>
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/analysis/:jobId" element={<Analysis />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
