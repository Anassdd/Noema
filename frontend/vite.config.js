import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev server runs on 5173 — the origin the backend's CORS allow-list expects.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
});
