import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-time proxy so the frontend (localhost:5173) can call the
// backend (localhost:8000) without CORS headaches. Adjust the
// target if your backend runs on a different port.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
