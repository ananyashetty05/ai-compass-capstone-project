import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Dev only: lets a browser that can reach only this dev server (for example
  // an embedded preview pane) use the API through /api. Normal setups that set
  // VITE_API_BASE_URL are unaffected.
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8080', changeOrigin: true },
    },
  },
})
