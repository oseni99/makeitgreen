import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // Listen on IPv4 + IPv6. Default Node bind is often ::1 only, which makes
    // http://127.0.0.1:5173 fail while http://localhost:5173 works (and vice
    // versa depending on the browser). Pin the API proxy to IPv4 to match
    // uvicorn's 127.0.0.1:8000 bind.
    host: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
