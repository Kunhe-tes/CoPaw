import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Empty = same-origin; frontend and backend served together, no hardcoded host.
  // Use a dedicated Vite-prefixed key so unrelated shell BASE_URL values don't leak into the build.
  const apiBaseUrl = env.VITE_API_BASE_URL ?? "";
  // 本地 Vite 开发服务器使用固定管理员身份，便于直接访问管理页面。
  // 该配置仅作用于 dev proxy，不会进入生产构建或覆盖 iframe 生产身份。
  const localAdminHeaders = {
    "X-User-Role": "admin",
    "X-Source-Id": "RMASSIST",
    "X-User-Id": "80280195",
    "X-Tenant-Id": "80280195",
  };

  return {
    define: {
      VITE_API_BASE_URL: JSON.stringify(apiBaseUrl),
      TOKEN: JSON.stringify(env.TOKEN || ""),
      MOBILE: false,
    },
    plugins: [react()],
    css: {
      modules: {
        localsConvention: "camelCase",
        generateScopedName: "[name]__[local]__[hash:base64:5]",
      },
      preprocessorOptions: {
        less: {
          javascriptEnabled: true,
        },
      },
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      target: "chrome80",
      cssTarget: "chrome80",
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api/market": {
          target: "http://127.0.0.1:8091",
          changeOrigin: true,
          headers: localAdminHeaders,
        },
        "/api/monitor": {
          target: "http://127.0.0.1:9090",
          changeOrigin: true,
          headers: localAdminHeaders,
        },
        "/api": {
          target: "http://127.0.0.1:8088",
          changeOrigin: true,
          headers: localAdminHeaders,
        },
      },
    },
    // build: {
    //   // Output to CoPaw's console directory,
    //   // so we don't need to copy files manually after build.
    //   outDir: path.resolve(__dirname, "../src/copaw/console"),
    //   emptyOutDir: true,
    // },
  };
});
