import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo (`npm run dev`) las llamadas a /api se envían al backend local.
export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, ".", "").VITE_PROXY_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target, changeOrigin: true },
        "/health": { target, changeOrigin: true },
      },
    },
  };
});
