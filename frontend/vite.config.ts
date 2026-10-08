import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 本番では S3+CloudFront から同一オリジンの /api を叩く想定のため、
// ローカル開発でも API ベース URL は /api 固定にし、ここでバックエンドへプロキシする。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Claude を使う処理は Mac 上の AI サーバー(importer/ai_server.py)が受け持つ
      '/ai': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
