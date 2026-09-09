import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

// https://vitejs.dev/config/
export default defineConfig({
  resolve: {
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "i18next", "react-i18next"],
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // 开发代理：前端 :5173 的 /api 转发到 backend :8000
  //（单进程 backend-unified 或多进程 backend 均监听 8000）。
  // 缺此代理时，相对 /api 请求会落到 vite dev server：GET 被 SPA fallback 成 index.html(200)、
  // POST 返回 404 —— 即 dashboard 崩溃与 /api/v1/logs/batch 404 的根因。
  // 如需指向其它后端地址，设 VITE_API_URL（fsiClient / logger 会用作 BASE）。
  server: {
    hmr: {
      protocol: "ws",
      host: "localhost",
    },
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    include: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "i18next", "react-i18next"],
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
