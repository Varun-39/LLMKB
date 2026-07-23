import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Backend (FastAPI) is served separately at 127.0.0.1:8000 and has no CORS
// middleware configured — proxying same-origin here means the browser never
// makes a cross-origin request, so nothing on the backend needs to change.
// The proxy applies in both `vite dev` and `vite preview`, so the built
// static bundle behaves the same way as dev.
const proxy = {
  '/alert': 'http://127.0.0.1:8000',
  '/cards': 'http://127.0.0.1:8000',
  '/health': 'http://127.0.0.1:8000',
  '/ingest': 'http://127.0.0.1:8000',
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy, port: 5173 },
  preview: { proxy, port: 4173 },
})
