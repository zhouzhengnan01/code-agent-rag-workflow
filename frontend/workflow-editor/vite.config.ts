import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/assets/workflow-editor/',
  build: { outDir: '../../web/workflow-editor', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8080' } },
});
