import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Runs only the upload dialog variant generator; the normal suite never sees it.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/dev/upload-variants/generate.tsx'],
  },
})
