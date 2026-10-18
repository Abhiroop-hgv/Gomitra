import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The router (FastAPI) serves the built app: index.html at "/" and assets under "/static/".
// `npm run build` writes into router/static, next to the sample files that already live there.
export default defineConfig({
  base: '/static/',
  plugins: [react()],
  build: { outDir: '../router/static', emptyOutDir: false, assetsDir: 'assets' },
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8080', '/static/samples': 'http://localhost:8080' },
  },
});
