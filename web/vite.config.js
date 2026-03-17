import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: ['mermaid'],
    exclude: [],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          mermaid: ['mermaid'],
          mantine: ['@mantine/core', '@mantine/hooks', '@mantine/code-highlight'],
        },
      },
    },
  },
})
