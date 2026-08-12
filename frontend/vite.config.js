import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Must match an entry in backend/config.py::ALLOWED_ORIGINS. The API refuses
    // unknown origins on purpose — these requests carry an uploaded document, so
    // the allowlist is never "*".
    port: 5173,
    strictPort: true,
  },
  // Vitest config lives here rather than in its own file so there is only one
  // place where the React plugin and the test environment can disagree.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/tests/setup.js',
    include: ['src/tests/**/*.test.{js,jsx}'],
  },
})
