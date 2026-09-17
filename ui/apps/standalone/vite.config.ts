import react from "@vitejs/plugin-react";
import { defineConfig, type ProxyOptions } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(["/reader", "/library/topics", "/library/sources"].map(path => [path, {
      target: "http://127.0.0.1:8765", changeOrigin: true,
      configure(proxy) {
        proxy.on("proxyReq", (req, incoming) => {
          const origin = incoming.headers.origin;
          if (origin === "http://localhost:5173" || origin === "http://127.0.0.1:5173") req.setHeader("Origin", "http://127.0.0.1:8765");
        });
      },
    } satisfies ProxyOptions])),
  },
});
