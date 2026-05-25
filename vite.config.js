import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // During local dev — proxy /chat calls to FastAPI
      '/chat':   'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
});
