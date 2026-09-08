import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  build: {
    outDir: '../testbench_ai_service/static/admin',
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` talks to a locally running service
    proxy: { '/admin/api': 'http://127.0.0.1:8010' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
  },
})
