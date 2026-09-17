import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

// https://vitejs.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // 🔑 开发期把 API 请求转给后端（默认 8000）。
    //
    // 为什么需要它：前端已改为"同源相对路径"（OpenAPI.BASE = ""），
    // 浏览器会请求 http://localhost:5173/api/v1/... —— 但 5173 是 vite 的
    // 静态服务器，不认识 /api，请求到不了后端。这里把它转发过去。
    //
    // 这样开发和生产的**代码路径完全一致**（都是 /api/v1/...，都由同源提供），
    // 唯一差别是"谁在转发"：开发时是 vite，生产时是后端自己托管。
    //
    // 后端换端口时无需改代码：BACKEND_URL=http://localhost:8001 bun run dev
    proxy: {
      "/api": {
        target: process.env.BACKEND_URL || "http://localhost:8000",
        changeOrigin: true,
        // WebSocket 走同一路径前缀，需要显式开启（否则聊天流式会连不上）
        ws: true,
      },
    },
  },
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
})
