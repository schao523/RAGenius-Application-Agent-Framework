import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// TODO: Add proxy/env config for backend API URL.
export default defineConfig({
  plugins: [react()],
});

