import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build is committed into api/static/app and served by FastAPI, so running the
// project never needs Node. `npm run dev` proxies the API for live UI work.
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: { outDir: "../api/static/app", emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: {
    proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" },
  },
});
