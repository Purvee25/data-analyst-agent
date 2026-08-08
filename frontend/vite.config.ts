import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend calls the FastAPI backend at localhost:8000. During development
// we proxy /api -> the backend so the browser makes same-origin requests (no
// CORS preflight) and the app can be deployed behind one origin unchanged.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8010',
    },
  },
})
