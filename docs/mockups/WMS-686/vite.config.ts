import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { demoTransform } from "./demoTransform";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL(".", import.meta.url));
export default defineConfig({
  root,
  plugins: [demoTransform(), react()],
  resolve: {
    dedupe: [
      "react",
      "react-dom",
      "@mui/material",
      "@emotion/react",
      "@emotion/styled",
    ],
  },
  server: {
    host: "127.0.0.1",
    port: 16866,
    fs: { allow: [fileURLToPath(new URL("../../../", import.meta.url))] },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
