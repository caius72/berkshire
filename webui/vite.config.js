import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to `berkshire serve`, so the page talks same-origin
// and the backend never needs CORS (see berkshire/server.py).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.BERKSHIRE_API ?? 'http://127.0.0.1:8787', changeOrigin: true },
    },
  },
})
