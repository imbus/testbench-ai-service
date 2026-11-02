import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The job page the TestBench client opens (`/jobs/{id}/view`), built apart from
// the console so it works with the console switched off. The service serves
// these assets at `/jobs/view-assets/` and fills the page's config itself.
export default defineConfig({
  plugins: [react()],
  base: '/jobs/view-assets/',
  build: {
    outDir: '../testbench_ai_service/static/job-view',
    emptyOutDir: true,
    rollupOptions: { input: 'job-view.html' },
  },
})
