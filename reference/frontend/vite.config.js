import { defineConfig } from '../../../1029/node_modules/vite/dist/node/index.js';
import react from '../../../1029/node_modules/@vitejs/plugin-react/dist/index.js';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'react/jsx-runtime': 'c:/workAI/work9/1029/node_modules/react/jsx-runtime.js',
      'react/jsx-dev-runtime': 'c:/workAI/work9/1029/node_modules/react/jsx-dev-runtime.js',
      'react-dom/client': 'c:/workAI/work9/1029/node_modules/react-dom/client.js',
      'react-dom': 'c:/workAI/work9/1029/node_modules/react-dom/index.js',
      react: 'c:/workAI/work9/1029/node_modules/react/index.js',
    },
  },
  server: {
    port: 5174,
    open: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
});
