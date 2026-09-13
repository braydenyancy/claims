import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// The browser only ever talks to /api on its own origin. The dev server
// forwards it to the API container, so the session cookie is first-party
// and CSRF needs nothing more than the header (D3).
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
    globals: true,
  },
});
