import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/strategy/',
  server: {
    proxy: {
      '/strategy/api': 'http://127.0.0.1:8000',
    },
  },
})
