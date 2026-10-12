import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  build: {
    outDir: '../testbench_ai_service/static/admin',
    emptyOutDir: true,
    // Monaco already lazy-loads into its own ~3.4 MB chunk; it can't be
    // split further, so the limit is raised to cover it
    chunkSizeWarningLimit: 3500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('monaco-editor')) return
          if (id.includes('primereact')) return 'primereact'
          if (/[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(id)) return 'react'
          if (/[\\/](react-markdown|remark-|micromark|mdast-|unified|hast-)/.test(id)) return 'markdown'
        },
      },
    },
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
