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
})
