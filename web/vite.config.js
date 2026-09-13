import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // /api is the web Lambda. In development it runs on localhost against the
  // real runtime: `python scripts/web_api_local.py` from the repo root.
  server: {
    proxy: { '/api': 'http://127.0.0.1:8787' },
  },
  build: {
    target: 'es2020',
    cssCodeSplit: false,
    assetsInlineLimit: 2048,
  },
})
